"""Persistent local application preferences with encrypted credential fields."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from app.config.settings import DATA_DIR, settings
from app.infrastructure.secret_box import open_secret, seal

PREFERENCES_PATH = DATA_DIR / "app_preferences.json"
_LOCK = threading.Lock()
_PLAIN_FIELDS = (
    "llama_server_host",
    "llama_server_port",
    "enable_local_ai",
    "local_ai_mode",
    "local_ai_autostart",
)
_SECRET_FIELDS = (
    "gemini_api_key",
    "openai_api_key",
    "anthropic_api_key",
    "deepgram_api_key",
    "elevenlabs_api_key",
)


def load_app_preferences() -> bool:
    """Load saved preferences into the process-wide settings object."""
    path = Path(PREFERENCES_PATH)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        plain = data.get("settings") or {}
        encrypted = data.get("secrets") or {}
        for field in _PLAIN_FIELDS:
            if field in plain:
                setattr(settings, field, plain[field])
        for field in _SECRET_FIELDS:
            if field in encrypted:
                setattr(settings, field, open_secret(encrypted[field]))
        return True
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def save_app_preferences() -> Path:
    """Atomically persist non-secret settings and encrypted credentials."""
    path = Path(PREFERENCES_PATH)
    payload = {
        "version": 1,
        "settings": {field: getattr(settings, field) for field in _PLAIN_FIELDS},
        "secrets": {field: seal(getattr(settings, field) or "") for field in _SECRET_FIELDS},
    }
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        pending = path.with_suffix(path.suffix + ".tmp")
        pending.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        pending.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return path
