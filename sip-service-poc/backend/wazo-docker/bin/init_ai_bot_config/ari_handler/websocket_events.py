"""Shared WebSocket connection registry and broadcast for Airtable/LLM events."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("ari_handler.websocket_events")

_connections: set[Any] = set()
_connection_lock = asyncio.Lock()


async def register_connection(websocket: Any) -> None:
    """Register a new WebSocket connection."""
    async with _connection_lock:
        _connections.add(websocket)
        logger.info("WebSocket connected. Total connections: %d", len(_connections))


async def unregister_connection(websocket: Any) -> None:
    """Unregister a WebSocket connection."""
    async with _connection_lock:
        _connections.discard(websocket)
        logger.info("WebSocket disconnected. Total connections: %d", len(_connections))


async def broadcast_event(event: dict[str, Any]) -> None:
    """Broadcast event to all connected WebSocket clients."""
    if not _connections:
        logger.debug("No WebSocket connections, event not sent: %s", event.get("event"))
        return

    message = json.dumps(event, ensure_ascii=False)
    disconnected: set[Any] = set()

    async with _connection_lock:
        for websocket in _connections:
            try:
                await websocket.send(message)
            except Exception as e:
                logger.warning("Failed to send to WebSocket: %s", e)
                disconnected.add(websocket)

        for ws in disconnected:
            _connections.discard(ws)


def send_ticket_created_event(
    ticket_id: str,
    category: str,
    description: str,
    session_id: str | None = None,
) -> None:
    """Send ticket_created event to frontend."""
    event = {
        "event": "ticket_created",
        "session_id": session_id or "unknown",
        "payload": {
            "ticket_id": ticket_id,
            "department": category,
            "summary": description,
            "created_at": datetime.now(UTC).isoformat(),
        },
    }
    asyncio.create_task(broadcast_event(event))
    logger.info("Sent ticket_created event: %s", ticket_id)


def send_booking_created_event(
    booking_id: str,
    service: str,
    guest_name: str,
    date: str,
    time: str,
    guests_count: int,
    session_id: str | None = None,
) -> None:
    """Send booking_created event to frontend."""
    details = f"Гость: {guest_name}; услуга: {service}; дата: {date}; время: {time}; гостей: {guests_count}"
    event = {
        "event": "booking_created",
        "session_id": session_id or "unknown",
        "payload": {
            "booking_id": booking_id,
            "service": service,
            "details": details,
            "status": "confirmed",
            "guest_name": guest_name,
            "created_at": datetime.now(UTC).isoformat(),
        },
    }
    asyncio.create_task(broadcast_event(event))
    logger.info("Sent booking_created event: %s", booking_id)
