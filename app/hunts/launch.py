"""Launch a Talent Hunt and kick off Copilot sourcing (LinkedIn + Naukri by default)."""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from nicegui import ui

from app.copilot.conversation import conversation_manager
from app.infrastructure.db import SessionFactory

logger = logging.getLogger("talenthunt.hunts.launch")

DEFAULT_LOCATION = "India"
DEFAULT_PLATFORMS = ["linkedin", "naukri"]


def build_sourcing_prompt(
    *,
    hunt_id: int,
    title: str,
    role: str,
    location: str,
    skills: str,
    experience: str = "",
    salary: str = "",
    industry: str = "",
    summary: str = "",
) -> str:
    """Build the Copilot user prompt that starts LinkedIn + Naukri sourcing."""
    loc = location.strip() or DEFAULT_LOCATION
    role_label = role.strip() or title.strip()
    skill_bits = [s.strip() for s in skills.split(",") if s.strip()]
    primary_skill = skill_bits[0] if skill_bits else role_label
    industry_bit = (industry or "").strip()
    industry_q = f' "{industry_bit}"' if industry_bit else ""

    return f"""I just launched Talent Hunt "{title}" (hunt_id={hunt_id}).

Role: {role_label}
Location: {loc}
Industry: {industry_bit or "N/A"}
Required skills: {skills or "N/A"}
Experience: {experience or "N/A"}
Salary: {salary or "N/A"}
Summary: {summary or "N/A"}

START SOURCING NOW. Defaults:
1) Search LinkedIn (site:linkedin.com/in)
2) Search Naukri (site:naukri.com)
3) Prefer candidates in {loc} / India
4) HARD FILTER on experience: only keep profiles inside "{experience or "any"}".
   Reject GMs/Directors/VPs/Founders and anyone clearly outside that band.
5) If industry is set, prefer profiles with experience in that industry.

Run batch_search_the_web with queries like:
- site:linkedin.com/in "{role_label}" {primary_skill}{industry_q} {experience or ""} {loc}
- site:naukri.com "{role_label}" {primary_skill}{industry_q} {experience or ""} {loc}
- "{role_label}" "{primary_skill}"{industry_q} {experience or "years"} resume {loc}

Also call search_candidates for our internal talent pool (same experience bounds).

For each strong match: verify_candidate_match, then add_candidate_to_database with hunt_id="{hunt_id}".
Do NOT add candidates outside the experience range.
Reply with a short live status as you search and save candidates."""


def launch_hunt_and_start_sourcing(
    *,
    title: str,
    target_role: Optional[str] = None,
    location: Optional[str] = None,
    salary_range: Optional[str] = None,
    description: Optional[str] = None,
    required_skills: Optional[str] = None,
    experience: Optional[str] = None,
    industry: Optional[str] = None,
    actor_type: str = "ui",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an Active hunt, bind Copilot session, and queue sourcing prompt."""
    loc = (location or "").strip() or DEFAULT_LOCATION
    role = (target_role or "").strip() or title.strip()
    skills = (required_skills or "").strip()
    exp = (experience or "").strip()
    industry_val = (industry or "").strip()

    from app.actions.api import dispatch_action

    created = dispatch_action(
        "hunts.create",
        {
            "title": title.strip(), "target_role": role, "location": loc,
            "salary_range": (salary_range or "").strip() or None,
            "description": (description or "").strip() or None,
            "required_skills": skills or None, "experience": exp or None,
            "industry": industry_val or None, "target_platforms": DEFAULT_PLATFORMS,
            "status": "Active",
        },
        actor_type=actor_type,
        session_id=session_id or "hunt_launch",
    )
    if not created.success:
        raise RuntimeError(created.error or "Failed to create Talent Hunt")
    hunt_id = int(created.data["hunt_id"])
    hunt_title = str(created.data["hunt_title"])

    session_id = f"hunt_{hunt_id}"
    prompt = build_sourcing_prompt(
        hunt_id=hunt_id,
        title=hunt_title,
        role=role,
        location=loc,
        skills=skills,
        experience=exp,
        salary=(salary_range or "").strip(),
        industry=industry_val,
        summary=(description or "").strip(),
    )

    conversation_manager.add_assistant_message(
        (
            f"🚀 **{hunt_title}** is live.\n\n"
            f"I'll start sourcing for **{role}** in **{loc}**, "
            f"defaulting to **LinkedIn** and **Naukri.com**.\n\n"
            f"Switching this chat to the hunt context and beginning search…"
        ),
        session_id=session_id,
    )

    # Persist session + pending prompt for Copilot panel on next page render
    try:
        ui.app.storage.user["active_session_id"] = session_id
        ui.app.storage.user["pending_copilot_prompt"] = prompt
        try:
            from app.ui.panels.copilot_panel import _COPILOT_STATE, _persist_session
            _COPILOT_STATE["session_id"] = session_id
            _persist_session(session_id)
        except Exception:
            pass
    except Exception as exc:
        logger.warning("Could not write user storage for hunt launch: %s", exc)

    # Check the local pool once. The queued Copilot prompt owns the single tracked
    # web search; starting another hidden crawl here doubles browser work.
    def _source_after_launch():
        auto_added = 0
        try:
            from app.intelligence.auto_pilot import run_autopilot_hunt_job
            auto_result = run_autopilot_hunt_job(hunt_id) or {}
            auto_added = int(auto_result.get("added") or auto_result.get("candidates_sourced") or 0)
        except Exception as exc:
            logger.error("AutoPilot after launch failed: %s", exc)

        try:
            conversation_manager.add_assistant_message(
                (
                    f"Local pool check complete for **{hunt_title}**: **{auto_added}** match(es) added. "
                    "The tracked LinkedIn/Naukri search is handled by Copilot so it can be "
                    "monitored and cancelled without launching a duplicate crawl."
                ),
                session_id=session_id,
            )
        except Exception as exc:
            logger.warning("Could not post sourcing summary to Copilot: %s", exc)

    threading.Thread(
        target=_source_after_launch,
        daemon=True,
        name=f"source-hunt-{hunt_id}",
    ).start()

    return {
        "hunt_id": hunt_id,
        "session_id": session_id,
        "title": hunt_title,
        "location": loc,
        "prompt": prompt,
        "action_id": created.data.get("action_id"),
    }
