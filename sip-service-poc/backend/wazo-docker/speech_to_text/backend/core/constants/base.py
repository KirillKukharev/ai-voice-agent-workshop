from enum import IntEnum, StrEnum


class AppStringEnum(StrEnum):
    """Base Enum class for strings"""

    def __str__(self):
        return self.value


class AppNumberEnum(IntEnum):
    """Base Enum class for int's"""

    def __str__(self):
        return str(self.value)
