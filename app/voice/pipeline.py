"""Pipecat real-time voice-to-voice orchestration pipeline for TalentHunt OS."""

import asyncio
import logging
import base64
from typing import AsyncGenerator, Any

from app.voice.providers.deepgram_stt import DeepgramSTTProvider
from app.voice.providers.elevenlabs_tts import ElevenLabsTTSProvider
from app.voice.vad import SileroVAD
from app.copilot.streaming import stream_copilot_response

logger = logging.getLogger("talenthunt.voice.pipeline")


class PipecatVoicePipeline:
    """Voice-to-Voice Real-Time Pipeline connecting VAD -> STT -> Copilot LLM -> TTS."""

    def __init__(
        self,
        stt_provider: DeepgramSTTProvider | None = None,
        tts_provider: ElevenLabsTTSProvider | None = None,
        vad_detector: SileroVAD | None = None,
    ) -> None:
        self.stt = stt_provider or DeepgramSTTProvider()
        self.tts = tts_provider or ElevenLabsTTSProvider()
        self.vad = vad_detector or SileroVAD()
        self.audio_buffer = bytearray()
        self.is_processing = False

    def append_audio_frame(self, frame_bytes: bytes) -> None:
        """Accumulate client audio bytes into processing buffer."""
        self.audio_buffer.extend(frame_bytes)
        if len(self.audio_buffer) > 10 * 1024 * 1024:
            logger.warning("Audio buffer exceeded 10MB, clearing to prevent overflow.")
            self.audio_buffer.clear()

    def clear_buffer(self) -> None:
        """Clear current audio frame buffer."""
        self.audio_buffer.clear()

    async def process_voice_input(self, audio_bytes: bytes | None = None) -> AsyncGenerator[dict[str, Any], None]:
        """Process buffered audio through STT -> Copilot Stream -> TTS.
        
        Yields pipeline event dicts:
          - {"type": "stt_result", "text": str, "error": bool}
          - {"type": "llm_chunk", "text": str}
          - {"type": "tts_audio", "audio_b64": str}
          - {"type": "status", "state": str}
        """
        data_to_process = audio_bytes if audio_bytes is not None else bytes(self.audio_buffer)
        if not data_to_process:
            yield {"type": "status", "state": "idle", "message": "No audio data received."}
            return

        self.is_processing = True
        try:
            yield {"type": "status", "state": "transcribing"}

            # Step 0.5: Voice Activity Detection — skip silence
            has_speech, vad_confidence = self.vad.is_speech(data_to_process)
            if not has_speech:
                logger.debug(f"VAD: No speech detected (confidence={vad_confidence:.2f}), skipping STT.")
                self.clear_buffer()
                yield {"type": "status", "state": "idle", "message": "No speech detected."}
                return

            # Step 1: Speech-to-Text
            self.clear_buffer()
            user_text = await self.stt.transcribe_audio(data_to_process)

            if not user_text or (isinstance(user_text, str) and user_text.startswith("[STT Error")):
                yield {
                    "type": "stt_result",
                    "text": user_text or "[Unrecognized Audio]",
                    "error": True if isinstance(user_text, str) and user_text.startswith("[STT Error") else False
                }
                yield {"type": "status", "state": "idle"}
                return

            yield {"type": "stt_result", "text": user_text, "error": False}
            yield {"type": "status", "state": "thinking"}

            # Step 2 & 3: Copilot LLM streaming + TTS generation
            full_response_text = ""
            async for accum_text in stream_copilot_response(user_text):
                full_response_text = accum_text
                yield {"type": "llm_chunk", "text": accum_text}

            yield {"type": "status", "state": "speaking"}

            # Step 4: ElevenLabs TTS output for complete response
            if full_response_text:
                audio_response = await self.tts.generate_speech(full_response_text)
                if audio_response:
                    audio_b64 = base64.b64encode(audio_response).decode("utf-8")
                    yield {"type": "tts_audio", "audio_b64": audio_b64}

            yield {"type": "status", "state": "idle"}
        finally:
            self.is_processing = False
