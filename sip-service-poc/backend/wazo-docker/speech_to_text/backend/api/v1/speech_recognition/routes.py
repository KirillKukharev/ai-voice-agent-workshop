import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from backend.api.v1.auth.services.token_validator import AppTokenValidator
from backend.api.v1.speech_recognition.services.voice_recognition import (
    GigaAMSpeechRecognizer,
)
from backend.settings import app_settings

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/speech_recognition",
    tags=["speech_recognition"],
)


@router.post("/recognize", dependencies=[Depends(AppTokenValidator())])
async def recognize(request: Request) -> JSONResponse:
    """Recognize speech from a single binary payload (non-stream)."""
    content_type = request.headers.get("content-type", "")
    logger.info("/recognize: model=%s, content_type=%s", app_settings.STT_MODEL, content_type)

    if "application/octet-stream" not in content_type and "audio/" not in content_type:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Expected raw audio body with content-type application/octet-stream or audio/*"},
        )

    body = await request.body()
    logger.info("/recognize: received %d bytes", len(body) if body else 0)

    recognizer = GigaAMSpeechRecognizer()

    try:
        text = await recognizer.recognize(body) or ""
        if not text.strip():
            logger.warning("LLM returned empty result")
            return JSONResponse({"text": ""})
        else:
            logger.info("/recognize: recognized='%s'", text)
            return JSONResponse({"text": text})
    except Exception as e:
        logger.error("LLM failed: %s", e)
        return JSONResponse({"text": ""})
