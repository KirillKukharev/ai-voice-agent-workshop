import asyncio
import audioop
import logging
from datetime import datetime

import grpc
from audio.converter import AudioConverter
from config.constants import OUTPUT_CODEC

from ari_handler.generated import tts_service_pb2_grpc
from ari_handler.generated.yandex.cloud.ai.tts.v3 import tts_pb2
from ari_handler.yandex_credentials_provider import YandexCredentialsProvider

logger = logging.getLogger(__name__)


class YandexSpeechSynthesizer:
    """
    Fully async Yandex Speech Synthesizer using gRPC aio.
    """

    def __init__(self, credentials_provider: YandexCredentialsProvider):
        """
        Initialize the YandexSpeechSynthesizer with the given credentials provider.

        :param credentials_provider: Instance of YandexCredentialsProvider to manage IAM tokens.
        """
        self.credentials_provider = credentials_provider
        self.iam_token = None
        self.token_expires_at: datetime | None = None
        self._iam_lock = asyncio.Lock()
        # Persistent channel/stub for lower latency
        self._channel: grpc.aio.Channel | None = None
        self._stub: tts_service_pb2_grpc.SynthesizerStub | None = None

    async def _ensure_credentials(self):
        # Cache IAM token with lock to avoid bursts
        now = datetime.now(self.token_expires_at.tzinfo) if self.token_expires_at else datetime.now()
        async with self._iam_lock:
            if not self.iam_token or not self.token_expires_at or self.token_expires_at <= now:
                logger.info("Token expired or missing, refreshing...")
                (
                    self.iam_token,
                    self.token_expires_at,
                ) = await self.credentials_provider.get_iam_token()
                logger.info(f"New token expires at: {self.token_expires_at}")

    async def _ensure_channel(self):
        if self._channel is None:
            self._channel = grpc.aio.secure_channel("tts.api.cloud.yandex.net:443", grpc.ssl_channel_credentials())
            self._stub = tts_service_pb2_grpc.SynthesizerStub(self._channel)

    async def synthesize(self, text: str, output_format: str) -> bytes:
        """
        Synthesize speech asynchronously using Yandex TTS gRPC API.

        :param text: Text to synthesize.
        :param output_format: Output format ("ulaw", "alaw", "g722", "pcm").
        :return: Audio data in specified format.
        """
        logger.info("🔥 Synthesizing text: %s", text)
        _t0_total = asyncio.get_event_loop().time()
        await self._ensure_credentials()
        await self._ensure_channel()

        target_sample_rate = 16000
        request = tts_pb2.UtteranceSynthesisRequest(  # type: ignore
            text=text,
            output_audio_spec=tts_pb2.AudioFormatOptions(  # type: ignore
                raw_audio=tts_pb2.RawAudio(  # type: ignore
                    audio_encoding=tts_pb2.RawAudio.LINEAR16_PCM,  # type: ignore
                    sample_rate_hertz=16000,
                )
            ),
            hints=[tts_pb2.Hints(voice="alena", speed=1.35)],  # type: ignore
        )

        metadata = [
            ("authorization", f"Bearer {self.iam_token}"),
            ("x-folder-id", self.credentials_provider.folder_id),
        ]

        try:
            response_stream = self._stub.UtteranceSynthesis(request, metadata=metadata) if self._stub else None
            if response_stream is None:
                raise ValueError("Response stream is None")
            audio_chunks = []
            async for response in response_stream:
                if response.HasField("audio_chunk"):
                    audio_chunks.append(response.audio_chunk.data)

            pcm16le = b"".join(audio_chunks)

            if output_format == OUTPUT_CODEC:
                if target_sample_rate != 16000:
                    pcm16le, _ = audioop.ratecv(pcm16le, 2, 1, target_sample_rate, 16000, None)
                try:
                    out_bytes = await AudioConverter.pcm16_to_g722(pcm16le, 16000, 64000)
                except Exception as e:
                    logger.warning(f"G.722 conversion failed: {e}, falling back to μ-law")
                    pcm8k, _ = audioop.ratecv(pcm16le, 2, 1, 16000, 8000, None)
                    out_bytes = audioop.lin2ulaw(pcm8k, 2)
            else:  # "pcm"
                if target_sample_rate != 16000:
                    pcm16le, _ = audioop.ratecv(pcm16le, 2, 1, target_sample_rate, 16000, None)
                out_bytes = pcm16le
            _total_ms = int((asyncio.get_event_loop().time() - _t0_total) * 1000)
            logger.info(f"⏱️ TTS всего (Yandex): {_total_ms} мс")
            return out_bytes

        except grpc.aio.AioRpcError as e:
            logger.error("❌ gRPC error during synthesis: %s", e)
            raise
