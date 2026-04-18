import logging
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

_env_file_path = Path(__file__).parent.parent.parent.parent / ".env"


class Settings(BaseSettings):
    APP_VERSION: str = "1.0.0"
    APP_MODE: str = "development"
    WAZO_TENANT_UUID: UUID = UUID("701e1f61-8c23-4e62-b564-7a049adf0aef")

    STT_BASE_URL: str = "http://speech_to_text:8000/v1/speech_recognition"
    STT_MODEL: str = "gigaam"
    TTS_MODEL: str = "yandex"
    STT_TOKEN: str = ""

    MAX_AVAILABLE_CALLS: int = 10
    MAX_DIALOG_CONTEXT: int = 20
    MAX_SILENCE_DURATION: float = 1.2
    SILENCE_TIMEOUT: float = 5.0
    MAX_CONVERSATION_LENGTH: int = 300

    WAZO_AUTH_USERNAME: str = "root"
    WAZO_AUTH_PASSWORD: str = ""

    ARI_HOST: str = "asterisk"
    ARI_PORT: int = 5039
    ARI_USER: str = "ariuser"
    ARI_PASSWORD: str = ""
    ARI_APP_NAME: str = "voicebot"

    SERVICE_ACCOUNT_ID: str = Field(..., validation_alias="YANDEX_SERVICE_ACCOUNT_ID")
    SA_KEY_ID: str = Field(..., validation_alias="YANDEX_SA_KEY_ID")
    PRIVATE_KEY: str = Field(..., validation_alias="YANDEX_PRIVATE_KEY")
    FOLDER_ID: str = Field(..., validation_alias="YANDEX_FOLDER_ID")

    NOCODE_BASE_URL: str = "https://example.com"
    NOCODE_API_KEY: str = ""

    # Airtable (optional; used for bookings/tickets and tool_call events)
    AIRTABLE_API_KEY: str = ""
    AIRTABLE_BASE_ID: str = ""
    AIRTABLE_TICKETS_TABLE: str = ""
    AIRTABLE_BOOKINGS_TABLE: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings(  # type: ignore
        APP_VERSION="1.0.0"
    )


app_settings = get_settings()
