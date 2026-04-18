from pydantic import BaseModel, field_validator

from ari_handler.models.channel import Channel
from ari_handler.models.event_type import EventType


class Event(BaseModel):
    """Base class for ARI events."""

    type: EventType
    timestamp: str
    channel: Channel | None = None
    asterisk_id: str
    application: str

    @field_validator("type", mode="before")
    def validate_event_type(cls, value) -> EventType:
        """
        Validate and convert the event type to an EventType enum.
        Unknown event types will be set to EventType.UNKNOWN.
        """
        try:
            return EventType(value)
        except ValueError:
            return EventType.UNKNOWN
