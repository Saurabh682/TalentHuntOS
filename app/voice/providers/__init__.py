"""Voice Provider Wrappers for TalentHunt OS."""

from app.voice.providers.deepgram_stt import DeepgramSTTProvider
from app.voice.providers.elevenlabs_tts import ElevenLabsTTSProvider

__all__ = ["DeepgramSTTProvider", "ElevenLabsTTSProvider"]
