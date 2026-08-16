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

        jobs.begin_running_phase(
            job_id,
            "reading",
            message="Reading and extracting the approved profile...",
        )

        def _cancelled() -> bool:
            row = jobs.get_job_row(job_id)
            return not row or row.status != "running"

        try:
            result = import_approved_discovery(
                int(match_id),
                actor_type=actor_type,
                cancel_check=_cancelled,
                before_apply=lambda: jobs.begin_running_phase(
                    job_id,
                    "applying",
                    message="Applying extracted evidence to the candidate profile...",
                ),
            )
            succeeded = result.get("status") == "success"
            cancelled = result.get("status") == "cancelled"
            jobs.finish_job_record(
                job_id,
                status="done" if succeeded else ("cancelled" if cancelled else "error"),
                message=(
                    f"Profile imported for {candidate_name}."
                    if succeeded
                    else (
                        f"Deep scan cancelled for {candidate_name}."
                        if cancelled
                        else f"Deep scan failed for {candidate_name}."
                    )
                ),
                error=(
                    None
                    if succeeded or cancelled
                    else str(result.get("error") or "Profile scan failed")
                ),
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


def cancel_job(job_id: str) -> dict[str, Any]:
    """Cancel one supported running workflow without overstating interruption."""
    row = jobs.get_job_row(job_id)
    if not row:
        raise ValueError("Background job not found.")
    if row.status != "running":
        raise ValueError(f"Job {job_id} is already {row.status}.")
    if row.kind == "sourcing":
        from app.hunts.sourcing_jobs import request_cancel

        if not request_cancel(job_id):
            raise ValueError(f"Job {job_id} could not be cancelled.")
        return {
            "status": "cancelled",
            "job_id": job_id,
            "kind": row.kind,
            "message": "Talent search cancelled. Background cleanup is finishing.",
        }
    if row.kind == "profile_enrichment":
        outcome = jobs.cancel_job_before_phases(
            job_id,
            message="Deep scan cancelled. Approval was retained for Retry.",
            blocked_phases={"applying"},
        )
        if not outcome["cancelled"]:
            raise ValueError(str(outcome.get("reason") or "Deep scan could not be cancelled."))

        from app.candidates.discovery import cancel_discovery_import

        match_id = jobs.serialize_job(row).get("payload", {}).get("match_id")
        if match_id:
            cancel_discovery_import(int(match_id), "profile reading")
        return {
            "status": "cancelled",
            "job_id": job_id,
            "kind": row.kind,
            "message": "Deep scan cancelled before candidate changes were applied.",
        }
    if row.kind == "site_connect":
        from app.browser.connection_jobs import signal_cancel

        if not signal_cancel(job_id):
            raise ValueError("The visible login browser is no longer attached to this job.")
        if not jobs.cancel_job(
            job_id, message="Site login cancelled. Browser cleanup is finishing."
        ):
            raise ValueError(f"Job {job_id} could not be cancelled.")
        return {
            "status": "cancelled",
            "job_id": job_id,
            "kind": row.kind,
            "message": "Site login cancelled. Browser cleanup is finishing.",
        }
    if row.kind == "site_verify":
        if not jobs.cancel_job(
            job_id,
            message="Site login verification cancelled. Browser cleanup is finishing.",
        ):
            raise ValueError(f"Job {job_id} could not be cancelled.")
        return {
            "status": "cancelled",
            "job_id": job_id,
            "kind": row.kind,
            "message": "Site login verification cancelled safely.",
        }
    if row.kind in {"embedded_ai_install", "embedded_ai_start"}:
        from app.ai.embedded_jobs import cancel_embedded_ai_job

        return cancel_embedded_ai_job(job_id)
    raise ValueError(f"Job kind '{row.kind}' does not support cancellation yet.")


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
    if original["kind"] in {"site_connect", "site_verify"}:
        from app.browser.connection_jobs import retry_site_job

        return retry_site_job(original)
    if original["kind"] in {"embedded_ai_install", "embedded_ai_start"}:
        from app.ai.embedded_jobs import retry_embedded_ai_job

        return retry_embedded_ai_job(original)
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
