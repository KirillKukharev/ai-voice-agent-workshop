from enum import StrEnum


class EventType(StrEnum):
    """Enum representing the different types of events that can be handled by the ARI handler."""

    STASIS_START = "StasisStart"
    STASIS_END = "StasisEnd"
    UNKNOWN = "Unknown"  # Default value for unknown events
