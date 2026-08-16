import json
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.actions.context import ActionContext
from app.actions.history import list_recent_actions, undo_action
from app.actions.sites import SiteListInput, list_connected_sites_action
from app.communications.models import BrowserSession
from app.infrastructure.db import Base, User
from app.jobs import service as jobs


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'site-actions.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.infrastructure.db.init_db", lambda: None)
    monkeypatch.setattr("app.actions.approvals.SessionFactory", factory)
    monkeypatch.setattr("app.actions.locks.SessionFactory", factory)
    monkeypatch.setattr("app.actions.tool_calls.SessionFactory", factory)


def _wait_for_job(job_id: str, statuses: set[str], timeout: float = 4.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        row = jobs.get_job_row(job_id)
        if row and row.status in statuses:
            return row
        time.sleep(0.02)
    raise AssertionError(f"Job {job_id} did not reach {sorted(statuses)}")


def test_site_status_action_never_exposes_browser_secrets(monkeypatch):
    monkeypatch.setattr(
        "app.browser.session_auth.get_platform_connection_status",
        lambda: [
            {
                "platform": "linkedin",
                "label": "LinkedIn",
                "status": "verified",
                "encrypted": True,
                "verified": True,
                "last_accessed_at": "2026-08-14T00:00:00+00:00",
                "verified_at": "2026-08-14T00:00:01+00:00",
                "verify_detail": "Opened home while authenticated.",
                "session_id": 42,
                "cookie_count": 9,
                "cookies": [{"name": "li_at", "value": "must-not-leak"}],
                "headers": {"authorization": "must-not-leak"},
            }
        ],
    )
    monkeypatch.setattr("app.browser.connection_jobs.list_active_site_jobs", lambda: {})

    result = list_connected_sites_action(SiteListInput(), ActionContext.create())
    serialized = json.dumps(result)
    assert result["sites"][0]["status"] == "verified"
    assert "must-not-leak" not in serialized
    assert "cookies" not in result["sites"][0]
    assert "headers" not in result["sites"][0]
    assert "session_id" not in result["sites"][0]
    assert "cookie_count" not in result["sites"][0]


def test_connection_jobs_are_non_blocking_exact_and_cancellable(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)

    def fake_connect(
        platform,
        *,
        timeout_sec,
        save_event,
        cancel_event,
        progress,
    ):
        progress.update(
            {
                "window_open": True,
                "login_page_loaded": True,
                "browser_channel": "chromium",
                "message": f"Waiting for {platform} login.",
            }
        )
        deadline = time.time() + 3
        while time.time() < deadline:
            if cancel_event.is_set():
                return {"status": "cancelled", "platform": platform}
            if save_event.is_set():
                return {
                    "status": "success",
                    "platform": platform,
                    "verified": True,
                    "encrypted": True,
                    "session_id": 88,
                    "cookie_count": 7,
                }
            time.sleep(0.01)
        return {"status": "timeout", "error": "test timeout"}

    monkeypatch.setattr("app.browser.session_auth.interactive_connect", fake_connect)
    from app.browser.connection_jobs import request_save, start_site_connection
    from app.jobs.runner import cancel_job

    started_at = time.perf_counter()
    started = start_site_connection(
        "linkedin",
        actor_type="copilot",
        session_id="site-test",
        timeout_sec=60,
    )
    assert time.perf_counter() - started_at < 0.5
    job_id = started["job_id"]

    deadline = time.time() + 3
    while time.time() < deadline:
        item = jobs.serialize_job(jobs.get_job_row(job_id))
        if item.get("ready_for_save"):
            break
        time.sleep(0.02)
    else:
        raise AssertionError("Connection job never became ready for Save")

    saved = request_save(job_id)
    assert saved["status"] == "save_requested"
    finished = _wait_for_job(job_id, {"done"})
    assert finished.message == "LinkedIn login verified and encrypted locally."

    from app.actions.recruiting import JobIdInput, get_background_job_action

    public = get_background_job_action(JobIdInput(job_id=job_id), ActionContext.create())
    assert "payload" not in public["job"]
    assert "result" not in public["job"]
    assert "cookie" not in json.dumps(public).lower()

    cancel_started = start_site_connection(
        "naukri",
        actor_type="ui",
        session_id="site-test",
        timeout_sec=60,
    )
    cancelled = cancel_job(cancel_started["job_id"])
    assert cancelled["kind"] == "site_connect"
    assert _wait_for_job(cancel_started["job_id"], {"cancelled"}).status == "cancelled"


def test_verification_cancellation_stops_before_metadata_changes():
    from app.browser.session_auth import verify_platform_session

    result = verify_platform_session(
        "linkedin",
        headless=True,
        cancel_check=lambda: True,
    )
    assert result == {
        "status": "cancelled",
        "ok": False,
        "platform": "linkedin",
        "error": "Verification cancelled before browser access.",
    }


def test_disconnect_requires_approval_and_remains_undoable(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        admin = User(username="admin", role="admin", is_active=True)
        site_session = BrowserSession(
            platform="linkedin",
            session_name="Primary",
            cookies_json="sealed-cookie-payload",
            headers_json="sealed-header-payload",
            is_active=True,
        )
        db.add_all([admin, site_session])
        db.commit()
        admin_id = admin.id
        browser_session_id = site_session.id

    monkeypatch.setattr(
        "app.actions.sites._site_status",
        lambda platform: {
            "platform": platform,
            "label": "LinkedIn",
            "status": "verified",
            "encrypted": True,
            "verified": True,
            "active_job": None,
        },
    )
    monkeypatch.setattr("app.browser.connection_jobs.list_active_site_jobs", lambda: {})

    from app.actions.api import approve_and_dispatch, dispatch_preview

    preview = dispatch_preview(
        "sites.disconnect",
        {"platform": "linkedin"},
        actor_type="ui",
        session_id="settings-site-linkedin",
        user_id=admin_id,
    )
    assert preview.success
    assert preview.data["status"] == "pending"
    with factory() as db:
        assert db.get(BrowserSession, browser_session_id).is_active is True

    applied = approve_and_dispatch(
        int(preview.data["approval_id"]),
        user_id=admin_id,
        session_id="settings-site-linkedin",
        actor_type="ui",
    )
    assert applied.success
    assert applied.data["deactivated"] == 1
    assert "cookie" not in json.dumps(applied.data).lower()

    with factory() as db:
        assert db.get(BrowserSession, browser_session_id).is_active is False
        action = next(
            item for item in list_recent_actions(db) if item.action_type == "disconnect_site"
        )
        undo_action(db, action.id)
        assert db.get(BrowserSession, browser_session_id).is_active is True


def test_settings_and_legacy_copilot_have_no_direct_session_mutation_bypass():
    settings_source = open("app/ui/components/connect_sites.py", encoding="utf-8").read()
    legacy_source = open("app/copilot/mgmt_tools.py", encoding="utf-8").read()

    assert "app.browser.session_auth" not in settings_source
    assert '"sites.list"' in settings_source
    assert '"sites.connect"' in settings_source
    assert '"sites.reconnect"' in settings_source
    assert '"sites.verify"' in settings_source
    assert '"sites.disconnect"' in settings_source
    assert "disconnect_platform(" not in legacy_source
