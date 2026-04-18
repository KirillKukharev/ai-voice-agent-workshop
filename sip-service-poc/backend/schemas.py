from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class DashboardEvent(BaseModel):
    """Generic dashboard event payload."""

    event: str = Field(..., description="Event discriminator")
    session_id: str | None = Field(default=None, description="Optional session identifier")
    payload: dict[str, Any] = Field(default_factory=dict, description="Event-specific payload")


class ServiceTicketRequest(BaseModel):
    """Incoming request for service ticket creation."""

    room_number: str = Field(..., description="Guest room number")
    category: Literal["maintenance", "housekeeping"] = Field(..., description="Ticket category")
    description: str = Field(..., description="Guest-provided description")
    phone_number: str | None = Field(default=None, description="Guest phone number")
    session_id: str | None = Field(default=None, description="Optional session identifier for event fan-out")


class BookingRequest(BaseModel):
    """Incoming request for booking creation."""

    service: Literal["restaurant", "spa"] = Field(..., description="Service to reserve")
    date: str = Field(..., description="ISO date string in YYYY-MM-DD format")
    time: str = Field(..., description="Time string in HH:MM format")
    guests_count: int = Field(..., ge=1, description="Number of guests")
    guest_name: str = Field(..., description="Reservation name")
    phone_number: str | None = Field(default=None, description="Guest phone number")
    session_id: str | None = Field(default=None, description="Optional session identifier for event fan-out")


class TicketCreatedPayload(BaseModel):
    """Payload broadcast when a ticket is created."""

    ticket_id: str
    department: Literal["maintenance", "housekeeping"]
    summary: str
    created_at: datetime


class BookingCreatedPayload(BaseModel):
    """Payload broadcast when a booking is created."""

    booking_id: str
    service: Literal["restaurant", "spa"]
    details: str
    status: Literal["confirmed", "pending", "cancelled"]
    guest_name: str
    created_at: datetime


class BotCitation(BaseModel):
    """Knowledge source reference that justifies a bot response."""

    source: str
    content: str
    url: HttpUrl = None


class BotResponsePayload(BaseModel):
    """Payload for bot response events."""

    text: str
    citations: list[BotCitation] | None = None
    latency_ms: int | None = None


class TextQueryRequest(BaseModel):
    """Manual text query submission for plan B scenario."""

    query: str = Field(..., min_length=1, description="Text query content")
    session_id: str | None = Field(default=None, description="Optional session identifier for event fan-out")


class ServiceTicketResponse(BaseModel):
    """Response contract for ticket creation."""

    ticket_id: str
    status: Literal["created"]
    payload: TicketCreatedPayload


class BookingResponse(BaseModel):
    """Response contract for booking creation."""

    booking_id: str
    status: Literal["confirmed", "pending"]
    payload: BookingCreatedPayload


class GenericStatusResponse(BaseModel):
    """Lightweight acknowledgement schema."""

    status: Literal["accepted", "queued"]
