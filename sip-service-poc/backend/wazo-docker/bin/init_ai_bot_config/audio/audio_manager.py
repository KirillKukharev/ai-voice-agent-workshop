"""
Audio File Manager - Manager for prebuilt audio files
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioFileManager:
    """Manager for prebuilt audio files"""

    def __init__(self) -> None:
        self.audio_files: dict[str, bytes] = {}
        self._load_audio_files()

    def get_audio(self, key: str) -> bytes | None:
        """Get audio data by key"""
        return self.audio_files.get(key)

    def _load_audio_files(self) -> None:
        """Load all prebuilt audio files"""
        audio_dir = Path(__file__).parent.parent / "audio_files"

        # Standard audio files mapping
        audio_files_mapping = {
            "fallback_not_understood": "fallback_not_understood.audio",
            "re_prompt_questions": "re_prompt_questions.audio",
            "greeting_initial": "greeting_initial.audio",
            "question_initial": "question_initial.audio",
            # Filler phrases for LLM latency reduction
            "filler_thinking": "filler_thinking_1.audio",
            "filler_checking": "filler_checking_1.audio",
            "filler_wait": "filler_wait_1.audio",
            "filler_moment": "filler_moment_1.audio",
            "filler_searching": "filler_searching_1.audio",
            "filler_answering": "filler_answering_1.audio",
            "filler_verifying": "filler_verifying_1.audio",
            "filler_preparing": "filler_preparing_1.audio",
        }

        for key, filename in audio_files_mapping.items():
            filepath = audio_dir / filename
            if filepath.exists():
                try:
                    with Path.open(filepath, "rb") as f:
                        self.audio_files[key] = f.read()
                    logger.info(f"Loaded prebuilt audio: {key}")
                except Exception as e:
                    logger.warning(f"Failed to load audio file {filepath}: {e}")
            else:
                logger.warning(f"Prebuilt audio file not found: {filepath}")

        logger.info(f"✅ AudioFileManager initialized with {len(self.audio_files)} audio files")
