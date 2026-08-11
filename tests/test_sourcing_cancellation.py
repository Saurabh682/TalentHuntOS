from app.hunts import sourcing_jobs


def test_cancel_is_immediately_terminal_and_late_updates_are_ignored():
    job_id = sourcing_jobs.start_job(hunt_id=99, hunt_title="Cancel Test")
    sourcing_jobs.update_job(job_id, message="Blocking network call")

    assert sourcing_jobs.request_cancel(job_id)
    job = sourcing_jobs.get_job(job_id)
    assert job["status"] == "cancelled"
    assert sourcing_jobs.should_cancel(job_id)
    assert all(item["id"] != job_id for item in sourcing_jobs.list_active_jobs())

    sourcing_jobs.update_job(job_id, status="running", message="Late worker update")
    job = sourcing_jobs.get_job(job_id)
    assert job["status"] == "cancelled"
    assert "cleanup" in job["message"].lower()
