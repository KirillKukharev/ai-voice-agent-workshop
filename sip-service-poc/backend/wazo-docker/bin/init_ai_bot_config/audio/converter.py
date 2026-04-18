"""
Audio Converter
Converts audio between different formats (G.711, G.722, PCM)
"""

import asyncio
import atexit
import audioop
import io
import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor

import G722
import numpy as np
from config.constants import (
    PAYLOAD_TYPE_ALAW,
    PAYLOAD_TYPE_G722,
    SAMPLE_RATE_8K,
    SAMPLE_RATE_16K,
)
from pydub import AudioSegment
from pydub.effects import normalize as _normalize

logger = logging.getLogger(__name__)


class CPUPoolManager:
    """Manager for ProcessPoolExecutor with lazy initialization and proper lifecycle management."""

    _instance = None
    _pool: ProcessPoolExecutor | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_pool(cls) -> ProcessPoolExecutor:
        """Get or create the CPU pool with lazy initialization."""
        if cls._pool is None:
            cls._init_pool()
        assert cls._pool is not None, "Pool should be initialized"
        return cls._pool

    @classmethod
    def _init_pool(cls):
        """Initialize the ProcessPoolExecutor."""
        cpu_count = multiprocessing.cpu_count()
        max_workers = max(1, cpu_count - 1)
        cls._pool = ProcessPoolExecutor(max_workers=max_workers, max_tasks_per_child=100)
        logger.info(f"✅ Initialized ProcessPoolExecutor with {max_workers} workers")
        atexit.register(cls._shutdown_pool)

    @classmethod
    def _shutdown_pool(cls):
        """Shutdown the pool gracefully."""
        if cls._pool is not None:
            cls._pool.shutdown(wait=True)
            logger.info("✅ Shutdown ProcessPoolExecutor")

    @classmethod
    def shutdown(cls):
        """Explicitly shutdown the pool (for testing/cleanup)."""
        cls._shutdown_pool()
        cls._pool = None


