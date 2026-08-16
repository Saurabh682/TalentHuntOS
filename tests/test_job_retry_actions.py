import json
import threading
import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.actions.api import dispatch_action
from app.actions.models import ActionExecution  # noqa: F401 - register action tables
from app.candidates.discovery import record_discovery
from app.candidates.models import DiscoveryHuntMatch
from app.hunts.models import TalentHunt
from app.infrastructure.db import Base
from app.jobs.models import BackgroundJob
from app.jobs.runner import recover_interrupted_workflows
from app.jobs.service import get_retryable_job, list_retryable_jobs


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'job-retry.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.actions.approvals.SessionFactory", factory)
    monkeypatch.setattr("app.actions.locks.SessionFactory", factory)


def _wait_for_status(factory, job_id, expected, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with factory() as db:
            status = db.get(BackgroundJob, job_id).status
        if status == expected:
            return
        time.sleep(0.02)
    raise AssertionError(f"Job {job_id} did not reach {expected}; last status was {status}")


def test_approval_launches_durable_enrichment_job(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    started = threading.Event()
    release = threading.Event()

    def fake_import(match_id, *, actor_type, cancel_check=None, before_apply=None):
        started.set()
        release.wait(1)
        return {"status": "success", "match_id": match_id, "actor_type": actor_type}

    monkeypatch.setattr("app.candidates.discovery.import_approved_discovery", fake_import)
    with factory() as db:
        hunt = TalentHunt(title="Durable Enrichment", target_role="Animator")
        db.add(hunt)
        db.commit()
        _, match = record_discovery(
            db,
            hunt_id=hunt.id,
            url="https://linkedin.com/in/durable-enrichment",
            platform="linkedin",
            source_query="animator",
            full_name="Durable Candidate",
            status="shortlisted",
        )
        match_id = match.id

    result = dispatch_action(
        "discoveries.approve",
        {"match_id": match_id},
        actor_type="agent",
        session_id="hunt_durable",
    )
    assert result.success
    assert started.wait(1)
    job_id = result.data["job_id"]
    with factory() as db:
        job = db.get(BackgroundJob, job_id)
        assert job.kind == "profile_enrichment"
        assert job.status == "running"
        assert json.loads(job.payload_json) == {
            "match_id": match_id,
            "actor_type": "copilot",
            "session_id": "hunt_durable",
        }
    release.set()
    _wait_for_status(factory, job_id, "done")


def test_registered_retry_creates_linked_enrichment_attempt(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    completed = threading.Event()

    def fake_import(match_id, *, actor_type, cancel_check=None, before_apply=None):
        completed.set()
        return {"status": "success", "match_id": match_id}

    monkeypatch.setattr("app.candidates.discovery.import_approved_discovery", fake_import)
    now = datetime.now(timezone.utc)
    with factory() as db:
        hunt = TalentHunt(title="Retry Hunt", target_role="Animator")
        db.add(hunt)
        db.commit()
        _, match = record_discovery(
            db,
            hunt_id=hunt.id,
            url="https://linkedin.com/in/retry-candidate",
            platform="linkedin",
            source_query="animator",
            full_name="Retry Candidate",
            status="scan_failed",
        )
        original = BackgroundJob(
            id="failedjob1",
            kind="profile_enrichment",
            status="error",
            hunt_id=hunt.id,
            hunt_title=hunt.title,
            label="Deep scan - Retry Candidate",
            message="Profile scan failed.",
            payload_json=json.dumps(
                {"match_id": match.id, "actor_type": "copilot", "session_id": "hunt_retry"}
            ),
            progress_json="{}",
            error="network failure",
            attempt=1,
            retryable=True,
            started_at=now,
            heartbeat_at=now,
            finished_at=now,
        )
        db.add(original)
        db.commit()
        match_id = match.id

    result = dispatch_action(
        "jobs.retry",
        {"job_id": "failedjob1"},
        actor_type="agent",
        session_id="hunt_retry",
    )
    assert result.success
    assert completed.wait(1)
    new_job_id = result.data["job_id"]
    _wait_for_status(factory, new_job_id, "done")
    with factory() as db:
        retry = db.get(BackgroundJob, new_job_id)
        assert retry.parent_job_id == "failedjob1"
        assert retry.attempt == 2
        assert json.loads(retry.payload_json)["match_id"] == match_id


def test_only_latest_leaf_attempt_remains_retryable(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    now = datetime.now(timezone.utc)
    with factory() as db:
        db.add_all(
            [
                BackgroundJob(
                    id="install-parent",
                    kind="embedded_ai_install",
                    status="error",
                    label="Install Embedded Local Copilot",
                    message="First attempt failed.",
                    error="old failure",
                    attempt=1,
                    retryable=True,
                    started_at=now,
                    heartbeat_at=now,
                    finished_at=now,
                ),
                BackgroundJob(
                    id="install-child",
                    kind="embedded_ai_install",
                    status="error",
                    label="Install Embedded Local Copilot",
                    message="Second attempt failed.",
                    error="latest failure",
                    attempt=2,
                    parent_job_id="install-parent",
                    retryable=True,
                    started_at=now,
                    heartbeat_at=now,
                    finished_at=now,
                ),
            ]
        )
        db.commit()

    assert [item["id"] for item in list_retryable_jobs()] == ["install-child"]
    with pytest.raises(ValueError, match="newer retry attempt"):
        get_retryable_job("install-parent")


def test_successful_child_resolves_failed_parent_retry_card(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    now = datetime.now(timezone.utc)
    with factory() as db:
        db.add_all(
            [
                BackgroundJob(
                    id="failed-install",
                    kind="embedded_ai_install",
                    status="error",
                    label="Install Embedded Local Copilot",
                    message="Failed.",
                    error="temporary failure",
                    attempt=1,
                    retryable=True,
                    started_at=now,
                    heartbeat_at=now,
                    finished_at=now,
                ),
                BackgroundJob(
                    id="ready-install",
                    kind="embedded_ai_install",
                    status="done",
                    label="Install Embedded Local Copilot",
                    message="Ready.",
                    attempt=2,
                    parent_job_id="failed-install",
                    retryable=True,
                    started_at=now,
                    heartbeat_at=now,
                    finished_at=now,
                ),
            ]
        )
        db.commit()

    assert list_retryable_jobs() == []


def test_restart_reconciles_interrupted_enrichment_domain_state(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    now = datetime.now(timezone.utc)
    with factory() as db:
        hunt = TalentHunt(title="Restart Hunt", target_role="Animator")
        db.add(hunt)
        db.commit()
        _, match = record_discovery(
            db,
            hunt_id=hunt.id,
            url="https://linkedin.com/in/restart-candidate",
            platform="linkedin",
            source_query="animator",
            full_name="Restart Candidate",
            status="enriching",
        )
        db.add(
            BackgroundJob(
                id="runningjob1",
                kind="profile_enrichment",
                status="running",
                hunt_id=hunt.id,
                hunt_title=hunt.title,
                label="Deep scan - Restart Candidate",
                message="Reading profile",
                payload_json=json.dumps({"match_id": match.id}),
                progress_json="{}",
                started_at=now,
                heartbeat_at=now,
            )
        )
        db.commit()
        match_id = match.id

    assert recover_interrupted_workflows() == 1
    with factory() as db:
        assert db.get(BackgroundJob, "runningjob1").status == "interrupted"
        match = db.get(DiscoveryHuntMatch, match_id)
        assert match.status == "scan_failed"
        assert "interrupted" in match.scan_error.lower()


def test_registered_retry_replays_exact_sourcing_payload(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    completed = threading.Event()
    captured = {}

    def fake_source(hunt_id, **kwargs):
        captured.update({"hunt_id": hunt_id, **kwargs})
        from app.hunts import sourcing_jobs

        sourcing_jobs.finish_job(kwargs["job_id"], message="Retry complete")
        completed.set()
        return {"status": "complete"}

    monkeypatch.setattr("app.hunts.web_sourcing.source_candidates_for_hunt", fake_source)
    now = datetime.now(timezone.utc)
    payload = {
        "role": "Spine Animator",
        "skills": "Spine, 2D animation",
        "location": "Noida, India",
        "target_count": 25,
        "platforms": ["linkedin", "naukri"],
        "approval_required": True,
        "time_budget_sec": 180,
    }
    with factory() as db:
        hunt = TalentHunt(title="Sourcing Retry", target_role="Spine Animator")
        db.add(hunt)
        db.commit()
        db.add(
            BackgroundJob(
                id="sourcefail1",
                kind="sourcing",
                status="error",
                hunt_id=hunt.id,
                hunt_title=hunt.title,
                label="Sourcing 25 - Spine Animator",
                message="Search backend failed.",
                payload_json=json.dumps(payload),
                progress_json="{}",
                error="backend unavailable",
                attempt=1,
                retryable=True,
                started_at=now,
                heartbeat_at=now,
                finished_at=now,
            )
        )
        db.commit()
        hunt_id = hunt.id

    result = dispatch_action(
        "jobs.retry",
        {"job_id": "sourcefail1"},
        actor_type="agent",
        session_id=f"hunt_{hunt_id}",
    )
    assert result.success
    assert completed.wait(1)
    assert captured["hunt_id"] == hunt_id
    assert captured["role"] == payload["role"]
    assert captured["location"] == payload["location"]
    assert captured["platforms"] == payload["platforms"]
    assert captured["target_added"] == 25
    with factory() as db:
        retry = db.get(BackgroundJob, result.data["job_id"])
        assert retry.parent_job_id == "sourcefail1"
        assert retry.attempt == 2
        assert retry.status == "done"
