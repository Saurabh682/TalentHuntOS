"""Deepgram Speech-to-Text provider wrapper for TalentHunt OS."""

import logging
import httpx
from app.config.settings import settings

logger = logging.getLogger("talenthunt.voice.deepgram")


class DeepgramSTTProvider:
    """Wrapper for Deepgram Speech-to-Text API."""

    def __init__(self, api_key: str | None = None, model: str = "nova-2", language: str = "en") -> None:
        self.api_key = api_key or settings.deepgram_api_key
        self.model = model
        self.language = language
        self.endpoint = "https://api.deepgram.com/v1/listen"
        self._client = httpx.AsyncClient(timeout=15.0)

    async def transcribe_audio(self, audio_data: bytes, content_type: str = "audio/wav") -> str:
        """Transcribe raw audio bytes to text using Deepgram API."""
        if not self.api_key:
            logger.warning("DEEPGRAM_API_KEY is not configured.")
            return "[STT Error: Deepgram API key missing]"

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": content_type,
        }
        params = {
            "model": self.model,
            "language": self.language,
            "smart_format": "true",
            "punctuate": "true",
        }

        try:
            response = await self._client.post(
                self.endpoint,
                params=params,
                headers=headers,
                content=audio_data
            )
            response.raise_for_status()
            result = response.json()
            
            channels = (result.get("results") or {}).get("channels", [])
            if channels and len(channels) > 0:
                alternatives = channels[0].get("alternatives", [])
                if alternatives and len(alternatives) > 0:
                    transcript = alternatives[0].get("transcript", "").strip()
                    return transcript
            return ""
        except Exception as exc:
            logger.error(f"Deepgram STT transcription failed: {exc}")
            return f"[STT Error: {exc}]"
