from pydantic import BaseModel


class Dialplan(BaseModel):
    """Represents a dialplan in the ARI system."""

    context: str
    exten: str
    priority: int
    app_name: str
    app_data: str
