import asyncio
import logging
import warnings
from pathlib import Path

import torch
from GigaAM import gigaam

logger = logging.getLogger(__name__)

# Cache the model once per process to avoid repeated heavy loads
_GIGAAM_MODEL_SINGLETON = None


def load_gigaam_model_from_path(model_path: str, device: str | None = None) -> gigaam.GigaAMASR:
    """
    Load GigaAM model directly from local file path.

    Args:
        model_path: Path to the .ckpt file
        device: Device to load model on ('cpu', 'cuda', etc.)

    Returns:
        Loaded GigaAMASR model
    """
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    device_obj = torch.device(device)

    if not Path(model_path).exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=(FutureWarning))
        checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)

    model = gigaam.GigaAMASR(checkpoint["cfg"])

    model.load_state_dict(checkpoint["state_dict"])
    model = model.eval()

    if device_obj.type != "cpu":
        model.encoder = model.encoder.half()

    return model.to(device_obj)


def _get_gigaam_model():
    """Lazy-load and cache GigaAM ASR model. Default to RNNT for realtime."""
    global _GIGAAM_MODEL_SINGLETON
    if _GIGAAM_MODEL_SINGLETON is not None:
        return _GIGAAM_MODEL_SINGLETON

    # Determine device: use GPU if available, otherwise CPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Loading GigaAM model on device: %s", device)

    current_file = Path(__file__)
    local_model_path = current_file.parents[5] / "backend" / "model" / "v3_rnnt.ckpt"

    try:
        if Path(local_model_path).exists():
            logger.info("Found local model at %s, loading from project", local_model_path)
            _GIGAAM_MODEL_SINGLETON = load_gigaam_model_from_path(local_model_path, device=device)
        else:
            logger.info("No local model found, downloading from remote")
            _GIGAAM_MODEL_SINGLETON = gigaam.load_model("v3_rnnt", device=device)
        logger.info("Successfully loaded GigaAM model on %s", device)
    except Exception as e:
        raise e

    return _GIGAAM_MODEL_SINGLETON


class GigaAMSpeechRecognizer:
    """GigaAM recognizer with optimized in-memory processing.

    Uses numpy arrays for in-memory transcription when possible,
    falls back to temp WAV files. Optimized for low-latency speech
    recognition with minimal I/O operations.

    Note: RNNT variant is most suitable for near-realtime, but here it's
    single-shot per utterance.
    """

    def __init__(self):
        self._model = _get_gigaam_model()

    async def recognize(self, audio_data: bytes) -> str | None:
        """Recognize speech from audio data.

        Args:
            audio_data: Raw audio data (PCM16 16kHz)
        """
        try:
            try:
                result = await asyncio.to_thread(self._model.transcribe_bytes, audio_data)
            except Exception as e:
                logger.error("GigaAM transcribe_bytes failed: %s", e)
                return None

            if isinstance(result, str):
                return result.strip() or None

        except Exception as e:
            logger.error("Direct transcription error: %s", e)

        return None


def preload_models():
    """Optionally preload models at app startup to avoid first-request latency."""

    try:
        _get_gigaam_model()
        logger.info("Preloaded GigaAM model")
    except Exception as e:
        logger.warning("Failed to preload: %s", e)
