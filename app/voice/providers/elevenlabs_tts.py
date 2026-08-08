"""ElevenLabs Text-to-Speech provider wrapper for TalentHunt OS."""

import logging
import httpx
from app.config.settings import settings

logger = logging.getLogger("talenthunt.voice.elevenlabs")


class ElevenLabsTTSProvider:
    """Wrapper for ElevenLabs Text-to-Speech API."""

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        model_id: str = "eleven_turbo_v2_5"
    ) -> None:
        self.api_key = api_key or settings.elevenlabs_api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.base_url = "https://api.elevenlabs.io/v1/text-to-speech"
        self._client = httpx.AsyncClient(timeout=20.0)

    async def generate_speech(self, text: str, voice_id: str | None = None) -> bytes:
        """Convert text to speech audio bytes (MP3 format)."""
        if not self.api_key:
            logger.warning("ELEVENLABS_API_KEY is not configured.")
            return b""

        target_voice = voice_id or self.voice_id
        url = f"{self.base_url}/{target_voice}?optimize_streaming_latency=3"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }

        try:
            response = await self._client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            if not response.content:
                logger.error("ElevenLabs TTS returned empty audio bytes")
            return response.content
        except Exception as exc:
            logger.error(f"ElevenLabs TTS generation failed: {exc}")
            logger.error("ElevenLabs TTS returned empty audio bytes")
            return b""
