"""Free neural TTS via Microsoft Edge voices (edge-tts) — no API key, no paid plan.

Much clearer than browser speechSynthesis. Needs network (Microsoft TTS endpoint)
but is free for personal/local app use. Fully offline alternatives: Kokoro / Piper later.
"""

from __future__ import annotations

import io
import logging
from typing import List, Optional

logger = logging.getLogger("talenthunt.voice.edge_tts")

# Good default English voices (neural)
DEFAULT_VOICE = "en-US-JennyNeural"
RECOMMENDED_VOICES = [
    {"id": "en-US-JennyNeural", "label": "Jenny (US · natural)"},
    {"id": "en-US-AriaNeural", "label": "Aria (US · warm)"},
    {"id": "en-US-GuyNeural", "label": "Guy (US · clear)"},
    {"id": "en-GB-SoniaNeural", "label": "Sonia (UK)"},
    {"id": "en-IN-NeerjaNeural", "label": "Neerja (India)"},
    {"id": "en-IN-PrabhatNeural", "label": "Prabhat (India)"},
]


class EdgeTTSProvider:
    """Free Edge neural TTS (no API key)."""

    def __init__(self, voice: str | None = None) -> None:
        from app.config.settings import settings

        self.voice = voice or getattr(settings, "tts_edge_voice", None) or DEFAULT_VOICE

    async def generate_speech(self, text: str, voice: str | None = None) -> bytes:
        clean = (text or "").strip()
        if not clean:
            return b""
        # Keep replies snappy for Copilot
        if len(clean) > 2500:
            clean = clean[:2500]

        try:
            import edge_tts
        except ImportError:
            logger.error("edge-tts not installed. Run: pip install edge-tts")
            return b""

        target = voice or self.voice or DEFAULT_VOICE
        try:
            communicate = edge_tts.Communicate(clean, target)
            buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    buf.write(chunk["data"])
            data = buf.getvalue()
            if not data:
                logger.warning("edge-tts returned empty audio")
            return data
        except Exception as exc:
            logger.error("edge-tts generation failed: %s", exc)
            return b""

    @staticmethod
    def recommended_voices() -> List[dict]:
        return list(RECOMMENDED_VOICES)
