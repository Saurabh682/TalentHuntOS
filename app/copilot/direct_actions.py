"""Deterministic clear-hunt + LinkedIn source actions (no LLM required)."""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Dict, Optional, Tuple

from app.config.constants import MAX_SOURCING_TARGET

logger = logging.getLogger("talenthunt.copilot.direct_actions")

_CONFIRMATION_WORDS = re.compile(
    r"^(?:yes|yes please|confirm|confirmed|proceed|go ahead|do it|"
    r"confirm removal of \d+ candidates?)$",
    re.IGNORECASE,
)
_PENDING_HUNT_CLEAR_MARKER = re.compile(
    r"pending-action:hunt-clear:(?P<hunt_id>\d+):(?P<count>\d+)"
    r"(?::source:(?P<source_target>\d+))?",
    re.IGNORECASE,
)


def _compound_source_request(text: str) -> Optional[Dict[str, Any]]:
    request = parse_clear_and_source(text)
    if request and request.get("clear"):
        return request
    low = (text or "").strip().lower()
    if not (
        any(word in low for word in ("clear", "remove", "delete", "wipe"))
        and "candidate" in low
        and any(phrase in low for phrase in ("add", "new ones", "replace"))
    ):
        return None
    target_match = re.search(r"\b(\d+)\b", low)
    target = max(
        1,
        min(int(target_match.group(1)) if target_match else 25, MAX_SOURCING_TARGET),
    )
    platforms = [
        source
        for source in ("linkedin", "naukri", "github", "behance", "artstation", "dribbble")
        if source in low
    ]
    return {"clear": True, "target": target, "platforms": platforms}


