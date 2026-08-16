import json
import threading
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.actions.api import dispatch_action
from app.actions.models import ActionExecution
from app.candidates.discovery import record_discovery
from app.candidates.models import Candidate, DiscoveryHuntMatch
from app.hunts import sourcing_jobs
from app.hunts.models import HuntCandidate, TalentHunt
from app.infrastructure.db import Base
from app.jobs.models import BackgroundJob
from app.jobs.runner import start_profile_enrichment


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'job-controls.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.actions.approvals.SessionFactory", factory)
    monkeypatch.setattr("app.actions.locks.SessionFactory", factory)


def _wait_until(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for background state.")


def test_job_list_and_get_are_bounded_and_hide_launch_payload(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        db.add_all(
            [
                BackgroundJob(
                    id="running001",
                    kind="sourcing",
                    status="running",
                    label="Search one",
                    message="Searching",
                    payload_json=json.dumps(
                        {"role": "Animator", "session_id": "private", "api_token": "secret"}
                    ),
                    progress_json=json.dumps({"phase": "searching"}),
                ),
                BackgroundJob(
                    id="failed001",
                    kind="profile_enrichment",
                    status="error",
                    label="Scan one",
                    message="Failed",
                    error="network failure",
                    payload_json=json.dumps({"match_id": 4}),
                    progress_json=json.dumps({"phase": "reading"}),
                ),
            ]
        )
        db.commit()

    listed = dispatch_action(
        "jobs.list",
        {"status": "all", "limit": 1},
        actor_type="agent",
        session_id="jobs-audit",
    )
    assert listed.success
    assert listed.data["count"] == 1
    assert "payload" not in listed.data["jobs"][0]

    active = dispatch_action(
        "jobs.list",
        {"status": "active"},
        actor_type="agent",
        session_id="jobs-audit",
    )
    assert active.success
    assert [item["id"] for item in active.data["jobs"]] == ["running001"]
    assert active.data["jobs"][0]["cancellable"] is True

    detail = dispatch_action(
        "jobs.get",
        {"job_id": "failed001"},
        actor_type="agent",
        session_id="jobs-audit",
    )
    assert detail.success
    assert detail.data["job"]["error"] == "network failure"
    assert detail.data["job"]["retryable"] is True
    assert "payload" not in detail.data["job"]


def test_cancel_sourcing_targets_one_job_and_rejects_late_updates(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    sourcing_jobs._cancel_events.clear()
    job_id = sourcing_jobs.start_job(hunt_id=7, hunt_title="Spine Animator")

    result = dispatch_action(
        "jobs.cancel",
        {"job_id": job_id},
        actor_type="agent",
        session_id="hunt_7",
    )
    assert result.success
    assert result.data["job_id"] == job_id
    assert result.data["job_status"] == "cancelled"
    sourcing_jobs.update_job(job_id, scanned=999, message="Late worker update")

    with factory() as db:
        row = db.get(BackgroundJob, job_id)
        assert row.status == "cancelled"
        assert row.scanned == 0
        execution = db.query(ActionExecution).filter_by(action_name="jobs.cancel").one()
        assert execution.status == "completed"
    assert sourcing_jobs.should_cancel(job_id)
    sourcing_jobs._cancel_events.clear()


def test_cancel_enrichment_before_apply_prevents_candidate_mutation(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    scan_started = threading.Event()
    release_scan = threading.Event()

    def fake_enrich(*args, **kwargs):
        scan_started.set()
        release_scan.wait(2)
        return {
            "status": "success",
            "blocked": False,
            "text": "Cancel Candidate - Spine Animator - Noida, India",
        }

    monkeypatch.setattr("app.browser.page_reader.enrich_profile_from_url", fake_enrich)
    with factory() as db:
        hunt = TalentHunt(title="Cancelable Hunt", target_role="Animator")
        db.add(hunt)
        db.commit()
        _, match = record_discovery(
            db,
            hunt_id=hunt.id,
            url="https://linkedin.com/in/cancel-before-apply",
            platform="linkedin",
            source_query="animator",
            full_name="Cancel Candidate",
            status="approved",
        )
        match_id = match.id

    started = start_profile_enrichment(
        match_id,
        actor_type="copilot",
        session_id="cancel-enrichment",
    )
    assert scan_started.wait(1)
    cancelled = dispatch_action(
        "jobs.cancel",
        {"job_id": started["job_id"]},
        actor_type="agent",
        session_id="cancel-enrichment",
    )
    assert cancelled.success
    release_scan.set()

    def worker_stopped():
        with factory() as db:
            return db.get(DiscoveryHuntMatch, match_id).status == "scan_failed"

    _wait_until(worker_stopped)
    with factory() as db:
        assert db.get(BackgroundJob, started["job_id"]).status == "cancelled"
        assert db.query(Candidate).count() == 0
        assert db.query(HuntCandidate).count() == 0


def test_enrichment_cancel_is_refused_after_apply_phase_begins(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        db.add(
            BackgroundJob(
                id="applying01",
                kind="profile_enrichment",
                status="running",
                label="Applying profile",
                message="Applying",
                payload_json=json.dumps({"match_id": 99}),
                progress_json=json.dumps({"phase": "applying"}),
            )
        )
        db.commit()

    result = dispatch_action(
        "jobs.cancel",
        {"job_id": "applying01"},
        actor_type="agent",
        session_id="jobs-audit",
    )
    assert not result.success
    assert "can no longer be cancelled safely" in result.error
    with factory() as db:
        assert db.get(BackgroundJob, "applying01").status == "running"
