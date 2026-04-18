"""Handle Dify tool calls: create_ticket, create_booking — Airtable read + WebSocket events."""

import logging
from uuid import uuid4

from .airtable_client import (
    check_booking_availability,
    read_bookings,
    read_tickets,
)
from .phone_utils import matches_phone
from .websocket_events import send_booking_created_event, send_ticket_created_event

logger = logging.getLogger("ari_handler.tool_call")


async def handle_tool_call(
    tool_name: str,
    tool_inputs: dict,
    conversation_id: str | None = None,
    user: str | None = None,
) -> None:
    """Handle tool calls from Dify: create_service_ticket, create_ticket, create_booking, book_service."""
    try:
        logger.info("Handling tool call: %s, inputs: %s, user: %s", tool_name, tool_inputs, user)

        if tool_name in ("create_service_ticket", "create_ticket"):
            category = tool_inputs.get("category", "maintenance")
            description = tool_inputs.get("description", "")

            try:
                all_tickets_data = read_tickets(limit=10)
                user_tickets = []
                for ticket in all_tickets_data.get("tickets", []):
                    fields = ticket.get("fields", {})
                    ticket_phone = fields.get("telephone_number_tech", "") or fields.get("telephone_number_booking", "")
                    if user and matches_phone(ticket_phone, user):
                        user_tickets.append(ticket)
            except Exception as e:
                logger.error("Failed to read tickets from Airtable: %s", e, exc_info=True)

            ticket_id = f"ticket-{uuid4().hex[:8]}"
            send_ticket_created_event(
                ticket_id=ticket_id,
                category=category,
                description=description,
                session_id=conversation_id or user or "unknown",
            )

        elif tool_name in ("create_booking", "book_service"):
            service = tool_inputs.get("service", "restaurant")
            date = tool_inputs.get("date", "")
            time = tool_inputs.get("time", "")
            guests_count = tool_inputs.get("guests_count", 1)
            guest_name = tool_inputs.get("guest_name", "")

            availability = check_booking_availability(service=service, date=date, time=time)

            try:
                all_bookings_data = read_bookings(limit=10)
                user_bookings = []
                for booking in all_bookings_data.get("bookings", []):
                    fields = booking.get("fields", {})
                    booking_phone = fields.get("telephone_number_booking", "")
                    if user and matches_phone(booking_phone, user):
                        if service and fields.get("booking_service") != service:
                            continue
                        if date and fields.get("date") != date:
                            continue
                        user_bookings.append(booking)
            except Exception as e:
                logger.error("Failed to read bookings from Airtable: %s", e, exc_info=True)

            booking_id = f"booking-{uuid4().hex[:8]}"
            send_booking_created_event(
                booking_id=booking_id,
                service=service,
                guest_name=guest_name,
                date=date,
                time=time,
                guests_count=guests_count,
                session_id=conversation_id or user or "unknown",
            )

            if not availability.get("available", True):
                logger.warning("Booking conflict detected: %s", availability)
        else:
            logger.warning("Unknown tool call: %s", tool_name)

    except Exception as e:
        logger.error("Failed to handle tool call: %s", e, exc_info=True)