def parse_pending_hunt_clear_confirmation(
    text: str,
    messages: list[dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Resolve a short confirmation only against the latest removal preview."""
    cleaned = re.sub(r"[.!]+$", "", (text or "").strip())
    if not _CONFIRMATION_WORDS.fullmatch(cleaned):
        return None

    latest_assistant_index = next(
        (
            index
            for index in range(len(messages or []) - 1, -1, -1)
            if messages[index].get("role") == "assistant"
        ),
        None,
    )
    latest_assistant = (
        str(messages[latest_assistant_index].get("content") or "")
        if latest_assistant_index is not None
        else ""
    )
    if not latest_assistant:
        return None

    marker = _PENDING_HUNT_CLEAR_MARKER.search(latest_assistant)
    if marker:
        typed_count = re.search(r"confirm removal of (\d+) candidates?", cleaned, re.IGNORECASE)
        if typed_count and int(typed_count.group(1)) != int(marker.group("count")):
            return None
        result = {
            "hunt_id": int(marker.group("hunt_id")),
            "expected_count": int(marker.group("count")),
        }
        if marker.group("source_target"):
            result["source_target"] = int(marker.group("source_target"))
        else:
            for message in reversed((messages or [])[: latest_assistant_index or 0]):
                if message.get("role") != "user":
                    continue
                source_request = _compound_source_request(str(message.get("content") or ""))
                if source_request and source_request.get("clear"):
                    result["source_target"] = int(source_request["target"])
                    if source_request.get("platforms"):
                        result["platforms"] = list(source_request["platforms"])
                    break
        return result

    plain = latest_assistant.replace("**", "").replace("`", "")
    if "confirm removal" not in plain.lower() or "hunt #" not in plain.lower():
        return None
    hunt_match = re.search(r"hunt\s*#(?P<hunt_id>\d+)", plain, re.IGNORECASE)
    count_match = re.search(
        r"(?:found|remove|removal of)\s+(?P<count>\d+)\s+candidate",
        plain,
        re.IGNORECASE,
    )
    if not hunt_match or not count_match:
        return None
    result = {
        "hunt_id": int(hunt_match.group("hunt_id")),
        "expected_count": int(count_match.group("count")),
    }
    for message in reversed((messages or [])[: latest_assistant_index or 0]):
        if message.get("role") != "user":
            continue
        source_request = _compound_source_request(str(message.get("content") or ""))
        if source_request and source_request.get("clear"):
            result["source_target"] = int(source_request["target"])
            if source_request.get("platforms"):
                result["platforms"] = list(source_request["platforms"])
            break
    return result


def run_confirmed_hunt_clear(
    *,
    session_id: str,
    hunt_id: int,
    expected_count: int,
    source_target: int | None = None,
    platforms: list[str] | None = None,
) -> str:
    """Clear a hunt only when its live count still matches the approved preview."""
    from sqlalchemy import func, select

    from app.hunts.models import HuntCandidate
    from app.hunts.pipeline import clear_hunt_candidates
    from app.hunts.service import get_hunt
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        hunt = get_hunt(db, hunt_id)
        if not hunt:
            return f"Hunt #{hunt_id} no longer exists. Nothing was removed."
        current_count = int(
            db.scalar(
                select(func.count()).select_from(HuntCandidate).where(
                    HuntCandidate.hunt_id == hunt_id
                )
            )
            or 0
        )
        if current_count != expected_count:
            source_marker = f":source:{source_target}" if source_target else ""
            continuation = (
                f" After removal, discovery will start for **{source_target} new profiles**."
                if source_target
                else ""
            )
            return (
                f"The pipeline changed after the preview: it showed **{expected_count}** "
                f"candidate(s), but **{hunt.title}** now contains **{current_count}**. "
                "Nothing was removed. Review the current pipeline, then reply "
                f"**confirm removal of {current_count} candidates** to approve the updated scope."
                f"{continuation} "
                f"<!-- pending-action:hunt-clear:{hunt_id}:{current_count}{source_marker} -->"
            )
        if current_count == 0:
            return f"**{hunt.title}** is already empty. Nothing was removed."
        result = clear_hunt_candidates(
            db,
            hunt_id,
            actor_type="copilot",
            session_id=session_id,
        )

    with SessionFactory() as verify_db:
        remaining = int(
            verify_db.scalar(
                select(func.count()).select_from(HuntCandidate).where(
                    HuntCandidate.hunt_id == hunt_id
                )
            )
            or 0
        )
    removed = int(result.get("removed") or 0)
    if remaining:
        return (
            f"Removal failed verification: **{remaining}** candidate(s) remain in "
            f"**{result.get('hunt_title') or hunt_id}**. No success was reported."
        )
    completed = (
        f"Removed **{removed} candidate(s)** from **{result.get('hunt_title')}**. "
        "Master candidate profiles were kept. This action can be undone from "
        "Action history for **7 days**."
    )
    if source_target:
        sourcing = run_clear_and_source(
            session_id=session_id,
            target=source_target,
            clear=False,
            hunt_id=hunt_id,
            platforms=platforms,
        )
        completed += f"\n\n{sourcing}"
    return completed


def parse_clear_and_source(text: str) -> Optional[Dict[str, Any]]:
    """Detect 'clear this hunt and look for N talents…' style commands."""
    raw = (text or "").strip()
    if not raw:
        return None
    low = raw.lower()
    wants_clear = any(w in low for w in ("clear", "remove", "reset", "wipe", "delete"))
    wants_source = any(
        w in low
        for w in (
            "look for",
            "find",
            "source",
            "search",
            "linkedin",
            "naukri",
            "github",
            "behance",
            "artstation",
            "dribbble",
        )
    )
    if not (wants_clear and wants_source):
        # Also accept source-specific commands when hunt context exists.
        named_source = any(
            source in low
            for source in ("linkedin", "naukri", "github", "behance", "artstation", "dribbble")
        )
        if not (wants_source and re.search(r"\b\d+\b", low) and named_source):
            return None
        wants_clear = False

    m = re.search(r"\b(\d+)\b", low)
    target = int(m.group(1)) if m else 25
    target = max(1, min(target, MAX_SOURCING_TARGET))
    platforms = [
        source
        for source in ("linkedin", "naukri", "github", "behance", "artstation", "dribbble")
        if source in low
    ]
    return {"clear": wants_clear, "target": target, "platforms": platforms}


def parse_global_candidate_delete(text: str) -> Optional[Dict[str, Any]]:
    """Detect database-wide candidate deletion without requiring hunt context."""
    low = (text or "").strip().lower()
    if not low or not any(word in low for word in ("delete", "remove", "wipe")):
        return None
    mentions_candidates = "candidate" in low
    global_scope = any(
        phrase in low
        for phrase in (
            "all candidates",
            "every candidate",
            "candidate database",
            "candidates in the database",
            "global database",
            "entire database",
            "whole database",
        )
    )
    if not (mentions_candidates and global_scope):
        return None
    confirm = any(word in low for word in ("confirm", "confirmed", "yes, delete", "do it", "proceed"))
    return {"confirm": confirm}


def run_global_candidate_delete(*, session_id: str, confirm: bool = False) -> str:
    """Preview or archive every visible candidate and record a reversible action."""
    from sqlalchemy import func, select, update
    from app.actions.history import record_action
    from app.candidates.models import Candidate
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidates = list(db.scalars(select(Candidate).where(Candidate.status != "Archived")).all())
        if not candidates:
            return "There are no active candidates to delete."
        if not confirm:
            return (
                f"This will archive **{len(candidates)} candidates** from the global database. "
                "It can be undone from Action history for **7 days**. "
                "Reply **confirm delete all candidates** to proceed."
            )
        candidate_ids = [candidate.id for candidate in candidates]
        previous = {str(candidate.id): candidate.status for candidate in candidates}
        result = db.execute(
            update(Candidate)
            .where(Candidate.id.in_(candidate_ids))
            .values(status="Archived")
        )
        if result.rowcount != len(candidate_ids):
            db.rollback()
            return (
                f"Delete failed verification: expected {len(candidate_ids)} updates but the database "
                f"reported {result.rowcount}. No success was recorded."
            )
        item = record_action(
            db,
            action_type="archive_candidates",
            summary=f"Deleted {len(candidates)} candidates from the global database",
            payload={"candidate_ids": candidate_ids},
            undo_payload={"previous_statuses": previous},
            actor_type="copilot",
            session_id=session_id,
        )
    with SessionFactory() as verify_db:
        archived = verify_db.scalar(
            select(func.count()).select_from(Candidate).where(
                Candidate.id.in_(candidate_ids), Candidate.status == "Archived"
            )
        ) or 0
    if archived != len(candidate_ids):
        return (
            f"Delete did not pass post-commit verification: {archived} of {len(candidate_ids)} "
            "records are archived. The operation must not be reported as successful."
        )
    return (
            f"Archived **{len(candidates)} candidates**. Action **#{item.id}** is undoable for 7 days. "
            "Say **undo that** or use Action history. <!-- ui-refresh:candidates -->"
    )


def resolve_hunt_id(session_id: str, hunt_id: str | int | None = None) -> Optional[int]:
    if hunt_id is not None and str(hunt_id).isdigit():
        return int(hunt_id)
    if session_id.startswith("hunt_"):
        part = session_id.split("_", 1)[1]
        if part.isdigit():
            return int(part)
    return None


def run_clear_and_source(
    *,
    session_id: str,
    target: int = 25,
    clear: bool = True,
    hunt_id: Optional[int] = None,
    platforms: Optional[list[str]] = None,
) -> str:
    """Optionally clear a pipeline and start approval-gated web discovery."""
    from app.infrastructure.db import SessionFactory
    from app.hunts.service import get_hunt
    from app.hunts.pipeline import clear_hunt_candidates
    from app.hunts.web_sourcing import source_candidates_for_hunt
    from app.hunts import sourcing_jobs

    hid = resolve_hunt_id(session_id, hunt_id)
    if not hid:
        return (
            "I need an active hunt selected in the Copilot dropdown "
            "(e.g. **BD-Executive**) before I can clear & source."
        )

    if sourcing_jobs.is_busy():
        return (
            "A talent search is already running. You can keep chatting, but I won't start "
            "another search until it finishes. Say **cancel search** to stop it first."
        )

    with SessionFactory() as db:
        hunt = get_hunt(db, hid)
        if not hunt:
            return f"Hunt id {hid} was not found."
        hunt_title = hunt.title
        role = (hunt.target_role or hunt.title or "Professional").strip()
        loc = (hunt.location or "India").strip() or "India"
        skills = ""
        if hunt.search_config and hunt.search_config.required_skills:
            skills = hunt.search_config.required_skills

        removed = 0
        if clear:
            result = clear_hunt_candidates(db, hid)
            removed = int(result.get("removed") or 0)

    target = max(1, min(int(target or 25), MAX_SOURCING_TARGET))
    job_id = sourcing_jobs.start_job(
        hunt_id=hid,
        hunt_title=hunt_title,
        label=f"Sourcing {target} · {role}",
        payload={
            "role": role,
            "skills": skills,
            "location": loc,
            "target_count": target,
            "platforms": platforms or [],
            "approval_required": True,
            "time_budget_sec": 180,
        },
    )
    per_q = max(6, min(12, (target // 2) + 2))

    def _bg():
        try:
            logger.info("[sourcing] background thread start job=%s hunt=%s", job_id, hid)
            source_candidates_for_hunt(
                hid,
                role=role,
                skills=skills,
                location=loc,
                hunt_title=hunt_title,
                max_per_query=per_q,
                enrich_pages=True,
                verify_with_ai=False,
                job_id=job_id,
                target_added=target,
                approval_required=True,
                time_budget_sec=180,
                platforms=platforms,
            )
        except Exception as exc:
            logger.exception("direct clear+source failed")
            sourcing_jobs.finish_job(job_id, status="error", message=str(exc), error=str(exc))

    threading.Thread(target=_bg, daemon=True, name=f"direct-source-{hid}").start()

    bits = []
    if clear:
        bits.append(f"Cleared **{removed}** pipeline enrollment(s) from **{hunt_title}**.")
    source_label = ", ".join(platform.capitalize() for platform in (platforms or [])) or "all configured sources"
    bits.append(
        f"Started discovery for **{hunt_title}** on **{source_label}** - finding up to **{target}** profiles "
        "for recruiter review. Watch the orange banner; "
        "you can **Cancel** anytime. "
        f"Open **Discoveries → Common Pool** to see every retained profile, including filtered results."
    )
    return "\n\n".join(bits)
