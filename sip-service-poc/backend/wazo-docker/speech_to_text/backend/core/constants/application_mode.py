from backend.core.constants.base import AppStringEnum


class ApplicationMode(AppStringEnum):
    """App work modes"""

    LOCAL = "LOCAL"
    DEV = "DEV"
    PROD = "PROD"
