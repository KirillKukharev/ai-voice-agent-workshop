# v1 API router
from fastapi import APIRouter

from backend.api.v1 import router as v1_router  # noqa: E402

router = APIRouter()

# Mount versioned API
router.include_router(v1_router)
