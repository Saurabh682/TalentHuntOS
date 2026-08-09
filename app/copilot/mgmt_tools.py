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
    from app.hunts.experience import parse_experience_range
    from app.hunts.models import HuntSearchConfig

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

            h = resolved
            changed: List[str] = []

            if title.strip():
                h.title = title.strip()
                changed.append("title")
            if target_role.strip():
                h.target_role = target_role.strip()
                changed.append("target_role")
            if location.strip():
                h.location = location.strip()
                changed.append("location")
            if salary_range.strip():
                h.salary_range = salary_range.strip()
                changed.append("salary_range")
            if description.strip():
                h.description = description.strip()
                changed.append("description")

            if not h.search_config:
                h.search_config = HuntSearchConfig(hunt_id=h.id)
                db.add(h.search_config)

            if required_skills.strip():
                h.search_config.required_skills = required_skills.strip()
                changed.append("required_skills")
            if industry.strip():
                h.search_config.industry = industry.strip()
                changed.append("industry")
            if location.strip():
                h.search_config.locations = location.strip()

            if experience.strip():
                emin, emax = parse_experience_range(experience)
                h.search_config.experience_years_min = emin
                h.search_config.experience_years_max = emax
                changed.append("experience")

            if not changed:
                return json.dumps({
                    "status": "noop",
                    "hunt_id": h.id,
                    "message": "No fields to update. Pass title, role, location, experience, salary_range, skills, industry, or description.",
                }, indent=2)

            db.commit()
            return json.dumps({
                "status": "success",
                "action": "update_talent_hunt",
                "hunt_id": h.id,
                "title": h.title,
                "changed": changed,
                "message": f"Updated hunt '{h.title}' ({', '.join(changed)}).",
            }, indent=2)
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
    from app.hunts.service import update_hunt

    allowed = {"Active", "Paused", "Draft", "Completed", "Archived"}
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
            hunt = update_hunt(db, resolved.id, status=st)
            if not hunt:
                return json.dumps({"status": "error", "message": "Update failed."}, indent=2)
            return json.dumps({
                "status": "success",
                "action": "set_hunt_status",
                "hunt_id": hunt.id,
                "title": hunt.title,
                "new_status": hunt.status,
                "message": f"Hunt '{hunt.title}' is now {hunt.status}.",
            }, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@tool
def delete_talent_hunt(hunt_id: str = "", hunt_title: str = "", confirm: bool = False) -> str:
    """Permanently delete a Talent Hunt campaign and its pipeline enrollments.
    Always preview first (confirm=false), then re-call with confirm=true.

    Args:
        hunt_id: Numeric hunt id.
        hunt_title: Title substring if id unknown.
        confirm: Must be True to actually delete.
    """
    from app.infrastructure.db import SessionFactory
    from app.hunts.service import delete_hunt
    from app.hunts.models import HuntCandidate
    from sqlalchemy import select, func

    try:
        with SessionFactory() as db:
            resolved = _resolve_hunt(db, hunt_id, hunt_title)
            if isinstance(resolved, dict) and "ambiguous" in resolved:
                return json.dumps({"status": "ambiguous", "matches": resolved["ambiguous"]}, indent=2)
            if not resolved:
                return json.dumps({"status": "error", "message": "Hunt not found."}, indent=2)

            count = int(
                db.scalar(
                    select(func.count()).select_from(HuntCandidate).where(
                        HuntCandidate.hunt_id == resolved.id
                    )
                )
                or 0
            )
            if not confirm:
                return json.dumps({
                    "status": "preview",
                    "hunt_id": resolved.id,
                    "title": resolved.title,
                    "pipeline_candidates": count,
                    "message": (
                        f"Preview only. Re-call with confirm=true to permanently delete "
                        f"'{resolved.title}' and {count} pipeline enrollment(s)."
                    ),
                }, indent=2)

            title = resolved.title
            hid = resolved.id
            ok = delete_hunt(db, hid)
            if not ok:
                return json.dumps({"status": "error", "message": "Delete failed."}, indent=2)
            return json.dumps({
                "status": "success",
                "action": "delete_talent_hunt",
                "hunt_id": hid,
                "title": title,
                "message": f"Deleted hunt '{title}'.",
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
    from app.hunts.service import list_hunts, get_hunt_metrics

    try:
        with SessionFactory() as db:
            st = None if (not status or status.lower() == "all") else status.strip().title()
            hunts = list_hunts(db, status=st, limit=max(1, min(int(limit or 20), 50)))
            rows = []
            for h in hunts:
                metrics = get_hunt_metrics(db, h.id) or {}
                sc = h.search_config
                exp = None
                if sc and (sc.experience_years_min is not None or sc.experience_years_max is not None):
                    emin, emax = sc.experience_years_min, sc.experience_years_max
                    if emin is not None and emax is not None:
                        exp = f"{emin}-{emax}" if emin != emax else str(emin)
                    elif emin is not None:
                        exp = f"{emin}+"
                rows.append({
                    "id": h.id,
                    "title": h.title,
                    "role": h.target_role,
                    "location": h.location,
                    "status": h.status,
                    "salary_range": h.salary_range,
                    "industry": sc.industry if sc else None,
                    "experience": exp,
                    "skills": sc.required_skills if sc else None,
                    "candidates": metrics.get("total_candidates", 0),
                })
            return json.dumps({"status": "success", "count": len(rows), "hunts": rows}, indent=2)
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
    from app.hunts.playbook import keep_hunt_candidate

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

            result = keep_hunt_candidate(
                db, hc.id, note=(note or "").strip() or None, author_name="Copilot"
            )
            result["hunt_id"] = resolved.id
            result["candidate_name"] = hc.full_name
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
    from app.hunts.playbook import pass_hunt_candidate

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
            result = pass_hunt_candidate(
                db, hc.id, note=(note or "").strip() or None, author_name="Copilot"
            )
            result["hunt_id"] = resolved.id
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
    from app.hunts.pipeline import move_candidate_stage
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

            moved = move_candidate_stage(db, hc.id, stage.id)
            if not moved:
                return json.dumps({"status": "error", "message": "Move failed."}, indent=2)
            return json.dumps({
                "status": "success",
                "action": "move_pipeline_candidate",
                "hunt_id": resolved.id,
                "hunt_candidate_id": hc.id,
                "candidate_name": moved.full_name,
                "stage": stage.name,
                "message": f"Moved '{moved.full_name}' to {stage.name}.",
            }, indent=2)
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
    from app.candidates.models import Candidate, CandidateTag
    from app.hunts.models import HuntCandidate
    from app.hunts.pipeline import add_candidate_to_hunt
    from sqlalchemy import select

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

            candidate = db.get(Candidate, cid)
            if not candidate:
                return json.dumps({"status": "error", "message": f"Candidate {cid} not found."}, indent=2)

            if move_from_other_hunts:
                other = list(
                    db.scalars(
                        select(HuntCandidate).where(
                            HuntCandidate.candidate_id == cid,
                            HuntCandidate.hunt_id != resolved.id,
                        )
                    ).all()
                )
                for hc in other:
                    db.delete(hc)
                tags = list(
                    db.scalars(
                        select(CandidateTag).where(
                            CandidateTag.candidate_id == cid,
                            CandidateTag.tag_name.like("Hunt:%"),
                        )
                    ).all()
                )
                keep_tag = f"Hunt: {resolved.title}".lower()
                for t in tags:
                    if (t.tag_name or "").lower() != keep_tag:
                        db.delete(t)
                db.commit()

            hc = add_candidate_to_hunt(
                db,
                hunt_id=resolved.id,
                full_name=candidate.full_name,
                candidate_id=candidate.id,
                current_title=candidate.current_title,
                current_company=candidate.current_company,
                location=candidate.location,
                linkedin_url=candidate.linkedin_url,
                ai_summary=(note or "").strip()
                or f'Assigned to hunt "{resolved.title}" by Copilot.',
                match_score=80.0,
                source_platform="copilot",
            )

            hunt_tag = f"Hunt: {resolved.title}"
            existing = {
                (t.tag_name or "").lower()
                for t in db.scalars(
                    select(CandidateTag).where(CandidateTag.candidate_id == cid)
                ).all()
            }
            if hunt_tag.lower() not in existing:
                db.add(CandidateTag(candidate_id=cid, tag_name=hunt_tag, tag_type="hunt"))
                db.commit()

            return json.dumps({
                "status": "success",
                "action": "assign_candidate_to_hunt",
                "candidate_id": cid,
                "candidate_name": candidate.full_name,
                "hunt_id": resolved.id,
                "hunt_title": resolved.title,
                "hunt_candidate_id": hc.id if hc else None,
                "moved": bool(move_from_other_hunts),
                "message": f"Assigned {candidate.full_name} to '{resolved.title}'.",
            }, indent=2)
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

        raw = enrich_profile_from_url(url, timeout_ms=int(timeout_ms or 25000))
        # Keep payload chat-friendly
        text = (raw.get("summary") or raw.get("text") or "")[:3500]
        payload = {
            "status": raw.get("status") or ("success" if text else "error"),
            "action": "read_profile_page",
            "url": raw.get("final_url") or raw.get("url") or url,
            "title": raw.get("title"),
            "headline": raw.get("headline"),
            "experience_years": raw.get("experience_years"),
            "senior_title": raw.get("senior_title"),
            "summary": text,
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
        }, indent=2)
    except Exception as e:
        logger.exception("ask_talent_pool failed")
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


ENRICH_TOOLS = [
    read_profile_page,
    ask_talent_pool,
]

# Back-compat: export enrich tools alongside mgmt for a single import list
MGMT_TOOLS = list(MGMT_TOOLS) + list(ENRICH_TOOLS)
