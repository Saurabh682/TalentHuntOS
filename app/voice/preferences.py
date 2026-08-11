"""Persistent local preferences for Copilot speech output."""

import json

from app.config.settings import DATA_DIR, settings

PREFERENCES_PATH = DATA_DIR / "tts_preferences.json"


def load_tts_preferences() -> None:
    try:
        data = json.loads(PREFERENCES_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return
    settings.tts_provider = str(data.get("provider") or settings.tts_provider)
    settings.tts_edge_voice = str(data.get("edge_voice") or settings.tts_edge_voice)
    settings.tts_kokoro_voice = str(data.get("kokoro_voice") or settings.tts_kokoro_voice)


def save_tts_preferences(*, provider: str, edge_voice: str, kokoro_voice: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PREFERENCES_PATH.write_text(
        json.dumps(
            {"provider": provider, "edge_voice": edge_voice, "kokoro_voice": kokoro_voice},
            indent=2,
        ),
        encoding="utf-8",
    )
    settings.tts_provider = provider
    settings.tts_edge_voice = edge_voice
    settings.tts_kokoro_voice = kokoro_voice

