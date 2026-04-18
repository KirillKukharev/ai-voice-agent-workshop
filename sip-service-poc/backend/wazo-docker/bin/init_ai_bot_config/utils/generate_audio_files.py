"""
Audio File Generation Script
Generates audio files for standard replies of the bot instead of realtime speech synthesis.
This will allow sending ready audio files to the queue instead of synthesizing on the fly.
"""

import asyncio
import json
import logging
import os
import struct
import sys
from pathlib import Path

# Import speech synthesis components
from ari_handler.yandex_credentials_provider import YandexCredentialsProvider
from ari_handler.yandex_speech_synthesizer import YandexSpeechSynthesizer

# Import utilities
from config.constants import OUTPUT_CODEC
from config.models import CodecType
from config.settings import app_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def create_wav_header(
    pcm_data: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
    bits_per_sample: int = 16,
) -> bytes:
    """
    Create WAV file header for PCM data.

    :param pcm_data: Raw PCM audio data
    :param sample_rate: Sample rate (Hz)
    :param channels: Number of channels (1 = mono, 2 = stereo)
    :param bits_per_sample: Bits per sample (8, 16, 24, 32)
    :return: WAV header bytes
    """

    # Calculate sizes
    data_size = len(pcm_data)
    block_align = channels * (bits_per_sample // 8)
    byte_rate = sample_rate * block_align

    # WAV header structure
    # RIFF chunk
    riff_chunk_id = b"RIFF"
    riff_chunk_size = 36 + data_size  # 36 = size of header minus RIFF/FMT/data chunks
    riff_format = b"WAVE"

    # Format chunk
    fmt_chunk_id = b"fmt "
    fmt_chunk_size = 16
    audio_format = 1  # PCM
    num_channels = channels
    sample_rate_val = sample_rate
    byte_rate_val = byte_rate
    block_align_val = block_align
    bits_per_sample_val = bits_per_sample

    # Data chunk
    data_chunk_id = b"data"
    data_chunk_size = data_size

    # Pack header
    header = struct.pack("<4sI4s", riff_chunk_id, riff_chunk_size, riff_format)
    header += struct.pack(
        "<4sIHHIIHH",
        fmt_chunk_id,
        fmt_chunk_size,
        audio_format,
        num_channels,
        sample_rate_val,
        byte_rate_val,
        block_align_val,
        bits_per_sample_val,
    )
    header += struct.pack("<4sI", data_chunk_id, data_chunk_size)

    return header


def load_environment_from_files():
    """Load environment variables from .env files"""
    env_file = app_settings.Config.env_file

    if Path(env_file).exists():
        logger.info(f"Loading environment from: {env_file}")
        try:
            with Path.open(env_file, encoding="utf-8") as f:
                content = f.read()

            # Process multiline values properly
            lines = content.split("\n")
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if not line or line.startswith("#"):
                    i += 1
                    continue

                if "=" in line:
                    key, value_part = line.split("=", 1)
                    key = key.strip()
                    value = value_part.strip()

                    # Handle multiline values (starting with quote)
                    if value.startswith('"') and not value.endswith('"'):
                        # Collect multiline value
                        full_value = value
                        i += 1
                        while i < len(lines):
                            next_line = lines[i]
                            full_value += "\n" + next_line
                            if next_line.strip().endswith('"'):
                                break
                            i += 1
                        value = full_value

                        # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]

                    # Convert escaped newlines
                    value = value.replace("\\n", "\n")

                    os.environ[key] = value

                i += 1

        except Exception as e:
            logger.error(f"Failed to load environment from {env_file}: {e}")
    else:
        logger.error(f"Environment file not found: {env_file}")


class AudioFileGenerator:
    """Generate audiofiles from text"""

    def __init__(self):
        self.speech_synthesizer = None
        self.output_dir = Path(__file__).parent.parent / "audio_files"
        self.output_dir.mkdir(exist_ok=True)

    async def initialize_synthesizer(self):
        """Initialize speech synthesizer"""
        try:
            logger.info("🔊 Initializing Yandex speech synthesizer...")
            credentials_provider = YandexCredentialsProvider()
            self.speech_synthesizer = YandexSpeechSynthesizer(credentials_provider)
            logger.info("✅ Speech synthesizer initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize speech synthesizer: {e}")
            raise

    async def generate_audio_file(self, text: str, filename: str) -> str:
        """Generate audio file from text and save it"""
        try:
            logger.info(f"Generating audio for: '{text}'")

            # Synthesize audio in the same format as used in the main service (G722)
            audio_data = await self.speech_synthesizer.synthesize(
                text,
                output_format=CodecType.G722,
            )

            if not audio_data:
                raise ValueError(f"No audio data generated for text: {text}")

            # Saved raw audio data in the format for RTP (G722)
            # These data can be directly sent to call_manager.play_next()
            filepath = self.output_dir / filename
            with Path.open(filepath, "wb") as f:
                f.write(audio_data)

            logger.info(f"💾 Raw audio data saved to: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"❌ Failed to generate audio for '{text}': {e}")
            raise

    async def generate_standard_replies(self):
        """Generate audio files for standard replies"""

        # Standard replies
        replies = [
            {
                "text": "Я вас не поняла, пожалуйста повторите.",
                "filename": "fallback_not_understood.audio",
                "description": "Реплика, когда не распознана речь пользователя",
            },
            {
                "text": "Остались ли у вас ещё вопросы?",
                "filename": "re_prompt_questions.audio",
                "description": "Повторный вопрос после паузы в разговоре",
            },
            {
                "text": "Добрый день! Чем я могу вам помочь?",
                "filename": "greeting_initial.audio",
                "description": "Приветственное сообщение при начале разговора",
            },
            {
                "text": "Желаете что-нибудь спросить или узнать?",
                "filename": "question_initial.audio",
                "description": "Первый вопрос пользователю через 5 секунд после начала разговора",
            },
            # Filler phrases for LLM response delay reduction
            {
                "text": "Уточняю информацию.",
                "filename": "filler_thinking_1.audio",
                "description": "Филлер: показываем что обрабатываем запрос",
            },
            {
                "text": "Сейчас проверю.",
                "filename": "filler_checking_1.audio",
                "description": "Филлер: проверка информации",
            },
            {
                "text": "Подождите пожалуйста.",
                "filename": "filler_wait_1.audio",
                "description": "Филлер: вежливая просьба подождать",
            },
            {
                "text": "Один момент.",
                "filename": "filler_moment_1.audio",
                "description": "Филлер: короткое ожидание",
            },
            {
                "text": "Ищу ответ.",
                "filename": "filler_searching_1.audio",
                "description": "Филлер: поиск информации",
            },
            {
                "text": "Сейчас отвечу.",
                "filename": "filler_answering_1.audio",
                "description": "Филлер: скоро будет ответ",
            },
            {
                "text": "Проверяю данные.",
                "filename": "filler_verifying_1.audio",
                "description": "Филлер: валидация информации",
            },
            {
                "text": "Подготавливаю ответ.",
                "filename": "filler_preparing_1.audio",
                "description": "Филлер: финальная подготовка",
            },
        ]

        results = []
        for reply in replies:
            try:
                filepath = await self.generate_audio_file(reply["text"], reply["filename"])
                results.append(
                    {
                        "text": reply["text"],
                        "filename": reply["filename"],
                        "filepath": filepath,
                        "description": reply["description"],
                        "success": True,
                    }
                )
            except Exception as e:
                logger.error(f"Failed to generate {reply['filename']}: {e}")
                results.append(
                    {
                        "text": reply["text"],
                        "filename": reply["filename"],
                        "description": reply["description"],
                        "success": False,
                        "error": str(e),
                    }
                )

        return results

    def save_metadata(self, results: list):
        """Save metadata about generated files"""
        metadata = {
            "generated_at": asyncio.get_event_loop().time(),
            "codec": OUTPUT_CODEC,
            "files": results,
            "usage_note": "Use .audio files for RTP playback, .wav files for testing",
        }

        metadata_path = self.output_dir / "audio_metadata.json"
        with Path.open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)


async def main():
    """Main function"""
    logger.info("Starting audio file generation")

    # Load environment variables from .env files
    load_environment_from_files()

    generator = AudioFileGenerator()

    try:
        # Initialize synthesizer
        await generator.initialize_synthesizer()

        # Generate standard replies
        results = await generator.generate_standard_replies()

        # Save metadata
        generator.save_metadata(results)

        # Display results
        logger.info("Generation completed!")
        successful = sum(1 for r in results if r["success"])
        total = len(results)
        logger.info(f"Successfully generated: {successful}/{total} files")

        for result in results:
            if result["success"]:
                logger.info(f"Successfully generated: {result['filename']}: {result['text']}")
            else:
                logger.error(f"Failed to generate: {result['filename']}: {result['error']}")

    except Exception as e:
        logger.error(f"Audio generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
