"""Fully local Kokoro-82M speech synthesis through ONNX Runtime."""

from __future__ import annotations

import asyncio
import io
import logging
import threading
import wave

from app.config.settings import MODELS_DIR, settings

logger = logging.getLogger("talenthunt.voice.kokoro")

DEFAULT_VOICE = "af_heart"
MODEL_PATH = MODELS_DIR / "kokoro" / "kokoro-v1.0.int8.onnx"
VOICES_PATH = MODELS_DIR / "kokoro" / "voices-v1.0.bin"
RECOMMENDED_VOICES = [
    {"id": "af_heart", "label": "Heart (US · warm)"},
    {"id": "af_bella", "label": "Bella (US · soft)"},
    {"id": "af_nova", "label": "Nova (US · clear)"},
    {"id": "af_sarah", "label": "Sarah (US · natural)"},
    {"id": "am_michael", "label": "Michael (US · natural)"},
    {"id": "am_adam", "label": "Adam (US · deep)"},
    {"id": "bf_emma", "label": "Emma (UK · natural)"},
    {"id": "bm_george", "label": "George (UK · clear)"},
]


class KokoroTTSProvider:
    _engine = None
    _lock = threading.RLock()

    def __init__(self, voice: str | None = None) -> None:
        self.voice = voice or settings.tts_kokoro_voice or DEFAULT_VOICE

    @classmethod
    def is_available(cls) -> bool:
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return False
        return MODEL_PATH.is_file() and VOICES_PATH.is_file()

    @classmethod
    def _get_engine(cls):
        if cls._engine is None:
            with cls._lock:
                if cls._engine is None:
                    from kokoro_onnx import Kokoro

                    cls._engine = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
        return cls._engine

    def _generate_wav(self, text: str, voice: str) -> bytes:
        import numpy as np

        with self._lock:
            samples, sample_rate = self._get_engine().create(
                text[:2500], voice=voice, speed=1.0, lang="en-us"
            )
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)
        return output.getvalue()

    async def generate_speech(self, text: str, voice: str | None = None) -> bytes:
        clean = (text or "").strip()
        if not clean or not self.is_available():
            return b""
        try:
            return await asyncio.to_thread(self._generate_wav, clean, voice or self.voice)
        except Exception as exc:
            logger.error("Kokoro generation failed: %s", exc)
            return b""

    @staticmethod
    def recommended_voices() -> list[dict]:
        return list(RECOMMENDED_VOICES)
