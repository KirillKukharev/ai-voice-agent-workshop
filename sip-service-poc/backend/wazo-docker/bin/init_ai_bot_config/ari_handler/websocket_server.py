"""WebSocket server for frontend: session start, Airtable load on connect, periodic refresh."""

import asyncio
import concurrent.futures
import json
import logging

import websockets
from websockets.server import WebSocketServerProtocol

from .airtable_client import read_bookings, read_tickets
from .airtable_loader import load_airtable_data_for_user
from .websocket_events import (
    _connections,
    register_connection,
    unregister_connection,
)

logger = logging.getLogger("ari_handler.websocket")


async def websocket_handler(websocket: WebSocketServerProtocol, path: str) -> None:
    """Handle WebSocket connections: send session_start, load Airtable for session_id, periodic refresh."""
    await register_connection(websocket)

    try:
        session_id = "unknown"
        if "?" in path:
            query = path.split("?")[1]
            params = dict(p.split("=") for p in query.split("&") if "=" in p)
            session_id = params.get("session_id", "unknown")

        logger.info(
            "WebSocket connection from %s, session_id=%s",
            websocket.remote_address,
            session_id,
        )

        async def load_data_for_session() -> None:
            try:
                await websocket.send(
                    json.dumps(
                        {
                            "event": "session_start",
                            "session_id": session_id or "unknown",
                            "payload": {},
                        }
                    )
                )
                logger.info("Sent session_start event to new connection")
            except Exception as e:
                logger.warning("Failed to send session_start: %s", e)

            await asyncio.sleep(0.5)

            phone_number = None
            if session_id and session_id != "unknown":
                clean = session_id.replace("+", "").replace("-", "").replace(" ", "")
                if session_id.startswith("+") or clean.isdigit():
                    phone_number = session_id
                    logger.info("Detected phone number from session_id: %s", phone_number)

            async def load_data() -> None:
                if phone_number:
                    try:
                        logger.info(
                            "Loading Airtable data for WebSocket session: %s",
                            phone_number,
                        )
                        await load_airtable_data_for_user(phone_number=phone_number, session_id=session_id)
                    except Exception as e:
                        logger.error(
                            "Error loading Airtable data for session %s: %s",
                            session_id,
                            e,
                            exc_info=True,
                        )
                elif session_id == "waiting":
                    try:
                        loop = asyncio.get_event_loop()
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            bookings_task = loop.run_in_executor(executor, read_bookings, 10)
                            tickets_task = loop.run_in_executor(executor, read_tickets, 10)
                            all_bookings, all_tickets = await asyncio.gather(bookings_task, tickets_task)

                        phone_numbers: set[str] = set()
                        for booking in all_bookings.get("bookings", []):
                            phone = booking.get("fields", {}).get("telephone_number_booking", "")
                            if phone:
                                phone_numbers.add(phone)
                        for ticket in all_tickets.get("tickets", []):
                            fields = ticket.get("fields", {})
                            phone = fields.get("telephone_number_tech", "") or fields.get(
                                "telephone_number_booking", ""
                            )
                            if phone:
                                phone_numbers.add(phone)

                        for phone in list(phone_numbers)[:5]:
                            try:
                                await load_airtable_data_for_user(phone_number=phone, session_id=session_id)
                                await asyncio.sleep(0.2)
                            except Exception as e:
                                logger.error("Error loading data for phone %s: %s", phone, e)
                    except Exception as e:
                        logger.error(
                            "Error loading Airtable data for test session: %s",
                            e,
                            exc_info=True,
                        )
                else:
                    logger.debug(
                        "Skipping Airtable load for session_id=%s (not a phone number or test session)",
                        session_id,
                    )

            await load_data()

            while True:
                try:
                    await asyncio.sleep(30.0)
                    if websocket not in _connections:
                        logger.info(
                            "Connection closed, stopping periodic Airtable updates for %s",
                            session_id,
                        )
                        break
                    logger.info("Periodic Airtable data refresh for session: %s", session_id)
                    await load_data()
                except asyncio.CancelledError:
                    logger.info("Periodic Airtable updates cancelled for %s", session_id)
                    break
                except Exception as e:
                    logger.error(
                        "Error in periodic Airtable update for %s: %s",
                        session_id,
                        e,
                        exc_info=True,
                    )
                    await asyncio.sleep(30.0)

        asyncio.create_task(load_data_for_session())

        async for message in websocket:
            try:
                data = json.loads(message)
                logger.debug("Received WebSocket message: %s", data)
                if data.get("type") == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from WebSocket: %s", message)
            except Exception as e:
                logger.error("Error handling WebSocket message: %s", e, exc_info=True)

    except websockets.exceptions.ConnectionClosed:
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.error("WebSocket error: %s", e, exc_info=True)
    finally:
        await unregister_connection(websocket)


async def start_websocket_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start WebSocket server."""
    logger.info("Starting WebSocket server on %s:%s", host, port)

    async with websockets.serve(websocket_handler, host, port):
        logger.info("WebSocket server running on ws://%s:%s", host, port)
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            logger.info("WebSocket server is shutting down...")
            raise
