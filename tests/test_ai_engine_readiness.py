import pytest

from app.ai import embedded_runtime
from app.ai.engine import AIEngine, LocalAIUnavailableError


def test_embedded_base_url_does_not_share_external_port(monkeypatch):
    monkeypatch.setattr(embedded_runtime.settings, "local_ai_mode", "standard")
    monkeypatch.setattr(embedded_runtime.settings, "embedded_ai_port", 18081)
    monkeypatch.setattr(embedded_runtime.settings, "llama_server_port", 1234)

    assert AIEngine._local_base_url() == "http://127.0.0.1:18081/v1"


def test_missing_embedded_model_fails_before_openai_client(monkeypatch):
    monkeypatch.setattr(
        embedded_runtime,
        "public_status",
        lambda: {
            "mode": "standard",
            "runtime": {"verified": True},
            "model": {"verified": False},
            "server": {"status": "stopped", "port": 18081},
            "external_endpoint": {"host": "127.0.0.1", "port": 1234},
        },
    )

    with pytest.raises(LocalAIUnavailableError, match="not installed yet"):
        AIEngine().get_llm(provider="local")
