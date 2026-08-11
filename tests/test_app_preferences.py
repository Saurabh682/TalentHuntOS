import json

from app.config import preferences
from app.config.settings import settings


def test_app_preferences_persist_and_encrypt_credentials(monkeypatch, tmp_path):
    path = tmp_path / "app_preferences.json"
    monkeypatch.setattr(preferences, "PREFERENCES_PATH", path)
    monkeypatch.setattr(preferences, "seal", lambda value: f"sealed:{value}")
    monkeypatch.setattr(preferences, "open_secret", lambda value: value.removeprefix("sealed:"))

    monkeypatch.setattr(settings, "llama_server_host", "127.0.0.9")
    monkeypatch.setattr(settings, "llama_server_port", 4321)
    monkeypatch.setattr(settings, "enable_local_ai", False)
    monkeypatch.setattr(settings, "openai_api_key", "audit-secret")
    preferences.save_app_preferences()

    raw = path.read_text(encoding="utf-8")
    assert "audit-secret" not in json.dumps(json.loads(raw)["settings"])
    assert json.loads(raw)["secrets"]["openai_api_key"] == "sealed:audit-secret"

    settings.llama_server_host = "localhost"
    settings.llama_server_port = 1234
    settings.enable_local_ai = True
    settings.openai_api_key = ""
    assert preferences.load_app_preferences()
    assert settings.llama_server_host == "127.0.0.9"
    assert settings.llama_server_port == 4321
    assert settings.enable_local_ai is False
    assert settings.openai_api_key == "audit-secret"
