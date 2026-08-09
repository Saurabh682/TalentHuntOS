"""Deterministic clear-hunt + LinkedIn source actions (no LLM required)."""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("talenthunt.copilot.direct_actions")


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
            "talents",
            "candidates",
            "people",
        )
    )
    if not (wants_clear and wants_source):
        # Also accept pure "look for 25 talents on linkedin" when hunt context exists
        if not (wants_source and re.search(r"\b\d+\b", low) and "linkedin" in low):
            return None
        wants_clear = False

    m = re.search(r"\b(\d{1,2})\b", low)
    target = int(m.group(1)) if m else 25
    target = max(1, min(target, 40))
    return {"clear": wants_clear, "target": target, "linkedin": "linkedin" in low}


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
) -> str:
    """Cancel any crawl, optionally clear pipeline, start Playwright+AI sourcing."""
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

    # Always cancel stuck/previous crawls so a new request never no-ops
    cancelled = sourcing_jobs.cancel_all()
    for job in list(sourcing_jobs.list_active_jobs()):
        sourcing_jobs.finish_job(
            job["id"], status="cancelled", message="Superseded by a new clear & source request."
        )
    sourcing_jobs.force_clear_running()

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

    target = max(1, min(int(target or 25), 40))
    job_id = sourcing_jobs.start_job(
        hunt_id=hid,
        hunt_title=hunt_title,
        label=f"Sourcing {target} · {role}",
    )
    per_q = max(6, min(12, (target // 2) + 2))

    def _bg():
        try:
            source_candidates_for_hunt(
                hid,
                role=role,
                skills=skills,
                location=loc,
                hunt_title=hunt_title,
                max_per_query=per_q,
                enrich_pages=True,
                verify_with_ai=True,
                job_id=job_id,
                target_added=target,
            )
        except Exception as exc:
            logger.exception("direct clear+source failed")
            sourcing_jobs.finish_job(job_id, status="error", message=str(exc), error=str(exc))

    threading.Thread(target=_bg, daemon=True, name=f"direct-source-{hid}").start()

    bits = []
    if cancelled:
        bits.append(f"Cancelled {cancelled} previous crawl(s).")
    if clear:
        bits.append(f"Cleared **{removed}** pipeline enrollment(s) from **{hunt_title}**.")
    bits.append(
        f"Started LinkedIn sourcing job `{job_id}` for **{target}** people "
        f"(Playwright open + AI verify). Watch the orange banner — you can **Cancel** anytime. "
        f"Refresh **Pipeline Kanban** when it finishes."
    )
    return "\n\n".join(bits)
