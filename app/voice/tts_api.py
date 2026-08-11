"""HTTP TTS endpoint for local Kokoro and Edge neural speech."""

from __future__ import annotations

import logging
import threading
import time
from urllib.parse import unquote

from fastapi import Response
from nicegui import app

logger = logging.getLogger("talenthunt.voice.tts_api")
_warmup_started = False


def _warm_selected_local_provider() -> None:
    """Load the selected local model in the background before the first reply."""
    try:
        from app.config.settings import settings
        from app.voice.preferences import load_tts_preferences
        from app.voice.providers.kokoro_tts_provider import KokoroTTSProvider

        load_tts_preferences()
        if settings.tts_provider == "kokoro" and KokoroTTSProvider.is_available():
            KokoroTTSProvider._get_engine()
            logger.info("Kokoro TTS engine warmed and ready")
    except Exception as exc:
        logger.warning("Could not warm the selected TTS provider: %s", exc)


def register_tts_routes() -> None:
    """Register /api/tts on the NiceGUI/Starlette app (idempotent)."""

    @app.get("/api/tts")
    async def api_tts(text: str = "", voice: str = "") -> Response:
        from app.config.settings import settings
        from app.voice.providers.edge_tts_provider import EdgeTTSProvider, DEFAULT_VOICE
        from app.voice.providers.kokoro_tts_provider import KokoroTTSProvider
        from app.voice.preferences import load_tts_preferences

        load_tts_preferences()
        provider_name = (settings.tts_provider or "edge").strip().lower()
        if provider_name == "browser":
            return Response(
                content=b"",
                status_code=204,
                headers={"X-TTS-Provider": provider_name},
            )

        raw = unquote(text or "").strip()
        if not raw:
            return Response(status_code=400, content=b"missing text")

        started = time.perf_counter()
        if provider_name == "kokoro":
            voice_id = (voice or settings.tts_kokoro_voice or "af_heart").strip()
            audio = await KokoroTTSProvider(voice=voice_id).generate_speech(raw, voice=voice_id)
            media_type = "audio/wav"
        else:
            provider_name = "edge"
            voice_id = (voice or settings.tts_edge_voice or DEFAULT_VOICE).strip()
            audio = await EdgeTTSProvider(voice=voice_id).generate_speech(raw, voice=voice_id)
            media_type = "audio/mpeg"
        if not audio:
            return Response(status_code=503, content=b"tts unavailable")
        return Response(
            content=audio,
            media_type=media_type,
            headers={
                "Cache-Control": "no-store",
                "X-TTS-Provider": provider_name,
                "X-TTS-Voice": voice_id,
                "Server-Timing": f'tts;dur={(time.perf_counter() - started) * 1000:.1f}',
            },
        )

    @app.get("/api/tts/voices")
    async def api_tts_voices() -> dict:
        from app.voice.providers.edge_tts_provider import EdgeTTSProvider
        from app.voice.providers.kokoro_tts_provider import KokoroTTSProvider
        from app.config.settings import settings
        from app.voice.preferences import load_tts_preferences

        load_tts_preferences()
        return {
            "provider": settings.tts_provider,
            "selected": settings.tts_kokoro_voice if settings.tts_provider == "kokoro" else settings.tts_edge_voice,
            "voices": (
                KokoroTTSProvider.recommended_voices()
                if settings.tts_provider == "kokoro"
                else EdgeTTSProvider.recommended_voices()
            ),
            "kokoro_available": KokoroTTSProvider.is_available(),
        }

    global _warmup_started
    if not _warmup_started:
        _warmup_started = True
        threading.Thread(
            target=_warm_selected_local_provider,
            daemon=True,
            name="tts-warmup",
        ).start()

    logger.info("Registered free TTS routes at /api/tts")
