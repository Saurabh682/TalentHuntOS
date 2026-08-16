"""Action-kernel tests for embedded local Copilot controls."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.actions.ai_runtime import (
    RuntimeConfigureInput,
    RuntimeInstallInput,
    configure_embedded_ai_action,
)
from app.actions.context import ActionContext
from app.actions.history import undo_action
from app.actions.models import ActionHistory
from app.config.settings import settings
from app.infrastructure.db import Base


def test_install_requires_explicit_download_acknowledgement():
    with pytest.raises(ValidationError):
        RuntimeInstallInput()
    assert RuntimeInstallInput(acknowledge_download_gb=2.1).acknowledge_download_gb == 2.1


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "ai.example.com"])
def test_external_mode_rejects_non_loopback_hosts(host):
    with pytest.raises(ValidationError, match="literal loopback"):
        RuntimeConfigureInput(
            mode="external",
            autostart=False,
            external_host=host,
            external_port=1234,
        )


def test_configuration_refuses_to_race_active_runtime_job(monkeypatch):
    monkeypatch.setattr(
        "app.actions.ai_runtime._active_runtime_job_id", lambda: "job-active-1"
    )
    with pytest.raises(ValueError, match="job-active-1"):
        configure_embedded_ai_action(
            RuntimeConfigureInput(mode="lite", autostart=False),
            ActionContext.create(actor_type="system"),
        )


def test_configuration_is_recorded_and_undoable(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'embedded-actions.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr(
        "app.ai.embedded_runtime.hardware_profile",
        lambda: {"supported": True, "reason": "Supported."},
    )
    monkeypatch.setattr(
        "app.ai.embedded_runtime.public_status",
        lambda: {"status": "success", "mode": settings.local_ai_mode},
    )
    stop_calls: list[bool] = []
    monkeypatch.setattr(
        "app.ai.local_server.local_server_manager.stop",
        lambda: stop_calls.append(True) or True,
    )
    monkeypatch.setattr("app.config.preferences.save_app_preferences", lambda: None)

    previous = (
        settings.local_ai_mode,
        settings.local_ai_autostart,
        settings.llama_server_host,
        settings.llama_server_port,
    )
    try:
        result = configure_embedded_ai_action(
            RuntimeConfigureInput(mode="lite", autostart=False),
            ActionContext.create(actor_type="system"),
        )
        assert result["status"] == "updated"
        assert result["undo_days"] == 7
        assert settings.local_ai_mode == "lite"
        assert settings.local_ai_autostart is False

        with factory() as db:
            history = db.get(ActionHistory, result["action_id"])
            assert history is not None
            assert history.action_type == "configure_embedded_ai"
            undo_action(db, history.id)

        assert settings.local_ai_mode == previous[0]
        assert settings.local_ai_autostart == previous[1]
        assert settings.llama_server_host == previous[2]
        assert settings.llama_server_port == previous[3]
        assert len(stop_calls) == 2
    finally:
        (
            settings.local_ai_mode,
            settings.local_ai_autostart,
            settings.llama_server_host,
            settings.llama_server_port,
        ) = previous
