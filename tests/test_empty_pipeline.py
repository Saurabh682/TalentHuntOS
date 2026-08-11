from pathlib import Path


def test_pipeline_has_a_first_run_empty_state():
    source = (
        Path(__file__).parents[1] / "app" / "ui" / "pages" / "pipeline.py"
    ).read_text(encoding="utf-8")

    assert "if not hunts_list:" in source
    assert "No pipeline yet" in source
    assert "value=current_hunt_id" in source
    assert "else (hunts_list[0].id if hunts_list else 1)" not in source


def test_conversation_store_uses_configured_data_directory():
    source = (
        Path(__file__).parents[1] / "app" / "copilot" / "conversation.py"
    ).read_text(encoding="utf-8")

    assert 'STORE_FILE_PATH = DATA_DIR / "conversations_store.json"' in source
    assert '"..", "..", "data"' not in source


def test_compact_shell_keeps_navigation_and_copilot_available():
    root = Path(__file__).parents[1]
    layout = (root / "app" / "ui" / "layout.py").read_text(encoding="utf-8")
    theme = (root / "app" / "ui" / "theme.py").read_text(encoding="utf-8")

    assert "th-mobile-nav" in layout
    assert "th-mobile-open" in layout
    assert "@media (max-width: 700px)" in theme
    assert ".th-sidebar {{ display: none !important; }}" in theme
    assert ".th-copilot-panel.th-mobile-open" in theme
    assert "fonts.googleapis.com" not in theme
