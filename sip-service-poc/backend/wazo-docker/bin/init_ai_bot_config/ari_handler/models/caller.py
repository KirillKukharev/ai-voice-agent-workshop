from pydantic import BaseModel


class Caller(BaseModel):
    """Represents a caller in the ARI system."""

    name: str
    number: str
