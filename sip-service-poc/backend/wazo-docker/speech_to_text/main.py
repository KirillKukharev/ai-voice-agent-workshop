import logging
from contextlib import asynccontextmanager
from importlib.metadata import distribution
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.templating import Jinja2Templates

from backend import exception_handler, settings
from backend.api.v1.speech_recognition.services.voice_recognition import preload_models
from backend.config import configure_application

configure_application()

from backend import api  # noqa E402  # pylint: disable=C0413


logger = logging.getLogger(__name__)

app_settings = settings.get_settings()

fastapi_kwargs: dict[str, Any] = {
    "title": "STT API Service",
    "description": "FastAPI app for Template API Service",
    "version": distribution("fastapi-template").version,
}

if not app_settings.APP_ENABLE_DOCS:
    fastapi_kwargs["docs_url"] = None
    fastapi_kwargs["redoc_url"] = None
    fastapi_kwargs["openapi_url"] = None


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    """Lifespan FastAPI function"""
    # Events on startup app
    try:
        preload_models()
    except Exception as e:
        logger.warning("STT preload skipped: %s", e)

    yield


app = FastAPI(lifespan=lifespan, **fastapi_kwargs)  # type: ignore

app.include_router(api.router)

app.exception_handler(HTTPException)(exception_handler.http_exception_handler)
app.exception_handler(Exception)(exception_handler.unexpected_exception_handler)
app.exception_handler(RequestValidationError)(exception_handler.unprocessable_entity_handler)

templates = Jinja2Templates(directory="frontend")


@app.get("/", include_in_schema=False)
async def proxy_app(request: Request):
    """Root App endpoint"""
    # Serve a simple JSON if template is missing to avoid 500s in API-only use
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception:
        return {"status": "ok", "service": "speech_to_text"}
