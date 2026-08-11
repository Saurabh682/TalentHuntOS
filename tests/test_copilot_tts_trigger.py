from pathlib import Path


PANEL_SOURCE = (
    Path(__file__).parents[1] / "app" / "ui" / "panels" / "copilot_panel.py"
).read_text(encoding="utf-8")


def test_completed_copilot_replies_are_spoken_for_typed_and_voice_input():
    assert "beginCopilotSpeechResponse" in PANEL_SOURCE
    assert "queueCopilotSpeechText" in PANEL_SOURCE
    assert "queue_tts_response(accum_text)" in PANEL_SOURCE
    assert "queue_tts_response(final_resp, final=True)" in PANEL_SOURCE
    assert "if voice_originated and final_resp" not in PANEL_SOURCE


def test_copilot_tts_has_a_bounded_latency_fallback():
    assert "setTimeout(() => controller.abort(), 4500)" in PANEL_SOURCE
    assert "await speakBrowserChunk(chunk, generation)" in PANEL_SOURCE
    assert "_speechQueue" in PANEL_SOURCE


def test_copilot_composer_uses_a_multiline_writing_surface():
    assert "ui.textarea(placeholder='Ask Copilot…')" in PANEL_SOURCE
    assert "autogrow rows=2" in PANEL_SOURCE
    assert "th-copilot-composer-tool" in PANEL_SOURCE
