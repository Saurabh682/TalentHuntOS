"""Durable sourcing jobs with process-local cooperative cancellation signals."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.jobs import service as jobs


_lock = threading.Lock()
_cancel_events: dict[str, threading.Event] = {}


def format_duration(seconds: Optional[float]) -> str:
    """Human-readable duration, e.g. '42s', '3m 12s', '1h 02m'."""
    if seconds is None:
        return ""
    try:
        total = max(0, int(round(float(seconds))))
    except (TypeError, ValueError):
        return ""
    if total < 60:
        return f"{total}s"
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


def _public(row) -> Dict[str, Any]:
    value = jobs.serialize_job(row)
    value["elapsed_label"] = format_duration(value.get("elapsed_sec"))
    return value


def start_job(
    *,
    hunt_id: int,
    hunt_title: str,
    label: str = "Searching profile sources",
    payload: dict[str, Any] | None = None,
    attempt: int = 1,
    parent_job_id: str | None = None,
) -> str:
    """Persist one cancellable sourcing job; reject concurrent searches atomically."""
    job_id = jobs.create_job(
        kind="sourcing",
        hunt_id=hunt_id,
        hunt_title=hunt_title,
        label=label,
        payload=payload,
        attempt=attempt,
        parent_job_id=parent_job_id,
    )
    with _lock:
        _cancel_events[job_id] = threading.Event()
    return job_id


def retry_sourcing_job(original: dict[str, Any]) -> dict[str, Any]:
    """Replay a terminal sourcing job from its stored launch parameters."""
    payload = dict(original.get("payload") or {})
    required = {"role", "location", "target_count"}
    if not required <= payload.keys():
        raise ValueError("This older sourcing job does not contain enough launch data to retry.")
    target = max(1, min(int(payload.get("target_count") or 25), 100))
    hunt_id = int(original.get("hunt_id") or 0)
    if hunt_id <= 0:
        raise ValueError("The original sourcing job has no valid Hunt ID.")
    job_id = start_job(
        hunt_id=hunt_id,
        hunt_title=original.get("hunt_title") or f"Hunt {hunt_id}",
        label=original.get("label") or f"Sourcing {target}",
        payload=payload,
        attempt=int(original.get("attempt") or 1) + 1,
        parent_job_id=original["id"],
    )

    def _worker() -> None:
        from app.hunts.web_sourcing import source_candidates_for_hunt

        try:
            source_candidates_for_hunt(
                hunt_id,
                role=str(payload.get("role") or "Professional"),
                skills=str(payload.get("skills") or ""),
                location=str(payload.get("location") or "India"),
                hunt_title=original.get("hunt_title") or f"Hunt {hunt_id}",
                max_per_query=max(6, min(12, (target // 2) + 2)),
                enrich_pages=True,
                verify_with_ai=False,
                job_id=job_id,
                target_added=target,
                approval_required=bool(payload.get("approval_required", True)),
                time_budget_sec=int(payload.get("time_budget_sec") or 180),
                platforms=payload.get("platforms") or None,
            )
        except Exception as exc:
            finish_job(job_id, status="error", message=str(exc), error=str(exc))

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"retry-source-{hunt_id}",
    ).start()
    return {
        "status": "started",
        "job_id": job_id,
        "kind": "sourcing",
        "hunt_id": hunt_id,
        "attempt": int(original.get("attempt") or 1) + 1,
        "parent_job_id": original["id"],
    }


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    row = jobs.get_job_row(job_id)
    return _public(row) if row else None


def recover_interrupted_jobs() -> int:
    """Mark work from a previous process interrupted and release its singleton slot."""
    return jobs.recover_interrupted_jobs()


def force_clear_running(max_age_sec: float = 0) -> int:
    """Cancel all running jobs, or only jobs with stale heartbeats."""
    if max_age_sec:
        active_before = {item["id"] for item in list_active_jobs(expire=False)}
        count = jobs.expire_stale_jobs(max_age_sec)
        for job_id in active_before:
            if (get_job(job_id) or {}).get("status") != "running":
                _signal_cancel(job_id)
        return count
    return cancel_all(message="Cleared stuck or superseded job.")


def list_active_jobs(*, expire: bool = True) -> List[Dict[str, Any]]:
    if expire:
        force_clear_running(max_age_sec=25 * 60)
    return [_public(row) for row in jobs.list_job_rows(statuses={"running"}) if row.kind == "sourcing"]


def list_recently_finished(since_sec: float = 120.0) -> List[Dict[str, Any]]:
    """Return recently terminal jobs for completion toasts."""
    now = datetime.now(timezone.utc).timestamp()
    out = []
    for row in jobs.list_job_rows(statuses=jobs.TERMINAL_STATUSES):
        if row.kind != "sourcing":
            continue
        item = _public(row)
        finished = item.get("finished_at")
        if finished and now - float(finished) <= since_sec:
            out.append(item)
    return out


def mark_notified(job_id: str) -> None:
    jobs.mark_notified_record(job_id)


def is_busy() -> bool:
    return bool(list_active_jobs())


def update_job(job_id: str, **fields: Any) -> None:
    jobs.update_running_job(job_id, fields)


def _signal_cancel(job_id: str) -> None:
    with _lock:
        event = _cancel_events.get(job_id)
        if event:
            event.set()


def should_cancel(job_id: Optional[str]) -> bool:
    if not job_id:
        return False
    with _lock:
        event = _cancel_events.get(job_id)
        if event and event.is_set():
            return True
    row = jobs.get_job_row(job_id)
    return bool(row and row.status in {"cancelled", "interrupted"})


def request_cancel(job_id: str) -> bool:
    _signal_cancel(job_id)
    return jobs.cancel_job(job_id, message="Cancelled. Background cleanup is finishing.")


def cancel_all(*, message: str = "Cancelled. Background cleanup is finishing.") -> int:
    count = 0
    for item in list_active_jobs(expire=False):
        _signal_cancel(item["id"])
        if jobs.cancel_job(item["id"], message=message):
            count += 1
    return count


def finish_job(
    job_id: str,
    *,
    status: str = "done",
    message: str = "",
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    current = get_job(job_id)
    if not current:
        return
    if should_cancel(job_id):
        status = "cancelled"
        message = message or "Cancelled."
    elapsed_label = format_duration(current.get("elapsed_sec"))
    base = (message or current.get("message") or "").strip()
    if "took " not in base.lower():
        base = f"{base} - took {elapsed_label}" if base else f"Finished - took {elapsed_label}"
    jobs.finish_job_record(
        job_id,
        status=status,
        message=base,
        error=error,
        result=result,
    )
    if status in jobs.TERMINAL_STATUSES:
        with _lock:
            _cancel_events.pop(job_id, None)


def prune_old(max_age_sec: float = 3600) -> None:
    jobs.prune_finished_jobs(max_age_sec)
