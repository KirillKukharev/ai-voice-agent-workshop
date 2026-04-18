import logging
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """App settings"""

    APP_VERSION: str
    APP_MODE: str
    APP_CONTAINERIZED: str
    APP_ENABLE_DOCS: bool = True

    APP_LOG_LEVEL: str = "DEBUG"
    APP_LOG_PATH: str | None = None

    APP_TOKEN: str

    DEFAULT_API_RETRY_COUNT: int = 5
    DEFAULT_API_RETRY_START_TIMEOUT: float = 1
    VERIFY_SSL: bool = True

    STT_MODEL: str = ""

    class ConfigDict:
        env_file = str(Path(__file__).parent.parent.parent / ".env")
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings(  # type: ignore
        APP_VERSION="0.0.1",
    )


app_settings = get_settings()
