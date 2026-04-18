from enum import StrEnum


class CodecType(StrEnum):
    G722 = "g722"
    G711 = "g711"


class StasisEventType(StrEnum):
    STASIS_START = "StasisStart"
    STASIS_END = "StasisEnd"
    UNKNOWN = "Unknown"


class ConversationRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    META = "meta"