class AudioConverter:
    """Converts audio between different codec formats"""

    @staticmethod
    def to_pcm(audio_data: bytes, payload_type: int) -> bytes:
        """
        Convert audio data to PCM16 based on payload type

        Args:
            audio_data: Audio data in source format
            payload_type: RTP payload type (0=u-law, 8=A-law, 9=G.722)

        Returns:
            PCM16 audio data
        """
        if payload_type == PAYLOAD_TYPE_ALAW:
            return audioop.alaw2lin(audio_data, 2)
        elif payload_type == PAYLOAD_TYPE_G722:
            return AudioConverter._g722_to_pcm_sync(audio_data, SAMPLE_RATE_16K)
        return audioop.ulaw2lin(audio_data, 2)

    @staticmethod
    async def to_pcm_async(audio_data: bytes, payload_type: int) -> bytes:
        """
        Asynchronously convert audio data to PCM16 based on payload type.

        Uses ProcessPoolExecutor for true CPU-bound parallelism,
        especially important for G.722 decoding which is CPU-intensive.

        Args:
            audio_data: Audio data in source format
            payload_type: RTP payload type (0=u-law, 8=A-law, 9=G.722)

        Returns:
            PCM16 audio data
        """
        loop = asyncio.get_event_loop()
        pool = CPUPoolManager.get_pool()
        return await loop.run_in_executor(pool, AudioConverter.to_pcm, audio_data, payload_type)

    @staticmethod
    async def from_pcm(pcm16_data: bytes, payload_type: int) -> bytes:
        """
        Convert PCM16 data to target format based on payload type

        Args:
            pcm16_data: PCM16 audio data
            payload_type: Target RTP payload type (0=u-law, 8=A-law, 9=G.722)
            sample_rate: Optional source sample rate

        Returns:
            Audio data in target format
        """
        if payload_type == PAYLOAD_TYPE_ALAW:
            return audioop.lin2alaw(pcm16_data, 2)
        elif payload_type == PAYLOAD_TYPE_G722:
            return await AudioConverter.pcm16_to_g722(pcm16_data, SAMPLE_RATE_16K)
        return audioop.lin2ulaw(pcm16_data, 2)

    @staticmethod
    async def pcm16_to_g722(pcm16_bytes: bytes, sample_rate: int = 16000, bitrate: int = 64000) -> bytes:
        """Convert 16-bit PCM to G.722 ADPCM raw bytes asynchronously."""
        loop = asyncio.get_event_loop()
        pool = CPUPoolManager.get_pool()
        return await loop.run_in_executor(pool, AudioConverter._pcm16_to_g722_sync, pcm16_bytes, sample_rate, bitrate)

    @staticmethod
    async def g722_to_pcm(g722_bytes: bytes, sample_rate: int = 16000) -> bytes:
        """Convert G.722 to PCM format asynchronously."""
        loop = asyncio.get_event_loop()
        pool = CPUPoolManager.get_pool()
        return await loop.run_in_executor(pool, AudioConverter._g722_to_pcm_sync, g722_bytes, sample_rate)

    @staticmethod
    def _g722_to_pcm_sync(g722_bytes: bytes, sample_rate: int = SAMPLE_RATE_16K) -> bytes:
        """Convert G.722 ADPCM to 16-bit PCM raw bytes (Linear PCM LE)."""
        try:
            decoder = G722.G722(16000, 64000)
            decoded = decoder.decode(g722_bytes)
            pcm_le = decoded.astype("<i2", copy=False)
            pcm_data = pcm_le.tobytes() if hasattr(decoded, "tobytes") else decoded

            if sample_rate != SAMPLE_RATE_16K:
                pcm_resampled, _ = audioop.ratecv(pcm_data, 2, 1, SAMPLE_RATE_16K, sample_rate, None)
                return pcm_resampled
            return pcm_data

        except Exception as e:
            logger.error(f"G.722 decoding failed: {e}")
            # Fallback to u-law
            if sample_rate != SAMPLE_RATE_8K:
                pcm8k, _ = audioop.ratecv(g722_bytes, 2, 1, sample_rate, SAMPLE_RATE_8K, None)
            else:
                pcm8k = g722_bytes
            return audioop.lin2ulaw(pcm8k, 2)

    @staticmethod
    def _pcm16_to_g722_sync(pcm16_bytes: bytes, sample_rate: int = SAMPLE_RATE_16K, bitrate: int = 64000) -> bytes:
        """Convert 16-bit PCM to raw G.722 ADPCM (16 kHz mono)."""
        try:
            # Ensure sample rate is 16kHz for G.722
            if sample_rate != SAMPLE_RATE_16K:
                pcm16k, _ = audioop.ratecv(pcm16_bytes, 2, 1, sample_rate, SAMPLE_RATE_16K, None)
            else:
                pcm16k = pcm16_bytes

            encoder = G722.G722(SAMPLE_RATE_16K, bitrate)
            pcm_array = np.frombuffer(pcm16k, dtype="<i2")
            encoded = encoder.encode(pcm_array)
            g722_bytes = encoded.tobytes() if hasattr(encoded, "tobytes") else encoded
            return g722_bytes

        except Exception as e:
            logger.error(f"G.722 encoding failed: {e}, falling back to μ-law")
            # Fallback to μ-law at 8kHz
            if sample_rate != SAMPLE_RATE_8K:
                pcm8k, _ = audioop.ratecv(pcm16_bytes, 2, 1, sample_rate, SAMPLE_RATE_8K, None)
            else:
                pcm8k = pcm16_bytes
            return audioop.lin2ulaw(pcm8k, 2)

    @staticmethod
    async def mp3_to_ulaw(mp3_bytes: bytes, sample_rate: int = SAMPLE_RATE_8K) -> bytes:
        """Convert MP3 to PCM µ-law (G.711) raw audio asynchronously."""
        loop = asyncio.get_event_loop()
        pool = CPUPoolManager.get_pool()
        return await loop.run_in_executor(pool, AudioConverter._mp3_to_ulaw_sync, mp3_bytes, sample_rate)

    @staticmethod
    async def create_g722_silence(duration_ms: int) -> bytes:
        """Create G.722 silence for specified duration in milliseconds."""
        try:
            # Create PCM silence at 16kHz, 16-bit, mono
            samples = int(SAMPLE_RATE_16K * duration_ms / 1000)
            pcm_silence = b"\x00" * (samples * 2)  # 16-bit = 2 bytes

            # Convert PCM silence to G.722
            g722_silence = await AudioConverter.pcm16_to_g722(pcm_silence, SAMPLE_RATE_16K)
            logger.info(f"✅ Created G.722 silence: {duration_ms}ms ({len(g722_silence)} bytes)")
            return g722_silence

        except Exception as e:
            logger.error(f"Failed to create G.722 silence: {e}")
            # Fallback: return simple silence pattern
            return b"\x00" * (duration_ms * 8)  # Rough estimate for G.722

    @staticmethod
    def _mp3_to_ulaw_sync(mp3_bytes: bytes, sample_rate: int = SAMPLE_RATE_8K) -> bytes:
        """Convert MP3 to raw µ-law (G.711)."""
        seg = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
        seg = seg.set_frame_rate(sample_rate).set_channels(1).set_sample_width(2)
        try:
            seg = seg.high_pass_filter(120)
            seg = seg.low_pass_filter(3400)
            seg = _normalize(seg).apply_gain(-1.0)
        except Exception:
            pass
        pcm_raw = seg.raw_data
        try:
            return audioop.lin2ulaw(pcm_raw, 2)
        except Exception:
            buf = io.BytesIO()
            seg.set_sample_width(1)
            seg.export(buf, format="mulaw", codec="pcm_mulaw")
            return buf.getvalue()

    @staticmethod
    def _normalize_sync(pcm16: bytes, target_rms: float) -> bytes:
        """Synchronous audio normalization."""
        current_rms = audioop.rms(pcm16, 2)
        gain = target_rms / (current_rms + 1e-6)
        gain = max(0.5, min(gain, 2.5))

        arr = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32)
        arr *= gain
        np.clip(arr, -30000.0, 30000.0, out=arr)
        return arr.astype(np.int16).tobytes()

    @staticmethod
    async def normalize_audio(pcm16: bytes, target_rms: float = 4000.0) -> bytes:
        """
        Asynchronous audio normalization.

        Performs level normalization of PCM16 audio data,
        performing CPU-bound operations in executor to avoid event loop blocking.

        Args:
            pcm16: PCM16 audio data (16-bit, little-endian)
            target_rms: Target RMS value for normalization (default: 4000.0)

        Returns:
            Normalized PCM16 audio data
        """
        loop = asyncio.get_event_loop()
        pool = CPUPoolManager.get_pool()
        return await loop.run_in_executor(pool, AudioConverter._normalize_sync, pcm16, target_rms)
