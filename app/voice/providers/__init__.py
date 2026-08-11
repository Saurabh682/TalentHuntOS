"""Voice Provider Wrappers for TalentHunt OS."""

from app.voice.providers.deepgram_stt import DeepgramSTTProvider
from app.voice.providers.elevenlabs_tts import ElevenLabsTTSProvider
from app.voice.providers.edge_tts_provider import EdgeTTSProvider
from app.voice.providers.kokoro_tts_provider import KokoroTTSProvider

__all__ = ["DeepgramSTTProvider", "ElevenLabsTTSProvider", "EdgeTTSProvider", "KokoroTTSProvider"]
