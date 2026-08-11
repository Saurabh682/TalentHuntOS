from pathlib import Path


def test_orange_busy_banner_is_reserved_for_background_jobs():
    source = (
        Path(__file__).parents[1] / "app" / "ui" / "panels" / "copilot_panel.py"
    ).read_text(encoding="utf-8")

    assert 'if jobs:\n                banner.set_visibility(True)' in source
    assert 'if busy_state["chat"] or jobs:' not in source
    assert "Waiting for Copilot reply" not in source
