import json


def test_tts_preferences_persist_across_runtime_resets(monkeypatch, tmp_path):
    from app.config.settings import settings
    from app.voice import preferences

    path = tmp_path / "tts_preferences.json"
    monkeypatch.setattr(preferences, "PREFERENCES_PATH", path)

    preferences.save_tts_preferences(
        provider="kokoro",
        edge_voice="en-US-AriaNeural",
        kokoro_voice="af_nova",
    )
    assert json.loads(path.read_text(encoding="utf-8"))["kokoro_voice"] == "af_nova"

    settings.tts_provider = "browser"
    settings.tts_kokoro_voice = "af_heart"
    preferences.load_tts_preferences()
    assert settings.tts_provider == "kokoro"
    assert settings.tts_kokoro_voice == "af_nova"
