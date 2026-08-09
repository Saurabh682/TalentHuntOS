"""Background sourcing job registry (progress + cancel for Copilot UI)."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}


def start_job(*, hunt_id: int, hunt_title: str, label: str = "Sourcing LinkedIn profiles") -> str:
    """Register a new cancellable job. Returns job_id."""
    job_id = uuid.uuid4().hex[:10]
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "hunt_id": hunt_id,
            "hunt_title": hunt_title,
            "label": label,
            "status": "running",  # running | done | cancelled | error
            "message": "Starting…",
            "scanned": 0,
            "added": 0,
            "skipped": 0,
            "cancel": threading.Event(),
            "started_at": time.time(),
            "finished_at": None,
            "error": None,
        }
    return job_id


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        return {k: v for k, v in job.items() if k != "cancel"}


def force_clear_running(max_age_sec: float = 0) -> int:
    """Mark running jobs cancelled so the UI never stays stuck forever.

    max_age_sec=0 clears all running jobs. Otherwise only jobs older than that.
    """
    now = time.time()
    n = 0
    with _lock:
        for job in _jobs.values():
            if job["status"] != "running":
                continue
            age = now - float(job.get("started_at") or now)
            if max_age_sec and age < max_age_sec:
                continue
            job["cancel"].set()
            job["status"] = "cancelled"
            job["finished_at"] = now
            job["message"] = "Cleared stuck/superseded job."
            n += 1
    return n


def list_active_jobs() -> List[Dict[str, Any]]:
    # Auto-expire zombies older than 25 minutes
    force_clear_running(max_age_sec=25 * 60)
    with _lock:
        out = []
        for job in _jobs.values():
            if job["status"] == "running":
                snap = {k: v for k, v in job.items() if k != "cancel"}
                out.append(snap)
        return out


def is_busy() -> bool:
    return bool(list_active_jobs())


def update_job(job_id: str, **fields: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        for k, v in fields.items():
            if k == "cancel":
                continue
            job[k] = v


def should_cancel(job_id: Optional[str]) -> bool:
    if not job_id:
        return False
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return False
        return bool(job["cancel"].is_set())


def request_cancel(job_id: str) -> bool:
    with _lock:
        job = _jobs.get(job_id)
        if not job or job["status"] != "running":
            return False
        job["cancel"].set()
        job["message"] = "Cancel requested…"
        return True


def cancel_all() -> int:
    n = 0
    with _lock:
        for job in _jobs.values():
            if job["status"] == "running":
                job["cancel"].set()
                job["message"] = "Cancel requested…"
                n += 1
    return n


def finish_job(
    job_id: str, *, status: str = "done", message: str = "", error: str | None = None
) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["status"] = status
        job["finished_at"] = time.time()
        if message:
            job["message"] = message
        if error:
            job["error"] = error


def prune_old(max_age_sec: float = 3600) -> None:
    now = time.time()
    with _lock:
        dead = [
            jid
            for jid, j in _jobs.items()
            if j["status"] != "running"
            and j.get("finished_at")
            and (now - float(j["finished_at"])) > max_age_sec
        ]
        for jid in dead:
            _jobs.pop(jid, None)
