"""Load Airtable data for a user and broadcast booking_loaded/ticket_loaded via WebSocket."""

import asyncio
import datetime
import logging

from .airtable_client import (
    get_airtable_executor,
    read_bookings,
    read_tickets,
)
from .phone_utils import matches_phone
from .websocket_events import broadcast_event

logger = logging.getLogger("ari_handler.airtable_loader")


async def load_airtable_data_for_user_async(phone_number: str, session_id: str) -> None:
    """
    Asynchronous wrapper for loading data from Airtable.
    Blocking calls run in executor so as not to block the event loop.
    """
    if not phone_number:
        logger.warning("No phone number provided, skipping Airtable load")
        return

    try:
        loop = asyncio.get_event_loop()
        executor = get_airtable_executor()

        bookings_task = loop.run_in_executor(executor, read_bookings, 10)
        tickets_task = loop.run_in_executor(executor, read_tickets, 10)

        logger.debug("Waiting for Airtable data...")
        all_bookings_data, all_tickets_data = await asyncio.gather(bookings_task, tickets_task)
        logger.debug("Loading data from Airtable completed")

        try:
            user_bookings = []
            for booking in all_bookings_data["bookings"]:
                fields = booking.get("fields", {})
                booking_phone = fields.get("telephone_number_booking", "")
                if matches_phone(booking_phone, phone_number):
                    user_bookings.append(booking)

            for booking in user_bookings[:5]:
                fields = booking.get("fields", {})
                guests_count = fields.get("guests_count", 0)
                if isinstance(guests_count, str):
                    try:
                        guests_count = int(float(guests_count.replace(",", ".")))
                    except Exception:
                        guests_count = 0
                elif isinstance(guests_count, float):
                    guests_count = int(guests_count)

                event = {
                    "event": "booking_loaded",
                    "session_id": session_id,
                    "payload": {
                        "booking_id": booking.get("id"),
                        "service": fields.get("booking_service", ""),
                        "guest_name": fields.get("guest_name", ""),
                        "date": fields.get("date", ""),
                        "time": fields.get("time", ""),
                        "guests_count": guests_count,
                        "loaded_at": datetime.datetime.now(datetime.UTC).isoformat(),
                    },
                }
                await broadcast_event(event)
        except Exception as e:
            logger.error(
                "Failed to process bookings from Airtable for %s: %s",
                phone_number,
                e,
                exc_info=True,
            )

        try:
            user_tickets = []
            for ticket in all_tickets_data["tickets"]:
                fields = ticket.get("fields", {})
                ticket_phone = fields.get("telephone_number_tech", "") or fields.get("telephone_number_booking", "")
                if not ticket_phone:
                    continue
                if matches_phone(ticket_phone, phone_number):
                    user_tickets.append(ticket)

            if len(user_tickets) == 0 and session_id == "waiting" and all_tickets_data["count"] > 0:
                user_tickets = all_tickets_data["tickets"][:5]

            for ticket in user_tickets[:5]:
                fields = ticket.get("fields", {})
                room_number = fields.get("room_number", "") or fields.get("guest_number", "") or "N/A"
                description = (
                    fields.get("problem_description", "") or fields.get("description", "") or fields.get("comment", "")
                )
                event = {
                    "event": "ticket_loaded",
                    "session_id": session_id,
                    "payload": {
                        "ticket_id": ticket.get("id"),
                        "room_number": room_number,
                        "category": fields.get("category", "") or "N/A",
                        "description": description,
                        "loaded_at": datetime.datetime.now(datetime.UTC).isoformat(),
                    },
                }
                await broadcast_event(event)
        except Exception as e:
            logger.error(
                "Failed to process tickets from Airtable for %s: %s",
                phone_number,
                e,
                exc_info=True,
            )

    except Exception as e:
        logger.error("Error loading Airtable data for %s: %s", phone_number, e, exc_info=True)


async def load_airtable_data_for_user(phone_number: str, session_id: str) -> None:
    """Wrapper: load Airtable data for user by phone and broadcast to WebSocket."""
    await load_airtable_data_for_user_async(phone_number=phone_number, session_id=session_id)
