from backend.core.constants.base import AppStringEnum


class LogColor(AppStringEnum):
    """Log color"""

    DEBUG = "cyan"
    INFO = "green"
    WARNING = "yellow"
    ERROR = "red"
    CRITICAL = "bold_red"
