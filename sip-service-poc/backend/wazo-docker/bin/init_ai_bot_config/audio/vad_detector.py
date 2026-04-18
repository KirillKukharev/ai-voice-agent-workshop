"""
VAD Detector
Voice Activity Detection using TEN VAD
"""

import asyncio
import logging
from collections import deque

import numpy as np
from config.constants import (
    START_VAD_THRESHOLD,
)
from ten_vad import TenVad

logger = logging.getLogger(__name__)


class VADDetector:
    """Voice Activity Detection using TEN VAD"""

    def __init__(self, threshold: float = START_VAD_THRESHOLD):
        """
        Initialize VAD Detector

        Args:
            threshold: VAD speech detection threshold (0.0-1.0)
        """
        self.hop_size = 256
        self.threshold = threshold
        self.vad = TenVad(self.hop_size, threshold)

        # Frame buffering for improved detection quality
        # Ring buffer stores recent audio frames for overlapping analysis
        self.max_buffer_samples = 512  # 32ms buffer for temporal smoothing
        self.frame_buffer: deque[np.int16] = deque(maxlen=self.max_buffer_samples)

    def is_speech(self, frame: bytes) -> bool:
        """
        Analyze audio frame for speech using TEN VAD.

        Args:
            frame: PCM audio frame (must be 10ms, 20ms, or 30ms at 16kHz)
            sample_rate: Sample rate in Hz (default: 16000)

        Returns:
            True if speech detected, False otherwise
        """
        try:
            # Convert frame to expected format for TEN VAD
            pcm_array = np.frombuffer(frame, dtype=np.int16)

            # Add frame to ring buffer for temporal smoothing
            # deque automatically manages size and removes old samples
            self.frame_buffer.extend(pcm_array)

            # Analyze with overlapping windows for better detection quality
            speech_detected = False

            # For 20ms frames, analyze multiple overlapping 16ms windows
            if len(pcm_array) == 320:  # 20ms at 16kHz
                # Check overlapping windows within the current frame
                windows = [
                    pcm_array[:256],  # 0-16ms
                    pcm_array[64:320],  # 4-20ms
                ]
            else:
                # For other frame sizes, use the current frame
                if len(pcm_array) >= self.hop_size:
                    windows = [pcm_array[: self.hop_size]]
                elif len(pcm_array) < self.hop_size:
                    # Pad short frames
                    windows = [
                        np.pad(
                            pcm_array,
                            (0, self.hop_size - len(pcm_array)),
                            mode="constant",
                        )
                    ]
                else:
                    windows = []

            # Process each window
            for window in windows:
                if len(window) == self.hop_size:
                    _, flag = self.vad.process(window)
                    if flag == 1:
                        speech_detected = True
                        break  # Early exit on speech detection

            return speech_detected

        except Exception as e:
            logger.warning(f"VAD processing failed: {e}")
            return False

    async def is_speech_async(self, frame: bytes) -> bool:
        """
        Asynchronous version of is_speech method

        Args:
            frame: PCM audio frame

        Returns:
            True if speech detected, False otherwise
        """
        # Run CPU-bound VAD processing in a thread pool
        return await asyncio.to_thread(self.is_speech, frame)
