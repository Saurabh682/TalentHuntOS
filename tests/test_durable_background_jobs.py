from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.hunts import sourcing_jobs
from app.infrastructure.db import Base
from app.jobs.models import BackgroundJob


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'durable-jobs.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    sourcing_jobs._cancel_events.clear()


def test_sourcing_progress_and_payload_survive_process_memory_loss(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    job_id = sourcing_jobs.start_job(
        hunt_id=7,
        hunt_title="Durable Hunt",
        label="Find 25",
        payload={"role": "Animator", "target_count": 25},
    )
    sourcing_jobs.update_job(
        job_id,
        message="Scanning profiles",
        scanned=14,
        added=3,
        source_counts={"linkedin": 8, "naukri": 6},
    )

    sourcing_jobs._cancel_events.clear()
    running = sourcing_jobs.get_job(job_id)
    assert running["status"] == "running"
    assert running["payload"] == {"role": "Animator", "target_count": 25}
    assert running["scanned"] == 14
    assert running["source_counts"] == {"linkedin": 8, "naukri": 6}

    sourcing_jobs.finish_job(job_id, message="Found three profiles")
    sourcing_jobs._cancel_events.clear()
    finished = sourcing_jobs.get_job(job_id)
    assert finished["status"] == "done"
    assert finished["added"] == 3
    assert "took" in finished["message"].lower()
    with factory() as db:
        assert db.get(BackgroundJob, job_id).status == "done"


def test_restart_marks_orphaned_job_interrupted_and_releases_search_slot(
    monkeypatch, tmp_path
):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    first = sourcing_jobs.start_job(hunt_id=1, hunt_title="Interrupted")

    sourcing_jobs._cancel_events.clear()
    assert sourcing_jobs.recover_interrupted_jobs() == 1
    recovered = sourcing_jobs.get_job(first)
    assert recovered["status"] == "interrupted"
    assert recovered["retryable"] is True
    assert "restart" in recovered["message"].lower()
    assert sourcing_jobs.should_cancel(first)

    second = sourcing_jobs.start_job(hunt_id=2, hunt_title="Replacement")
    assert sourcing_jobs.get_job(second)["status"] == "running"
    assert sourcing_jobs.request_cancel(second)


def test_cancelled_durable_job_rejects_late_progress_and_completion(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    job_id = sourcing_jobs.start_job(hunt_id=9, hunt_title="Cancelled")
    assert sourcing_jobs.request_cancel(job_id)

    sourcing_jobs._cancel_events.clear()
    sourcing_jobs.update_job(job_id, status="running", scanned=99, message="Late update")
    sourcing_jobs.finish_job(job_id, status="done", message="Late completion")
    job = sourcing_jobs.get_job(job_id)
    assert job["status"] == "cancelled"
    assert job["scanned"] == 0
    assert "cleanup" in job["message"].lower()

