import json
import uuid

import pytest
from pydantic import ValidationError

from app.candidates.intake_service import create_intake_request, submit_intake
from app.candidates.service import create_candidate, delete_candidate
from app.config.settings import Settings
from app.infrastructure.db import SessionFactory, init_db


def test_app_rejects_non_loopback_bind_address():
    assert Settings(host="localhost").host == "localhost"
    with pytest.raises(ValidationError):
        Settings(host="0.0.0.0")


def test_web_app_is_restricted_to_canonical_port():
    assert Settings(port=8080).port == 8080
    with pytest.raises(ValidationError):
        Settings(port=8081)


def test_private_data_directory_is_not_mounted():
    from nicegui import app as nicegui_app

    import app.main as app_main  # noqa: F401

    route_paths = {getattr(route, "path", None) for route in nicegui_app.routes}
    assert "/data" not in route_paths
    assert any(path and path.startswith("/profile-snapshots") for path in route_paths)
    assert "/api/reports/{artifact_id}" in route_paths


def test_intake_request_accepts_only_one_submission():
    init_db()
    with SessionFactory() as db:
        candidate = create_candidate(
            db,
            full_name=f"Intake Security {uuid.uuid4().hex[:8]}",
            email=f"intake-security-{uuid.uuid4().hex[:8]}@example.com",
        )
        assert candidate is not None
        candidate_id = candidate.id
        request = create_intake_request(db, candidate_id)
        assert request is not None

        first, first_message = submit_intake(db, request.token, {"skills": ["Python"]})
        second, second_message = submit_intake(db, request.token, {"skills": ["Rust"]})

        assert first is not None
        assert first_message == "ok"
        assert second is None
        assert "already submitted" in second_message.lower()
        assert delete_candidate(db, candidate_id)


def test_sensitive_copilot_tools_default_to_preview():
    from app.actions.api import ensure_core_actions_registered
    from app.actions.registry import get_action
    from app.copilot.mgmt_tools import apply_intake_submission, disconnect_site

    apply_result = json.loads(apply_intake_submission.invoke({"submission_id": "123"}))
    disconnect_result = json.loads(
        disconnect_site.invoke({"platform": "linkedin", "confirm": True})
    )

    assert apply_result["status"] == "preview"
    assert disconnect_result["status"] == "error"
    assert "trusted preview" in disconnect_result["error"]
    ensure_core_actions_registered()
    assert get_action("sites.disconnect").requires_approval is True


def test_connection_status_initializes_all_database_models(monkeypatch):
    from app.browser import session_auth

    initialized = []
    monkeypatch.setattr("app.infrastructure.db.init_db", lambda: initialized.append(True))
    monkeypatch.setattr("app.communications.service.list_browser_sessions", lambda db: [])

    result = session_auth.get_platform_connection_status()

    assert initialized == [True]
    assert {item["platform"] for item in result} == {
        "linkedin",
        "naukri",
        "github",
        "indeed",
    }
