"""Durable execution tests for embedded AI installation jobs."""

from __future__ import annotations

import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai import embedded_jobs
from app.infrastructure.db import Base
from app.jobs import service as jobs


def _job_factory(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'embedded-jobs.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    return factory


def _wait_for_terminal(job_id: str, timeout: float = 3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = jobs.get_job_row(job_id)
        if row and row.status != "running":
            return row
        time.sleep(0.02)
    raise AssertionError(f"Job {job_id} did not finish in time.")


def test_install_runs_in_durable_job_and_records_verified_result(monkeypatch, tmp_path):
    _job_factory(monkeypatch, tmp_path)
    monkeypatch.setattr(
        embedded_jobs,
        "hardware_profile",
        lambda: {"supported": True, "reason": "Supported."},
    )

    def fake_install(*, progress, cancel_check):
        progress(
            {
                "phase": "downloading_model",
                "bytes_completed": 5,
                "total_bytes": 10,
                "percent": 50.0,
            }
        )
        assert cancel_check() is False
        return {"runtime_verified": True, "model_verified": True}

    monkeypatch.setattr(embedded_jobs, "install_embedded_components", fake_install)
    monkeypatch.setattr(embedded_jobs.local_server_manager, "start", lambda **kwargs: True)
    monkeypatch.setattr(
        embedded_jobs,
        "public_status",
        lambda: {"server": {"status": "running"}, "mode": "standard"},
    )

    started = embedded_jobs.start_embedded_ai_install(
        actor_type="system", session_id="embedded-job-test"
    )
    row = _wait_for_terminal(started["job_id"])
    serialized = jobs.serialize_job(row)
    assert serialized["status"] == "done"
    assert serialized["result"] == {
        "runtime_verified": True,
        "model_verified": True,
        "server_status": "running",
        "mode": "standard",
    }
    assert serialized["payload"]["session_id"] == "embedded-job-test"


def test_install_cancellation_is_terminal_and_retains_retryability(monkeypatch, tmp_path):
    _job_factory(monkeypatch, tmp_path)
    monkeypatch.setattr(
        embedded_jobs,
        "hardware_profile",
        lambda: {"supported": True, "reason": "Supported."},
    )

    def wait_for_cancel(*, progress, cancel_check):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if cancel_check():
                raise embedded_jobs.DownloadCancelled("cancelled")
            time.sleep(0.01)
        raise AssertionError("Cancellation was not observed by the worker.")

    monkeypatch.setattr(embedded_jobs, "install_embedded_components", wait_for_cancel)
    started = embedded_jobs.start_embedded_ai_install(
        actor_type="system", session_id="embedded-cancel-test"
    )
    result = embedded_jobs.cancel_embedded_ai_job(started["job_id"])
    assert result["status"] == "cancelled"
    row = _wait_for_terminal(started["job_id"])
    assert row.status == "cancelled"
    assert row.retryable is True
