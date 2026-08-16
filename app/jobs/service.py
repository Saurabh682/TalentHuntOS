"""Persistence operations for asynchronous jobs."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.jobs.models import BackgroundJob

TERMINAL_STATUSES = {"done", "cancelled", "error", "interrupted"}
RETRYABLE_STATUSES = {"cancelled", "error", "interrupted"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def create_job(
    *,
    kind: str,
    label: str,
    hunt_id: int | None = None,
    hunt_title: str | None = None,
    payload: dict[str, Any] | None = None,
    attempt: int = 1,
    parent_job_id: str | None = None,
) -> str:
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    job_id = uuid.uuid4().hex[:12]
    now = _now()
    with dbinfra.SessionFactory() as db:
        row = BackgroundJob(
            id=job_id,
            kind=kind,
            status="running",
            hunt_id=hunt_id,
            hunt_title=hunt_title,
            label=label,
            message="Starting...",
            payload_json=_json(payload or {}),
            progress_json="{}",
            attempt=max(1, int(attempt)),
            parent_job_id=parent_job_id,
            started_at=now,
            heartbeat_at=now,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            message = (
                "A talent search is already running. Cancel it before starting another search."
                if kind == "sourcing"
                else f"A conflicting {kind.replace('_', ' ')} job is already running."
            )
            raise RuntimeError(message) from exc
    return job_id


def get_job_row(job_id: str) -> BackgroundJob | None:
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    with dbinfra.SessionFactory() as db:
        return db.get(BackgroundJob, job_id)


def list_job_rows(
    *,
    statuses: set[str] | None = None,
    kind: str | None = None,
    hunt_id: int | None = None,
    limit: int | None = None,
) -> list[BackgroundJob]:
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    with dbinfra.SessionFactory() as db:
        stmt = select(BackgroundJob).order_by(BackgroundJob.started_at.desc())
        if statuses:
            stmt = stmt.where(BackgroundJob.status.in_(sorted(statuses)))
        if kind:
            stmt = stmt.where(BackgroundJob.kind == kind)
        if hunt_id is not None:
            stmt = stmt.where(BackgroundJob.hunt_id == int(hunt_id))
        if limit is not None:
            stmt = stmt.limit(max(1, int(limit)))
        return list(db.scalars(stmt).all())


def get_retryable_job(job_id: str) -> dict[str, Any]:
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    with dbinfra.SessionFactory() as db:
        row = db.get(BackgroundJob, job_id)
        if not row:
            raise ValueError("Background job not found.")
        child_exists = db.scalar(
            select(
                exists().where(BackgroundJob.parent_job_id == row.id)
            )
        )
        if child_exists:
            raise ValueError(f"Job {job_id} already has a newer retry attempt.")
        if row.status not in RETRYABLE_STATUSES or not row.retryable:
            raise ValueError(f"Job {job_id} in status '{row.status}' cannot be retried.")
        return serialize_job(row)


def list_retryable_jobs(*, limit: int = 5) -> list[dict[str, Any]]:
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    child = aliased(BackgroundJob)
    with dbinfra.SessionFactory() as db:
        rows = list(
            db.scalars(
                select(BackgroundJob)
                .where(
                    BackgroundJob.status.in_(sorted(RETRYABLE_STATUSES)),
                    BackgroundJob.retryable.is_(True),
                    ~exists().where(child.parent_job_id == BackgroundJob.id),
                )
                .order_by(BackgroundJob.started_at.desc())
                .limit(max(1, int(limit)))
            ).all()
        )
        return [serialize_job(row) for row in rows]


def update_running_job(job_id: str, fields: dict[str, Any]) -> bool:
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    now = _now()
    direct = {"message", "scanned", "added", "skipped"}
    with dbinfra.SessionFactory() as db:
        row = db.get(BackgroundJob, job_id)
        if not row or row.status != "running":
            return False
        progress = _loads(row.progress_json)
        for key, value in fields.items():
            if key in direct:
                setattr(row, key, value)
            elif key not in {"id", "kind", "status", "cancel"}:
                progress[key] = value
        row.progress_json = _json(progress)
        row.heartbeat_at = now
        db.commit()
        return True


def begin_running_phase(
    job_id: str,
    phase: str,
    *,
    message: str | None = None,
) -> bool:
    """Atomically enter a worker phase only while cancellation is still allowed."""
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    now = _now()
    with dbinfra.SessionFactory() as db:
        row = db.get(BackgroundJob, job_id)
        if not row or row.status != "running" or row.cancel_requested_at is not None:
            return False
        progress = _loads(row.progress_json)
        progress["phase"] = phase.strip().lower()
        row.progress_json = _json(progress)
        if message:
            row.message = message
        row.heartbeat_at = now
        db.commit()
        return True


def cancel_job_before_phases(
    job_id: str,
    *,
    message: str,
    blocked_phases: set[str],
) -> dict[str, Any]:
    """Cancel a running job unless it has entered a non-interruptible phase."""
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    now = _now()
    with dbinfra.SessionFactory() as db:
        row = db.get(BackgroundJob, job_id)
        if not row:
            return {"cancelled": False, "reason": "Background job not found."}
        if row.status != "running":
            return {
                "cancelled": False,
                "reason": f"Job {job_id} is already {row.status}.",
            }
        phase = str(_loads(row.progress_json).get("phase") or "").strip().lower()
        if phase in blocked_phases:
            return {
                "cancelled": False,
                "reason": (
                    f"Job {job_id} has entered its {phase} phase and can no longer "
                    "be cancelled safely."
                ),
                "phase": phase,
            }
        row.status = "cancelled"
        row.cancel_requested_at = now
        row.finished_at = now
        row.heartbeat_at = now
        row.message = message
        db.commit()
        return {"cancelled": True, "phase": phase or None}


def cancel_job(job_id: str, *, message: str) -> bool:
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    now = _now()
    with dbinfra.SessionFactory() as db:
        row = db.get(BackgroundJob, job_id)
        if not row or row.status != "running":
            return False
        row.status = "cancelled"
        row.cancel_requested_at = now
        row.finished_at = now
        row.heartbeat_at = now
        row.message = message
        db.commit()
        return True


def finish_job_record(
    job_id: str,
    *,
    status: str,
    message: str,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> bool:
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    now = _now()
    with dbinfra.SessionFactory() as db:
        row = db.get(BackgroundJob, job_id)
        if not row:
            return False
        if row.status == "cancelled":
            return False
        row.status = status
        row.message = message
        row.error = error
        row.result_json = _json(result) if result is not None else row.result_json
        row.finished_at = now
        row.heartbeat_at = now
        db.commit()
        return True


def mark_notified_record(job_id: str) -> None:
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    with dbinfra.SessionFactory() as db:
        row = db.get(BackgroundJob, job_id)
        if row:
            row.notified = True
            row.notified_at = _now()
            db.commit()


def recover_interrupted_jobs() -> int:
    """Make jobs owned by a previous process truthful and retryable."""
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    now = _now()
    with dbinfra.SessionFactory() as db:
        rows = list(db.scalars(select(BackgroundJob).where(BackgroundJob.status == "running")))
        for row in rows:
            row.status = "interrupted"
            row.finished_at = now
            row.heartbeat_at = now
            row.error = "Application restarted before this job completed."
            row.message = (
                "Interrupted by an application restart. Retry this background job when ready."
            )
            row.retryable = True
        db.commit()
        return len(rows)


def expire_stale_jobs(max_age_sec: float) -> int:
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    cutoff = _now() - timedelta(seconds=max(0.0, float(max_age_sec)))
    now = _now()
    with dbinfra.SessionFactory() as db:
        rows = list(
            db.scalars(
                select(BackgroundJob).where(
                    BackgroundJob.status == "running",
                    BackgroundJob.heartbeat_at <= cutoff,
                )
            )
        )
        for row in rows:
            row.status = "cancelled"
            row.cancel_requested_at = now
            row.finished_at = now
            row.message = "Cleared stale background job."
        db.commit()
        return len(rows)


def prune_finished_jobs(max_age_sec: float) -> int:
    from app.infrastructure import db as dbinfra

    dbinfra.init_db()
    cutoff = _now() - timedelta(seconds=max(0.0, float(max_age_sec)))
    with dbinfra.SessionFactory() as db:
        rows = list(
            db.scalars(
                select(BackgroundJob).where(
                    BackgroundJob.status.in_(sorted(TERMINAL_STATUSES)),
                    BackgroundJob.finished_at.is_not(None),
                    BackgroundJob.finished_at < cutoff,
                )
            )
        )
        for row in rows:
            db.delete(row)
        db.commit()
        return len(rows)


def serialize_job(row: BackgroundJob) -> dict[str, Any]:
    started = _aware(row.started_at)
    finished = _aware(row.finished_at)
    end = finished or _now()
    elapsed = max(0.0, (end - started).total_seconds()) if started else 0.0
    return {
        "id": row.id,
        "kind": row.kind,
        "hunt_id": row.hunt_id,
        "hunt_title": row.hunt_title,
        "label": row.label,
        "status": row.status,
        "message": row.message,
        "scanned": row.scanned,
        "added": row.added,
        "skipped": row.skipped,
        "payload": _loads(row.payload_json),
        "result": _loads(row.result_json),
        "attempt": row.attempt,
        "parent_job_id": row.parent_job_id,
        "retryable": row.retryable,
        "notified": row.notified,
        "started_at": started.timestamp() if started else None,
        "heartbeat_at": _aware(row.heartbeat_at).timestamp() if row.heartbeat_at else None,
        "finished_at": finished.timestamp() if finished else None,
        "elapsed_sec": round(elapsed, 1),
        "error": row.error,
        **_loads(row.progress_json),
    }
