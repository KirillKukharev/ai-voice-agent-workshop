#!/usr/bin/env python3
"""
Скрипт для мониторинга и диагностики Voice Activity Detection (VAD)
Помогает настроить параметры VAD для оптимальной работы
"""

import asyncio
import audioop
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import List

import numpy as np

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class VADStats:
    """Статистика работы VAD"""

    total_frames: int = 0
    silence_frames: int = 0
    speech_frames: int = 0
    speech_ratio: float = 0.0
    false_positives: int = 0
    false_negatives: int = 0


class VADMonitor:
    """Монитор для анализа работы WebRTC VAD"""

    def __init__(self, window_size: int = 1000):
        self.stats = VADStats()
        self.speech_history = deque(maxlen=window_size)
        self.silence_history = deque(maxlen=window_size)
        self.spectral_history = deque(maxlen=window_size)

    def update_stats(self, is_silence: bool, spectral_centroid: float = 0):
        """Обновляет статистику"""
        self.stats.total_frames += 1

        if is_silence:
            self.stats.silence_frames += 1
            self.silence_history.append(1)
        else:
            self.stats.speech_frames += 1
            self.silence_history.append(0)

        self.spectral_history.append(spectral_centroid)

        # Обновляем соотношение речи и тишины
        if self.stats.total_frames > 0:
            self.stats.speech_ratio = self.stats.speech_frames / self.stats.total_frames

    def get_recommendations(self) -> List[str]:
        """Возвращает рекомендации по настройке VAD"""
        recommendations = []

        # Анализ соотношения речи и тишины
        if self.stats.total_frames > 0:
            silence_ratio = self.stats.silence_frames / self.stats.total_frames
            if silence_ratio > 0.9:
                recommendations.append(
                    "⚠️ Слишком много тишины. Возможно, VAD слишком агрессивный."
                )
            elif silence_ratio < 0.1:
                recommendations.append(
                    "⚠️ Слишком мало тишины. Возможно, VAD недостаточно агрессивный."
                )
            else:
                recommendations.append("✅ Хорошее соотношение речи и тишины.")

        # Анализ спектральных характеристик
        if len(self.spectral_history) > 10:
            avg_spectral = np.mean(self.spectral_history)
            if avg_spectral < 500:
                recommendations.append(
                    "⚠️ Низкий спектральный центроид. Возможно, проблемы с микрофоном."
                )
            elif avg_spectral > 3000:
                recommendations.append(
                    "⚠️ Высокий спектральный центроид. Возможно, много высокочастотного шума."
                )

        return recommendations

    def print_stats(self):
        """Выводит текущую статистику"""
        print("\n📊 VAD Статистика:")
        print(f"   Всего фреймов: {self.stats.total_frames}")
        print(f"   Фреймы речи: {self.stats.speech_frames}")
        print(f"   Фреймы тишины: {self.stats.silence_frames}")
        print(f"   Соотношение речи: {self.stats.speech_ratio:.2f}")

        if self.stats.total_frames > 0:
            silence_ratio = self.stats.silence_frames / self.stats.total_frames
            print(f"   Соотношение тишины: {silence_ratio:.2f}")

        # Рекомендации
        recommendations = self.get_recommendations()
        if recommendations:
            print("\n💡 Рекомендации:")
            for rec in recommendations:
                print(f"   {rec}")

        # Рекомендуемые настройки
        if self.stats.total_frames > 100:
            print("\n⚙️ Рекомендуемые настройки:")
            if silence_ratio > 0.8:
                print("   Уменьшите WEBRTC_VAD_AGGRESSIVENESS (текущее значение: 2)")
            elif silence_ratio < 0.3:
                print("   Увеличьте WEBRTC_VAD_AGGRESSIVENESS (текущее значение: 2)")
            else:
                print("   Текущие настройки WEBRTC_VAD_AGGRESSIVENESS=2 оптимальны")


