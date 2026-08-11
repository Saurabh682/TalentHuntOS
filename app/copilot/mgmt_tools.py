"""Copilot tools for hunt lifecycle + pipeline triage (parity with UI actions)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

logger = logging.getLogger("talenthunt.copilot.mgmt_tools")


def _parse_id(raw: Optional[str | int], *, prefixes: tuple[str, ...] = ()) -> Optional[int]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    for p in prefixes:
        if s.lower().startswith(p.lower()):
            tail = s[len(p):].lstrip("_-")
            if tail.isdigit():
                return int(tail)
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None


def _resolve_hunt(db, hunt_id: str = "", hunt_title: str = ""):
    from app.hunts.service import get_hunt, list_hunts

    hid = _parse_id(hunt_id)
    if hid:
        hunt = get_hunt(db, hid)
        if hunt:
            return hunt
    needle = (hunt_title or "").strip().lower()
    if not needle:
        return None
    hunts = list_hunts(db)
    matches = [
        h for h in hunts
        if needle in (h.title or "").lower() or needle in (h.target_role or "").lower()
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return {"ambiguous": [{"id": h.id, "title": h.title, "role": h.target_role} for h in matches[:10]]}
    return None


def _resolve_hunt_candidate(db, hunt_id: int, *, hunt_candidate_id: str = "", name_contains: str = ""):
    from app.hunts.models import HuntCandidate
    from sqlalchemy import select

    hcid = _parse_id(hunt_candidate_id, prefixes=("hc_", "hunt_cand_"))
    if hcid:
        hc = db.get(HuntCandidate, hcid)
        if hc and hc.hunt_id == hunt_id:
            return hc
        if hc:
            return None

    needle = (name_contains or "").strip().lower()
    if not needle:
        return None
    rows = list(
        db.scalars(select(HuntCandidate).where(HuntCandidate.hunt_id == hunt_id)).all()
    )
    matches = [hc for hc in rows if needle in (hc.full_name or "").lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return {"ambiguous": [{"id": m.id, "name": m.full_name} for m in matches[:15]]}
    return None


@tool
def update_talent_hunt(
    hunt_id: str = "",
    hunt_title: str = "",
    title: str = "",
    target_role: str = "",
    location: str = "",
    experience: str = "",
    salary_range: str = "",
    required_skills: str = "",
    industry: str = "",
    description: str = "",
) -> str:
    """Update an existing Talent Hunt — same fields as Create/Edit Hunt UI.
    Pass only fields you want to change. Resolve hunt via hunt_id (preferred) or hunt_title.

    Args:
        hunt_id: Numeric hunt database id from active hunt context.
        hunt_title: Title substring if hunt_id unknown.
        title: New campaign title.
        target_role: Target role / job title.
        location: Location or remote policy.
        experience: Free text like '4-5 years', '5+', '3-8'.
        salary_range: Optional salary band (e.g. '₹8–12 LPA'). Empty string clears it.
        required_skills: Comma-separated skills.
        industry: Optional industry (e.g. SaaS, FinTech).
        description: Role summary / responsibilities.
    """
    from app.infrastructure.db import SessionFactory
    try:
        with SessionFactory() as db:
            resolved = _resolve_hunt(db, hunt_id, hunt_title)
            if isinstance(resolved, dict) and "ambiguous" in resolved:
                return json.dumps({"status": "ambiguous", "matches": resolved["ambiguous"]}, indent=2)
            if not resolved:
                return json.dumps({
                    "status": "error",
                    "message": "Hunt not found. Pass hunt_id or a unique hunt_title.",
                }, indent=2)

            resolved_id = resolved.id

        payload = {"hunt_id": resolved_id}
        supplied = {
            "title": title, "target_role": target_role, "location": location,
            "experience": experience, "salary_range": salary_range,
            "required_skills": required_skills, "industry": industry,
            "description": description,
        }
        payload.update({key: value.strip() for key, value in supplied.items() if value.strip()})
        if len(payload) == 1:
            return json.dumps({
                "status": "noop", "hunt_id": resolved_id,
                "message": "No fields to update. Pass title, role, location, experience, salary range, skills, industry, or description.",
            }, indent=2)
        from app.actions.api import dispatch_action
        from app.copilot.session_ctx import get_active_session_id
        result = dispatch_action(
            "hunts.update", payload, actor_type="agent",
            session_id=get_active_session_id() or f"hunt_{resolved_id}",
        )
        if not result.success:
            return json.dumps({"status": "error", "message": result.error}, indent=2)
        return json.dumps(result.data, indent=2)
    except Exception as e:
        logger.exception("update_talent_hunt failed")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def set_hunt_status(hunt_id: str = "", hunt_title: str = "", status: str = "Paused") -> str:
    """Pause, resume, complete, or set draft on a Talent Hunt.
    Valid status values: Active, Paused, Draft, Completed, Archived.

    Args:
        hunt_id: Numeric hunt id (preferred).
        hunt_title: Title substring if id unknown.
        status: New status (default Paused).
    """
    from app.infrastructure.db import SessionFactory
    allowed = {"Active", "Paused", "Draft", "Completed"}
    st = (status or "Paused").strip().title()
    if st == "Pause":
        st = "Paused"
    if st == "Resume":
        st = "Active"
    if st not in allowed:
        return json.dumps({
            "status": "error",
            "message": f"Invalid status '{status}'. Use one of: {sorted(allowed)}",
        }, indent=2)

    try:
        with SessionFactory() as db:
            resolved = _resolve_hunt(db, hunt_id, hunt_title)
            if isinstance(resolved, dict) and "ambiguous" in resolved:
                return json.dumps({"status": "ambiguous", "matches": resolved["ambiguous"]}, indent=2)
            if not resolved:
                return json.dumps({"status": "error", "message": "Hunt not found."}, indent=2)
            resolved_id = resolved.id

        from app.actions.api import dispatch_action
        from app.copilot.session_ctx import get_active_session_id
        result = dispatch_action(
            "hunts.status.set", {"hunt_id": resolved_id, "status": st},
            actor_type="agent", session_id=get_active_session_id() or f"hunt_{resolved_id}",
        )
        if not result.success:
            return json.dumps({"status": "error", "message": result.error}, indent=2)
        return json.dumps(result.data, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def delete_talent_hunt(hunt_id: str = "", hunt_title: str = "", confirm: bool = False) -> str:
    """Request a trusted UI approval card to archive one Talent Hunt.
    The model cannot approve or execute this R3 action itself.

    Args:
        hunt_id: Numeric hunt id.
        hunt_title: Title substring if id unknown.
        confirm: Deprecated and ignored; only the authenticated UI approval button executes.
    """
    from app.infrastructure.db import SessionFactory
    from app.actions.api import dispatch_preview
    from app.copilot.session_ctx import get_active_session_id

    try:
        with SessionFactory() as db:
            resolved = _resolve_hunt(db, hunt_id, hunt_title)
            if isinstance(resolved, dict) and "ambiguous" in resolved:
                return json.dumps({"status": "ambiguous", "matches": resolved["ambiguous"]}, indent=2)
            if not resolved:
                return json.dumps({"status": "error", "message": "Hunt not found."}, indent=2)

            result = dispatch_preview(
                "hunts.archive",
                {"hunt_id": resolved.id},
                actor_type="agent",
                session_id=get_active_session_id() or f"hunt_{resolved.id}",
            )
            if not result.success:
                return json.dumps({"status": "error", "message": result.error}, indent=2)
            payload = result.data or {}
            return json.dumps({
                **payload,
                "message": (
                    "Archive preview created. The authenticated user must use the "
                    "Approve button in Copilot; model confirmation cannot execute it."
                ),
            }, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def list_talent_hunts(status: str = "All", limit: int = 20) -> str:
    """List Talent Hunt campaigns so the agent can pick hunt_id for other tools.

    Args:
        status: Filter — All, Active, Paused, Draft, Completed.
        limit: Max hunts to return (default 20).
    """
    from app.infrastructure.db import SessionFactory
    try:
        from app.actions.api import dispatch_action
        from app.copilot.session_ctx import get_active_session_id
        result = dispatch_action(
            "hunts.list",
            {"status": status, "limit": max(1, min(int(limit or 20), 50))},
            actor_type="agent", session_id=get_active_session_id() or "default",
        )
        if not result.success:
            return json.dumps({"status": "error", "message": result.error}, indent=2)
        return json.dumps(result.data, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def keep_pipeline_candidate(
    hunt_id: str = "",
    hunt_title: str = "",
    hunt_candidate_id: str = "",
    name_contains: str = "",
    note: str = "",
) -> str:
    """Keep a pipeline candidate (log playbook Keep + advance to next stage). Same as Pipeline Keep button.

    Args:
        hunt_id: Numeric hunt id.
        hunt_title: Hunt title substring if id unknown.
        hunt_candidate_id: HuntCandidate row id (preferred when known).
        name_contains: Candidate name filter if id unknown.
        note: Optional Keep reason for the playbook.
    """
    from app.infrastructure.db import SessionFactory
    try:
        with SessionFactory() as db:
            resolved = _resolve_hunt(db, hunt_id, hunt_title)
            if isinstance(resolved, dict) and "ambiguous" in resolved:
                return json.dumps({"status": "ambiguous", "matches": resolved["ambiguous"]}, indent=2)
            if not resolved:
                return json.dumps({"status": "error", "message": "Hunt not found."}, indent=2)

            hc = _resolve_hunt_candidate(
                db, resolved.id, hunt_candidate_id=hunt_candidate_id, name_contains=name_contains
            )
            if isinstance(hc, dict) and "ambiguous" in hc:
                return json.dumps({"status": "ambiguous", "matches": hc["ambiguous"]}, indent=2)
            if not hc:
                return json.dumps({
                    "status": "error",
                    "message": "Candidate not found on this hunt. Pass hunt_candidate_id or a unique name_contains.",
                }, indent=2)

            candidate_name = hc.full_name
            candidate_row_id = hc.id
            resolved_id = resolved.id

        from app.actions.api import dispatch_action
        from app.copilot.session_ctx import get_active_session_id

        action_result = dispatch_action(
            "pipeline.triage",
            {
                "hunt_candidate_id": candidate_row_id,
                "decision": "keep",
                "note": (note or "").strip() or None,
                "author": "Copilot",
            },
            actor_type="agent",
            session_id=get_active_session_id() or "default",
        )
        if not action_result.success:
            return json.dumps({"status": "error", "message": action_result.error}, indent=2)
        result = action_result.data or {}
        result["hunt_id"] = resolved_id
        result["candidate_name"] = candidate_name
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def pass_pipeline_candidate(
    hunt_id: str = "",
    hunt_title: str = "",
    hunt_candidate_id: str = "",
    name_contains: str = "",
    note: str = "",
) -> str:
    """Pass a pipeline candidate (log playbook Pass + remove from hunt). Same as Pipeline Pass button.
    Does NOT delete the master Candidates profile.

    Args:
        hunt_id: Numeric hunt id.
        hunt_title: Hunt title substring if id unknown.
        hunt_candidate_id: HuntCandidate row id.
        name_contains: Candidate name filter if id unknown.
        note: Optional Pass reason for the playbook.
    """
    from app.infrastructure.db import SessionFactory
    try:
        with SessionFactory() as db:
            resolved = _resolve_hunt(db, hunt_id, hunt_title)
            if isinstance(resolved, dict) and "ambiguous" in resolved:
                return json.dumps({"status": "ambiguous", "matches": resolved["ambiguous"]}, indent=2)
            if not resolved:
                return json.dumps({"status": "error", "message": "Hunt not found."}, indent=2)

            hc = _resolve_hunt_candidate(
                db, resolved.id, hunt_candidate_id=hunt_candidate_id, name_contains=name_contains
            )
            if isinstance(hc, dict) and "ambiguous" in hc:
                return json.dumps({"status": "ambiguous", "matches": hc["ambiguous"]}, indent=2)
            if not hc:
                return json.dumps({
                    "status": "error",
                    "message": "Candidate not found on this hunt.",
                }, indent=2)

            name = hc.full_name
            candidate_row_id = hc.id
            resolved_id = resolved.id

        from app.actions.api import dispatch_action
        from app.copilot.session_ctx import get_active_session_id

        action_result = dispatch_action(
            "pipeline.triage",
            {
                "hunt_candidate_id": candidate_row_id,
                "decision": "pass",
                "note": (note or "").strip() or None,
                "author": "Copilot",
            },
            actor_type="agent",
            session_id=get_active_session_id() or "default",
        )
        if not action_result.success:
            return json.dumps({"status": "error", "message": action_result.error}, indent=2)
        result = action_result.data or {}
        result["hunt_id"] = resolved_id
        result["candidate_name"] = name
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def move_pipeline_candidate(
    hunt_id: str = "",
    hunt_title: str = "",
    hunt_candidate_id: str = "",
    name_contains: str = "",
    stage_name: str = "",
) -> str:
    """Move a pipeline candidate to a named stage (Sourced, Contacted, Screening, Interview, Offer, Hired, Rejected).

    Args:
        hunt_id: Numeric hunt id.
        hunt_title: Hunt title substring if id unknown.
        hunt_candidate_id: HuntCandidate row id.
        name_contains: Candidate name filter if id unknown.
        stage_name: Target stage name (required).
    """
    from app.infrastructure.db import SessionFactory
    from app.hunts.models import HuntStage
    from sqlalchemy import select

    stage_needle = (stage_name or "").strip()
    if not stage_needle:
        return json.dumps({"status": "error", "message": "stage_name is required."}, indent=2)

    try:
        with SessionFactory() as db:
            resolved = _resolve_hunt(db, hunt_id, hunt_title)
            if isinstance(resolved, dict) and "ambiguous" in resolved:
                return json.dumps({"status": "ambiguous", "matches": resolved["ambiguous"]}, indent=2)
            if not resolved:
                return json.dumps({"status": "error", "message": "Hunt not found."}, indent=2)

            hc = _resolve_hunt_candidate(
                db, resolved.id, hunt_candidate_id=hunt_candidate_id, name_contains=name_contains
            )
            if isinstance(hc, dict) and "ambiguous" in hc:
                return json.dumps({"status": "ambiguous", "matches": hc["ambiguous"]}, indent=2)
            if not hc:
                return json.dumps({"status": "error", "message": "Candidate not found on this hunt."}, indent=2)

            stages = list(
                db.scalars(
                    select(HuntStage).where(HuntStage.hunt_id == resolved.id).order_by(HuntStage.position)
                ).all()
            )
            needle = stage_needle.lower()
            stage = next((s for s in stages if (s.name or "").lower() == needle), None)
            if not stage:
                stage = next((s for s in stages if needle in (s.name or "").lower()), None)
            if not stage:
                return json.dumps({
                    "status": "error",
                    "message": f"Stage '{stage_name}' not found.",
                    "available_stages": [s.name for s in stages],
                }, indent=2)

            from app.copilot.session_ctx import get_active_session_id

            from app.actions.api import dispatch_action

            action_result = dispatch_action(
                "pipeline.move",
                {"hunt_candidate_id": hc.id, "stage_id": stage.id},
                actor_type="agent",
                session_id=get_active_session_id() or "default",
            )
            if not action_result.success:
                return json.dumps({"status": "error", "message": action_result.error}, indent=2)
            return json.dumps(action_result.data, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def assign_candidate_to_hunt(
    candidate_id: str,
    hunt_id: str = "",
    hunt_title: str = "",
    move_from_other_hunts: bool = False,
    note: str = "",
) -> str:
    """Assign an existing Candidates-page profile to a Talent Hunt pipeline (same as Add to Hunt UI).

    Args:
        candidate_id: Master candidate id (e.g. '12' or 'cand_12').
        hunt_id: Target hunt numeric id.
        hunt_title: Hunt title substring if id unknown.
        move_from_other_hunts: If True, remove from other hunts first (move vs add).
        note: Optional assignment note stored on the enrollment.
    """
    from app.infrastructure.db import SessionFactory
    cid = _parse_id(candidate_id, prefixes=("cand_", "candidate_"))
    if not cid:
        return json.dumps({"status": "error", "message": "candidate_id must be numeric or cand_N."}, indent=2)

    try:
        with SessionFactory() as db:
            resolved = _resolve_hunt(db, hunt_id, hunt_title)
            if isinstance(resolved, dict) and "ambiguous" in resolved:
                return json.dumps({"status": "ambiguous", "matches": resolved["ambiguous"]}, indent=2)
            if not resolved:
                return json.dumps({"status": "error", "message": "Hunt not found."}, indent=2)

            resolved_id = resolved.id

        from app.actions.api import dispatch_action
        from app.copilot.session_ctx import get_active_session_id

        result = dispatch_action(
            "pipeline.enroll",
            {
                "candidate_id": cid,
                "hunt_id": resolved_id,
                "move_from_other_hunts": move_from_other_hunts,
                "note": (note or "").strip() or None,
            },
            actor_type="agent",
            session_id=get_active_session_id() or "default",
        )
        if not result.success:
            return json.dumps({"status": "error", "message": result.error}, indent=2)
        return json.dumps(result.data, indent=2)
    except Exception as e:
        logger.exception("assign_candidate_to_hunt failed")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


MGMT_TOOLS = [
    update_talent_hunt,
    set_hunt_status,
    delete_talent_hunt,
    list_talent_hunts,
    keep_pipeline_candidate,
    pass_pipeline_candidate,
    move_pipeline_candidate,
    assign_candidate_to_hunt,
]


@tool
def read_profile_page(url: str, timeout_ms: int = 25000) -> str:
    """Open a LinkedIn/Naukri/profile URL in Playwright, expand the page, and return readable text + heuristics.
    Same capability as Candidate Detail "Open & read page". Use before verifying or adding a web candidate.

    Args:
        url: Full profile URL (prefer linkedin.com/in/...).
        timeout_ms: Navigation timeout (default 25000).
    """
    try:
        from app.browser.page_reader import enrich_profile_from_url

        raw = enrich_profile_from_url(url, timeout_ms=int(timeout_ms or 25000), save_snapshot=True)
        # Keep payload chat-friendly
        text = (raw.get("summary") or raw.get("text") or "")[:3500]
        snap = raw.get("snapshot") or {}
        payload = {
            "status": raw.get("status") or ("success" if text else "error"),
            "action": "read_profile_page",
            "url": raw.get("final_url") or raw.get("url") or url,
            "title": raw.get("title"),
            "headline": raw.get("headline"),
            "experience_years": raw.get("experience_years"),
            "senior_title": raw.get("senior_title"),
            "summary": text,
            "snapshot_dir": snap.get("snapshot_dir"),
            "error": raw.get("error"),
        }
        if not text and not payload.get("error"):
            payload["status"] = "empty"
            payload["message"] = "Page opened but little readable text was extracted (login wall or empty DOM)."
        return json.dumps(payload, indent=2)
    except Exception as e:
        logger.exception("read_profile_page failed")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def ask_talent_pool(question: str) -> str:
    """Ask a natural-language question over the local Candidates talent pool (LlamaIndex RAG).
    Same capability as Candidates page "Ask RAG". Use for questions like who has React + 5 years in India.

    Args:
        question: Recruiter question about people already in the database.
    """
    q = (question or "").strip()
    if not q:
        return json.dumps({"status": "error", "message": "question is required."}, indent=2)
    try:
        from app.infrastructure.db import SessionFactory
        from app.candidates.rag import CandidateRAGPipeline

        with SessionFactory() as db:
            result = CandidateRAGPipeline().query_candidate_database(q, db)
        return json.dumps({
            "status": "success",
            "action": "ask_talent_pool",
            "query": result.get("query"),
            "answer": result.get("answer"),
            "sources": result.get("sources") or [],
            "retrieval": result.get("retrieval") or {},
        }, indent=2)
    except Exception as e:
        logger.exception("ask_talent_pool failed")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def enrich_candidate_profile(
    candidate_id: str,
    url: str = "",
    text: str = "",
    apply: bool = False,
    mode: str = "merge",
) -> str:
    """Extract structured experience / education / skills from a profile URL or pasted text.
    Same capability as Candidate Detail Fill from page / Paste text.
    By default returns a proposed JSON draft for recruiter confirmation.
    Set apply=true only when the user explicitly asks to save/write to the profile.

    Args:
        candidate_id: Candidate database id (e.g. '31' or 'cand_31').
        url: Optional LinkedIn/profile URL to open and read first.
        text: Optional pasted resume/profile text (used when url empty).
        apply: If true, write extracted sections to the candidate (merge or replace).
        mode: 'merge' (default) or 'replace' when apply=true.
    """
    from app.infrastructure.db import SessionFactory
    from app.candidates.service import get_candidate, replace_or_merge_profile_sections
    from app.candidates.profile_extract import extract_profile_from_text, extract_result_to_dict

    cid = _parse_id(candidate_id, prefixes=("cand_", "candidate_"))
    if not cid:
        return json.dumps({"status": "error", "message": "candidate_id is required."}, indent=2)

    source_text = (text or "").strip()
    try:
        with SessionFactory() as db:
            cand = get_candidate(db, cid)
            if not cand:
                return json.dumps({"status": "error", "message": f"Candidate {cid} not found."}, indent=2)

        enriched = {}
        if (url or "").strip():
            from app.browser.page_reader import enrich_profile_from_url
            enriched = enrich_profile_from_url(
                url.strip(),
                headless=True,
                candidate_id=cid,
                save_snapshot=True,
            )
            source_text = (enriched.get("text") or source_text or "").strip()
            if enriched.get("status") != "success" and len(source_text) < 40:
                return json.dumps({
                    "status": "error",
                    "action": "enrich_candidate_profile",
                    "message": enriched.get("error") or "Page read failed.",
                    "blocked": enriched.get("blocked"),
                }, indent=2)
        elif not source_text:
            # Fall back to stored resume/summary
            with SessionFactory() as db:
                cand = get_candidate(db, cid)
                if cand and cand.profile:
                    source_text = (cand.profile.resume_text or cand.profile.summary or "").strip()

        if len(source_text) < 40:
            return json.dumps({
                "status": "error",
                "message": "Need a profile URL, pasted text, or stored resume text to extract.",
            }, indent=2)

        result = extract_profile_from_text(source_text)
        draft = extract_result_to_dict(result)
        if result.status not in {"success"} and not draft.get("experiences") and not draft.get("skills"):
            return json.dumps({
                "status": result.status,
                "action": "enrich_candidate_profile",
                "error": result.error,
                "proposal": draft,
            }, indent=2)

        if apply:
            with SessionFactory() as db:
                cand = replace_or_merge_profile_sections(
                    db,
                    cid,
                    experiences=draft.get("experiences") or None,
                    educations=draft.get("educations") or None,
                    skills=draft.get("skills") or None,
                    highlights=draft.get("highlights") or None,
                    full_name=draft.get("full_name"),
                    email=draft.get("email"),
                    phone=draft.get("phone"),
                    location=draft.get("location") or enriched.get("location"),
                    current_title=draft.get("current_title"),
                    current_company=draft.get("current_company"),
                    pronouns=draft.get("pronouns"),
                    connection_degree=draft.get("connection_degree"),
                    connections_count=draft.get("connections_count"),
                    profile_image_url=(
                        enriched.get("profile_image_url") or draft.get("profile_image_url")
                    ),
                    headline=draft.get("headline"),
                    summary=draft.get("summary"),
                    experience_years=draft.get("experience_years"),
                    mode=mode or "merge",
                )
            if not cand:
                return json.dumps({"status": "error", "message": "Failed to apply sections."}, indent=2)
            return json.dumps({
                "status": "success",
                "action": "enrich_candidate_profile",
                "applied": True,
                "mode": mode or "merge",
                "candidate_id": cid,
                "counts": {
                    "experiences": len(draft.get("experiences") or []),
                    "educations": len(draft.get("educations") or []),
                    "skills": len(draft.get("skills") or []),
                },
            }, indent=2)

        return json.dumps({
            "status": "success",
            "action": "enrich_candidate_profile",
            "applied": False,
            "message": "Draft only — show the user and call again with apply=true to save.",
            "candidate_id": cid,
            "proposal": draft,
        }, indent=2)
    except Exception as e:
        logger.exception("enrich_candidate_profile failed")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def create_candidate_intake_link(candidate_id: str, hunt_id: str = "") -> str:
    """Create a magic-link candidate profile/JD form. Returns URL + draft outreach text (does NOT send email).
    Same as Candidate Detail 'Send profile form'.

    Args:
        candidate_id: Candidate database id.
        hunt_id: Optional hunt id to attach JD context to the form.
    """
    from app.infrastructure.db import SessionFactory
    from app.candidates.service import get_candidate
    from app.candidates.intake_service import (
        create_intake_request,
        draft_outreach_message,
        get_hunt_jd_context,
        intake_url_for_token,
    )

    cid = _parse_id(candidate_id, prefixes=("cand_", "candidate_"))
    if not cid:
        return json.dumps({"status": "error", "message": "candidate_id is required."}, indent=2)
    hid = _parse_id(hunt_id) if hunt_id else None

    try:
        with SessionFactory() as db:
            cand = get_candidate(db, cid)
            if not cand:
                return json.dumps({"status": "error", "message": f"Candidate {cid} not found."}, indent=2)
            req = create_intake_request(db, cid, hunt_id=hid, mark_sent=True)
            if not req:
                return json.dumps({"status": "error", "message": "Could not create intake link."}, indent=2)
            url = intake_url_for_token(req.token)
            jd = get_hunt_jd_context(db, hid)
            msg = draft_outreach_message(
                cand, url=url, hunt_title=jd.get("title"), role=jd.get("role")
            )
            return json.dumps({
                "status": "success",
                "action": "create_candidate_intake_link",
                "candidate_id": cid,
                "hunt_id": hid,
                "request_id": req.id,
                "url": url,
                "draft_message": msg,
                "sent": False,
                "message": "Link created. Copy draft_message into email/LinkedIn — nothing was sent.",
            }, indent=2)
    except Exception as e:
        logger.exception("create_candidate_intake_link failed")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def list_pending_intake_submissions(candidate_id: str = "") -> str:
    """List candidate form submissions awaiting recruiter Accept/Reject.

    Args:
        candidate_id: Optional filter to one candidate.
    """
    from app.infrastructure.db import SessionFactory
    from app.candidates.intake_service import list_pending_submissions

    cid = _parse_id(candidate_id, prefixes=("cand_", "candidate_")) if candidate_id else None
    try:
        with SessionFactory() as db:
            rows = list_pending_submissions(db, candidate_id=cid, limit=50)
        return json.dumps({
            "status": "success",
            "action": "list_pending_intake_submissions",
            "count": len(rows),
            "submissions": rows,
        }, indent=2)
    except Exception as e:
        logger.exception("list_pending_intake_submissions failed")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def apply_intake_submission(
    submission_id: str,
    accept: bool = True,
    mode: str = "merge",
    confirm: bool = False,
) -> str:
    """Accept (merge into Experience/Education/Skills) or reject a pending candidate intake submission.

    Args:
        submission_id: Intake submission id from list_pending_intake_submissions.
        accept: True to apply to profile, False to reject.
        mode: 'merge' or 'replace' when accepting.
        confirm: Must be True to apply or reject the submission.
    """
    from app.infrastructure.db import SessionFactory
    from app.candidates.intake_service import apply_intake_submission as _apply

    sid = _parse_id(submission_id)
    if not sid:
        return json.dumps({"status": "error", "message": "submission_id is required."}, indent=2)
    if not confirm:
        action = "accept and apply" if accept else "reject"
        return json.dumps({
            "status": "preview",
            "submission_id": sid,
            "action": action,
            "message": f"Preview only. Re-call with confirm=true to {action} this submission.",
        }, indent=2)
    try:
        with SessionFactory() as db:
            result = _apply(db, sid, mode=mode or "merge", accept=bool(accept))
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.exception("apply_intake_submission failed")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def list_connected_sites() -> str:
    """Show which sourcing sites (LinkedIn, Naukri, …) have an encrypted local login session.
    Tell the user to connect from Settings → Connected sites if a site is disconnected.
    """
    try:
        from app.browser.session_auth import get_platform_connection_status

        rows = get_platform_connection_status()
        return json.dumps({
            "status": "success",
            "action": "list_connected_sites",
            "sites": rows,
            "hint": "Connect from Settings → Connected sites (opens Chromium; cookies encrypted locally).",
        }, indent=2)
    except Exception as e:
        logger.exception("list_connected_sites failed")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def disconnect_site(platform: str, confirm: bool = False) -> str:
    """Disconnect a saved site login while retaining encrypted data for seven-day undo.

    Args:
        platform: linkedin | naukri | github | indeed
        confirm: Must be True to deactivate the saved browser session.
    """
    if not confirm:
        return json.dumps({
            "status": "preview",
            "platform": platform,
            "message": f"Preview only. Re-call with confirm=true to disconnect {platform}.",
        }, indent=2)
    try:
        from app.browser.session_auth import disconnect_platform

        result = disconnect_platform(platform, actor_type="copilot")
        result["action"] = "disconnect_site"
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.exception("disconnect_site failed")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


ENRICH_TOOLS = [
    read_profile_page,
    ask_talent_pool,
    enrich_candidate_profile,
    create_candidate_intake_link,
    list_pending_intake_submissions,
    apply_intake_submission,
    list_connected_sites,
    disconnect_site,
]

# Back-compat: export enrich tools alongside mgmt for a single import list
MGMT_TOOLS = list(MGMT_TOOLS) + list(ENRICH_TOOLS)
