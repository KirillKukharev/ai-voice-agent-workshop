"""
AVR-compatible Yandex SpeechKit adapter:
  POST /transcribe          — raw PCM (avr-asr-to-stt + Silero VAD)
  POST /text-to-speech-stream — JSON { "text": "..." } → audio/l16 stream

Auth: either YANDEX_API_KEY (Api-Key) or service account JWT → IAM (Bearer).
Docs: https://cloud.yandex.com/en/docs/speechkit/
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.iam import IamTokenProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="avr-yandex-speechkit-adapter", version="1.0.0")

FOLDER_ID = os.environ.get("FOLDER_ID", "").strip()
STT_LANG = os.environ.get("STT_LANG", "ru-RU")
STT_TOPIC = os.environ.get("STT_TOPIC", "general")
TTS_LANG = os.environ.get("TTS_LANG", "ru-RU")
TTS_VOICE = os.environ.get("TTS_VOICE", "alena")
TTS_SPEED = float(os.environ.get("TTS_SPEED", "1.35"))
TTS_SAMPLE_RATE = int(os.environ.get("TTS_SAMPLE_RATE", "8000"))

logger.info(
    "SpeechKit adapter: STT lang=%s topic=%s | TTS lang=%s voice=%s",
    STT_LANG,
    STT_TOPIC,
    TTS_LANG,
    TTS_VOICE,
)

YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY", "").strip()
SERVICE_ACCOUNT_ID = os.environ.get("SERVICE_ACCOUNT_ID", "").strip()
SA_KEY_ID = os.environ.get("SA_KEY_ID", "").strip()
PRIVATE_KEY = os.environ.get("PRIVATE_KEY", "").strip()

STT_BASE = os.environ.get(
    "YANDEX_STT_URL",
    "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize",
)
TTS_BASE = os.environ.get(
    "YANDEX_TTS_URL",
    "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
)

_iam: IamTokenProvider | None = None


def _auth_mode() -> str:
    if YANDEX_API_KEY:
        return "api_key"
    if SERVICE_ACCOUNT_ID and SA_KEY_ID and PRIVATE_KEY:
        return "iam"
    return "none"


async def _headers() -> dict[str, str]:
    if not FOLDER_ID:
        raise HTTPException(
            status_code=500,
            detail="FOLDER_ID is required",
        )
    mode = _auth_mode()
    if mode == "none":
        raise HTTPException(
            status_code=500,
            detail="Set YANDEX_API_KEY or SERVICE_ACCOUNT_ID+SA_KEY_ID+PRIVATE_KEY",
        )
    h: dict[str, str] = {"x-folder-id": FOLDER_ID}
    if mode == "api_key":
        h["Authorization"] = f"Api-Key {YANDEX_API_KEY}"
    else:
        global _iam
        if _iam is None:
            key = PRIVATE_KEY.replace("\\n", "\n")
            _iam = IamTokenProvider(SERVICE_ACCOUNT_ID, SA_KEY_ID, key)
        token = await _iam.get_token()
        h["Authorization"] = f"Bearer {token}"
    return h


def _parse_stt_text(data: dict) -> str:
    if not data:
        return ""
    if "result" in data and data["result"] is not None:
        return str(data["result"])
    # Some responses nest alternatives
    results = data.get("results") or data.get("chunks")
    if isinstance(results, list) and results:
        alt = results[0].get("alternatives") if isinstance(results[0], dict) else None
        if isinstance(alt, list) and alt:
            t = alt[0].get("text")
            if t:
                return str(t)
    return ""


@app.post("/transcribe")
async def transcribe(
    request: Request,
    x_sample_rate: Annotated[str | None, Header(alias="X-Sample-Rate")] = None,
):
    """PCM s16le mono; sample rate from avr-asr-to-stt (typically 16000 after VAD)."""
    body = await request.body()
    if not body:
        raise HTTPException(400, "Empty audio body")
    try:
        sr = int(x_sample_rate) if x_sample_rate else 16000
    except ValueError as e:
        raise HTTPException(400, f"Invalid X-Sample-Rate: {x_sample_rate}") from e

    params = {
        "topic": STT_TOPIC,
        "lang": STT_LANG,
        "format": "lpcm",
        "sampleRateHertz": str(sr),
        "folderId": FOLDER_ID,
    }
    hdrs = await _headers()
    hdrs["Content-Type"] = "application/octet-stream"

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(STT_BASE, params=params, headers=hdrs, content=body)

    if r.status_code != 200:
        logger.error("STT HTTP %s: %s", r.status_code, r.text[:2000])
        raise HTTPException(r.status_code, r.text[:2000])

    try:
        payload = r.json()
    except Exception:
        logger.error("STT non-JSON body: %s", r.text[:500])
        raise HTTPException(502, "STT returned non-JSON") from None

    text = _parse_stt_text(payload)
    logger.info("STT result len=%s", len(text))
    return {"transcription": text}


@app.post("/text-to-speech-stream")
async def text_to_speech_stream(payload: dict):
    """Same contract as avr-tts-deepgram: JSON { text }, stream raw LINEAR16."""
    text = (payload or {}).get("text")
    if not text or not str(text).strip():
        raise HTTPException(400, "text is required")

    hdrs = await _headers()
    # Yandex speech/v1/tts:synthesize принимает form-urlencoded, не JSON — иначе HTTP 400.
    form = {
        "text": str(text).strip(),
        "lang": TTS_LANG,
        "voice": TTS_VOICE,
        "speed": str(TTS_SPEED),
        "format": "lpcm",
        "sampleRateHertz": str(TTS_SAMPLE_RATE),
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(TTS_BASE, headers=hdrs, data=form)

    if r.status_code != 200:
        logger.error("TTS HTTP %s: %s", r.status_code, r.text[:2000])
        raise HTTPException(r.status_code, r.text[:2000])

    data = r.content

    async def stream():
        chunk_size = 4096
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    return StreamingResponse(
        stream(),
        media_type="audio/l16",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/health")
async def health():
    return {
        "ok": True,
        "auth": _auth_mode(),
        "folder_configured": bool(FOLDER_ID),
        "stt_lang": STT_LANG,
        "stt_topic": STT_TOPIC,
        "tts_lang": TTS_LANG,
    }
