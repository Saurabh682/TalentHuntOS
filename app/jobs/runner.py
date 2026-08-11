"""Launch and retry supported durable background workflows."""

from __future__ import annotations

import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.jobs import service as jobs


def _latest_parent_for_enrichment(match_id: int) -> dict[str, Any] | None:
    for row in jobs.list_job_rows(statuses=jobs.TERMINAL_STATUSES):
        item = jobs.serialize_job(row)
        if row.kind == "profile_enrichment" and item.get("payload", {}).get("match_id") == match_id:
            return item
    return None


def start_profile_enrichment(
    match_id: int,
    *,
    actor_type: str,
    session_id: str | None,
    parent_job_id: str | None = None,
    attempt: int | None = None,
) -> dict[str, Any]:
    """Persist and launch a deep profile scan for an approved discovery."""
    from app.candidates.models import DiscoveryHuntMatch
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        match = db.scalar(
            select(DiscoveryHuntMatch)
            .options(
                selectinload(DiscoveryHuntMatch.profile),
                selectinload(DiscoveryHuntMatch.hunt),
            )
            .where(DiscoveryHuntMatch.id == int(match_id))
        )
        if not match:
            raise ValueError("Discovery match not found.")
        if match.status not in {"approved", "scan_failed"}:
            raise ValueError(f"Discovery is {match.status}, not ready for deep scan.")
        candidate_name = match.profile.full_name or "candidate"
        hunt_id = match.hunt_id
        hunt_title = match.hunt.title

    parent = _latest_parent_for_enrichment(int(match_id)) if parent_job_id is None else None
    if parent:
        parent_job_id = parent["id"]
        attempt = int(parent.get("attempt") or 1) + 1
    job_id = jobs.create_job(
        kind="profile_enrichment",
        label=f"Deep scan - {candidate_name}",
        hunt_id=hunt_id,
        hunt_title=hunt_title,
        payload={
            "match_id": int(match_id),
            "actor_type": actor_type,
            "session_id": session_id,
        },
        attempt=attempt or 1,
        parent_job_id=parent_job_id,
    )

    def _worker() -> None:
        from app.candidates.discovery import import_approved_discovery

        jobs.update_running_job(job_id, {"message": "Reading and extracting the approved profile..."})
        try:
            result = import_approved_discovery(int(match_id), actor_type=actor_type)
            succeeded = result.get("status") == "success"
            jobs.finish_job_record(
                job_id,
                status="done" if succeeded else "error",
                message=(
                    f"Profile imported for {candidate_name}."
                    if succeeded
                    else f"Deep scan failed for {candidate_name}."
                ),
                error=None if succeeded else str(result.get("error") or "Profile scan failed"),
                result=result,
            )
        except Exception as exc:
            jobs.finish_job_record(
                job_id,
                status="error",
                message=f"Deep scan failed for {candidate_name}.",
                error=str(exc),
            )

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"enrich-discovery-{match_id}",
    ).start()
    return {
        "status": "started",
        "job_id": job_id,
        "kind": "profile_enrichment",
        "match_id": int(match_id),
        "candidate_name": candidate_name,
        "attempt": attempt or 1,
        "parent_job_id": parent_job_id,
    }


def retry_job(job_id: str) -> dict[str, Any]:
    """Replay one supported terminal job from its immutable persisted payload."""
    original = jobs.get_retryable_job(job_id)
    if original["kind"] == "sourcing":
        from app.hunts.sourcing_jobs import retry_sourcing_job

        return retry_sourcing_job(original)
    if original["kind"] == "profile_enrichment":
        payload = original["payload"]
        return start_profile_enrichment(
            int(payload["match_id"]),
            actor_type=str(payload.get("actor_type") or "copilot"),
            session_id=payload.get("session_id"),
            parent_job_id=original["id"],
            attempt=int(original.get("attempt") or 1) + 1,
        )
    raise ValueError(f"Job kind '{original['kind']}' does not support Retry yet.")


def recover_interrupted_workflows() -> int:
    """Recover durable rows and reconcile domain state owned by vanished workers."""
    recovered = jobs.recover_interrupted_jobs()
    if not recovered:
        return 0
    from app.candidates.models import DiscoveryHuntMatch
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        for item in jobs.list_retryable_jobs(limit=10_000):
            if item["status"] != "interrupted" or item["kind"] != "profile_enrichment":
                continue
            match_id = item.get("payload", {}).get("match_id")
            match = db.get(DiscoveryHuntMatch, int(match_id)) if match_id else None
            if match and match.status == "enriching":
                match.status = "scan_failed"
                match.scan_error = "The previous deep scan was interrupted. Retry when ready."
        db.commit()
    return recovered
