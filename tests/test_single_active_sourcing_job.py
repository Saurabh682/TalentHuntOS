import pytest

from app.hunts import sourcing_jobs


def test_only_one_sourcing_job_can_run_at_a_time():
    sourcing_jobs.force_clear_running()
    first = sourcing_jobs.start_job(hunt_id=1, hunt_title="First")
    try:
        with pytest.raises(RuntimeError, match="already running"):
            sourcing_jobs.start_job(hunt_id=2, hunt_title="Second")
        assert sourcing_jobs.get_job(first)["status"] == "running"
    finally:
        sourcing_jobs.request_cancel(first)