def analyze_audio_file(file_path: str, monitor: VADMonitor):
    """Анализирует аудиофайл с помощью WebRTC VAD"""
    try:
        import webrtcvad

        vad = webrtcvad.Vad(2)  # Агрессивность 2
        frame_size_ms = 20
        frame_size_bytes = int(8000 / 1000 * frame_size_ms) * 2  # 16-bit

        with open(file_path, "rb") as f:
            audio_data = f.read()

        # Конвертируем u-law в PCM если нужно
        if audio_data.startswith(b"\x00\x00\x00"):
            # Предполагаем, что это PCM
            pcm_data = audio_data
        else:
            # Предполагаем, что это u-law
            pcm_data = audioop.ulaw2lin(audio_data, 2)

        # Анализируем каждый фрейм
        for i in range(0, len(pcm_data), frame_size_bytes):
            frame = pcm_data[i : i + frame_size_bytes]
            if len(frame) == frame_size_bytes:
                try:
                    is_speech = vad.is_speech(frame, 8000)
                    is_silence = not is_speech

                    # Простой спектральный анализ для дополнительной информации
                    amplitudes = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
                    if len(amplitudes) > 0:
                        fft = np.fft.fft(amplitudes)
                        magnitude = np.abs(fft)
                        freqs = np.fft.fftfreq(len(amplitudes), 1 / 8000)
                        spectral_centroid = np.sum(freqs * magnitude) / np.sum(
                            magnitude
                        )
                    else:
                        spectral_centroid = 0

                    monitor.update_stats(is_silence, spectral_centroid)

                except Exception as e:
                    logger.warning(f"Frame analysis error: {e}")
                    continue

        monitor.print_stats()

    except ImportError:
        logger.error("webrtcvad not available. Install with: pip install webrtcvad")
    except Exception as e:
        logger.error(f"Audio analysis error: {e}")


def analyze_live_audio(monitor: VADMonitor, duration_seconds: int = 10):
    """Анализирует живое аудио с микрофона"""
    try:
        import pyaudio
        import webrtcvad

        vad = webrtcvad.Vad(2)
        frame_size_ms = 20
        frame_size_bytes = int(8000 / 1000 * frame_size_ms) * 2

        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=8000,
            input=True,
            frames_per_buffer=frame_size_bytes,
        )

        print(f"🎤 Записываем аудио {duration_seconds} секунд...")
        start_time = time.time()

        while time.time() - start_time < duration_seconds:
            try:
                frame = stream.read(frame_size_bytes)
                is_speech = vad.is_speech(frame, 8000)
                is_silence = not is_speech

                # Простой спектральный анализ
                amplitudes = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
                if len(amplitudes) > 0:
                    fft = np.fft.fft(amplitudes)
                    magnitude = np.abs(fft)
                    freqs = np.fft.fftfreq(len(amplitudes), 1 / 8000)
                    spectral_centroid = np.sum(freqs * magnitude) / np.sum(magnitude)
                else:
                    spectral_centroid = 0

                monitor.update_stats(is_silence, spectral_centroid)

            except Exception as e:
                logger.warning(f"Live audio analysis error: {e}")
                continue

        stream.stop_stream()
        stream.close()
        p.terminate()

        monitor.print_stats()

    except ImportError:
        logger.error("pyaudio not available. Install with: pip install pyaudio")
    except Exception as e:
        logger.error(f"Live audio analysis error: {e}")


async def main():
    """Основная функция"""
    print("🎯 WebRTC VAD Monitor - Анализ без RMS вычислений")
    print("=" * 50)

    monitor = VADMonitor()

    # Анализ аудиофайла если указан
    import sys

    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        print(f"📁 Анализируем файл: {file_path}")
        analyze_audio_file(file_path, monitor)
    else:
        # Интерактивный режим
        print("Выберите режим:")
        print("1. Анализ аудиофайла")
        print("2. Анализ живого аудио (10 секунд)")

        choice = input("Введите выбор (1 или 2): ").strip()

        if choice == "1":
            file_path = input("Введите путь к аудиофайлу: ").strip()
            if file_path:
                analyze_audio_file(file_path, monitor)
            else:
                print("Путь к файлу не указан")
        elif choice == "2":
            analyze_live_audio(monitor)
        else:
            print("Неверный выбор")


if __name__ == "__main__":
    asyncio.run(main())
