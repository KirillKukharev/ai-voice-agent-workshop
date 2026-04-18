from fastapi import APIRouter

# Versioned API root
router = APIRouter(prefix="/v1")

# Mount speech recognition endpoints
from backend.api.v1.speech_recognition.routes import router as speech_recognition_router  # noqa: E402

router.include_router(speech_recognition_router)
