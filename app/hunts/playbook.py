"""Global sourcing playbook: Keep/Pass triage logs and shared insights."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.hunts.models import PlaybookEntry, TalentHunt, HuntCandidate, HuntStage, HuntActivity
from app.candidates.models import CandidateTag

logger = logging.getLogger("talenthunt.hunts.playbook")


def _create_entry(
    db: Session,
    *,
    entry_type: str,
    insight_outcome: Optional[str] = None,
    role_context: Optional[str] = None,
    platform: Optional[str] = None,
    query_text: Optional[str] = None,
    candidate_name: Optional[str] = None,
    candidate_title: Optional[str] = None,
    candidate_id: Optional[int] = None,
    hunt_id: Optional[int] = None,
    hunt_title: Optional[str] = None,
    note: Optional[str] = None,
    author_name: str = "Recruiter",
    metadata: Optional[Dict[str, Any]] = None,
    commit: bool = True,
) -> PlaybookEntry:
    entry = PlaybookEntry(
        entry_type=entry_type,
        insight_outcome=insight_outcome,
        role_context=(role_context or "").strip() or None,
        platform=(platform or "").strip().lower() or None,
        query_text=(query_text or "").strip() or None,
        candidate_name=(candidate_name or "").strip() or None,
        candidate_title=(candidate_title or "").strip() or None,
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        hunt_title=(hunt_title or "").strip() or None,
        note=(note or "").strip() or None,
        author_name=(author_name or "Recruiter").strip() or "Recruiter",
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(entry)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(entry)
    return entry


def log_keep(
    db: Session,
    *,
    hunt_candidate: HuntCandidate,
    note: Optional[str] = None,
    author_name: str = "Recruiter",
    commit: bool = True,
) -> PlaybookEntry:
    hunt = db.get(TalentHunt, hunt_candidate.hunt_id)
    return _create_entry(
        db,
        entry_type="keep",
        role_context=(hunt.target_role if hunt else None) or (hunt.title if hunt else None),
        platform=hunt_candidate.source_platform,
        query_text=hunt_candidate.source_query,
        candidate_name=hunt_candidate.full_name,
        candidate_title=hunt_candidate.current_title,
        candidate_id=hunt_candidate.candidate_id,
        hunt_id=hunt_candidate.hunt_id,
        hunt_title=hunt.title if hunt else None,
        note=note,
        author_name=author_name,
        metadata={"hunt_candidate_id": hunt_candidate.id, "match_score": hunt_candidate.match_score},
        commit=commit,
    )


def log_pass(
    db: Session,
    *,
    hunt_candidate: HuntCandidate,
    note: Optional[str] = None,
    author_name: str = "Recruiter",
    commit: bool = True,
) -> PlaybookEntry:
    hunt = db.get(TalentHunt, hunt_candidate.hunt_id)
    return _create_entry(
        db,
        entry_type="pass",
        role_context=(hunt.target_role if hunt else None) or (hunt.title if hunt else None),
        platform=hunt_candidate.source_platform,
        query_text=hunt_candidate.source_query,
        candidate_name=hunt_candidate.full_name,
        candidate_title=hunt_candidate.current_title,
        candidate_id=hunt_candidate.candidate_id,
        hunt_id=hunt_candidate.hunt_id,
        hunt_title=hunt.title if hunt else None,
        note=note,
        author_name=author_name,
        metadata={"hunt_candidate_id": hunt_candidate.id, "match_score": hunt_candidate.match_score},
        commit=commit,
    )


def add_insight(
    db: Session,
    *,
    worked: bool,
    note: str,
    role_context: Optional[str] = None,
    platform: Optional[str] = None,
    query_text: Optional[str] = None,
    hunt_id: Optional[int] = None,
    hunt_title: Optional[str] = None,
    author_name: str = "Recruiter",
) -> PlaybookEntry:
    return _create_entry(
        db,
        entry_type="insight",
        insight_outcome="worked" if worked else "didnt_work",
        role_context=role_context,
        platform=platform,
        query_text=query_text,
        hunt_id=hunt_id,
        hunt_title=hunt_title,
        note=note,
        author_name=author_name,
    )


def list_playbook_entries(
    db: Session,
    *,
    entry_type: Optional[str] = None,
    role: Optional[str] = None,
    platform: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
) -> List[PlaybookEntry]:
    stmt = select(PlaybookEntry).order_by(PlaybookEntry.created_at.desc())

    if entry_type and entry_type != "All":
        et = entry_type.lower()
        if et in {"keep", "kept"}:
            stmt = stmt.where(PlaybookEntry.entry_type == "keep")
        elif et in {"pass", "passed"}:
            stmt = stmt.where(PlaybookEntry.entry_type == "pass")
        elif et in {"insight", "insights"}:
            stmt = stmt.where(PlaybookEntry.entry_type == "insight")

    if role and role.strip():
        stmt = stmt.where(PlaybookEntry.role_context.ilike(f"%{role.strip()}%"))

    if platform and platform.strip() and platform.lower() != "all":
        stmt = stmt.where(PlaybookEntry.platform == platform.strip().lower())

    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                PlaybookEntry.note.ilike(term),
                PlaybookEntry.query_text.ilike(term),
                PlaybookEntry.candidate_name.ilike(term),
                PlaybookEntry.candidate_title.ilike(term),
                PlaybookEntry.hunt_title.ilike(term),
                PlaybookEntry.role_context.ilike(term),
            )
        )

    stmt = stmt.limit(limit)
    return list(db.scalars(stmt).all())


def get_playbook_tips_for_role(
    db: Session,
    role: str,
    *,
    limit: int = 12,
) -> List[Dict[str, Any]]:
    """Read-only tip digest for Copilot / UI summaries."""
    entries = list_playbook_entries(db, role=role, limit=limit * 2)
    tips: List[Dict[str, Any]] = []
    for e in entries[:limit]:
        tips.append({
            "type": e.entry_type,
            "outcome": e.insight_outcome,
            "role": e.role_context,
            "platform": e.platform,
            "query": e.query_text,
            "candidate": e.candidate_name,
            "title": e.candidate_title,
            "note": e.note,
            "hunt": e.hunt_title,
            "author": e.author_name,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })
    return tips


def keep_hunt_candidate(
    db: Session,
    hunt_candidate_id: int,
    *,
    note: Optional[str] = None,
    author_name: str = "Recruiter",
    commit: bool = True,
) -> Dict[str, Any]:
    """Log Keep, move to next pipeline stage (Screening)."""
    hc = db.get(HuntCandidate, hunt_candidate_id)
    if not hc:
        return {"status": "error", "error": "Hunt candidate not found"}

    entry = log_keep(
        db, hunt_candidate=hc, note=note, author_name=author_name, commit=False
    )
    hc = db.get(HuntCandidate, hunt_candidate_id)
    if not hc:
        return {"status": "success", "action": "keep", "playbook_entry_id": entry.id, "moved_to_stage": None}

    # Move to next stage by position
    stages = list(
        db.scalars(
            select(HuntStage).where(HuntStage.hunt_id == hc.hunt_id).order_by(HuntStage.position)
        ).all()
    )
    current_idx = next((i for i, s in enumerate(stages) if s.id == hc.stage_id), 0)
    next_stage = stages[current_idx + 1] if current_idx + 1 < len(stages) else None
    if next_stage:
        old_name = stages[current_idx].name if stages else "Sourced"
        hc.stage_id = next_stage.id
        db.add(
            HuntActivity(
                hunt_id=hc.hunt_id,
                candidate_id=hc.id,
                activity_type="keep",
                description=f"Kept '{hc.full_name}' ({old_name} → {next_stage.name}).",
                metadata_json=json.dumps({"playbook_entry_id": entry.id, "note": note}),
            )
        )
    if commit:
        db.commit()
    else:
        db.flush()

    return {
        "status": "success",
        "action": "keep",
        "playbook_entry_id": entry.id,
        "moved_to_stage": next_stage.name if next_stage else None,
    }


def pass_hunt_candidate(
    db: Session,
    hunt_candidate_id: int,
    *,
    note: Optional[str] = None,
    author_name: str = "Recruiter",
    commit: bool = True,
) -> Dict[str, Any]:
    """Log Pass, remove from hunt only, strip Hunt: tag for this hunt."""
    hc = db.get(HuntCandidate, hunt_candidate_id)
    if not hc:
        return {"status": "error", "error": "Hunt candidate not found"}

    entry = log_pass(
        db, hunt_candidate=hc, note=note, author_name=author_name, commit=False
    )
    hc = db.get(HuntCandidate, hunt_candidate_id)
    if not hc:
        return {"status": "success", "action": "pass", "playbook_entry_id": entry.id}

    hunt = db.get(TalentHunt, hc.hunt_id)
    master_id = hc.candidate_id
    name = hc.full_name
    hunt_id = hc.hunt_id

    # Strip hunt tag from master candidate if present
    if master_id and hunt:
        tag_name = f"Hunt: {hunt.title}"
        tags = list(
            db.scalars(
                select(CandidateTag).where(
                    CandidateTag.candidate_id == master_id,
                    CandidateTag.tag_name == tag_name,
                )
            ).all()
        )
        for t in tags:
            db.delete(t)

    db.add(
        HuntActivity(
            hunt_id=hunt_id,
            candidate_id=None,
            activity_type="pass",
            description=f"Passed '{name}' — removed from hunt and logged to playbook.",
            metadata_json=json.dumps({"playbook_entry_id": entry.id, "note": note}),
        )
    )
    db.flush()
    db.delete(hc)
    if commit:
        db.commit()
    else:
        db.flush()

    return {
        "status": "success",
        "action": "pass",
        "playbook_entry_id": entry.id,
        "candidate_name": name,
    }


ROGUE_TAG = "Rogue"
ROGUE_TAG_COLOR = "#e85d4c"


def mark_candidate_rogue(
    db: Session,
    candidate_id: int,
    *,
    note: Optional[str] = None,
    author_name: str = "Recruiter",
) -> Dict[str, Any]:
    """Tag a master candidate as Rogue (bad-fit / wrong profile) and log to playbook."""
    from app.candidates.models import Candidate
    from app.candidates.service import add_candidate_tag
    from app.hunts.web_sourcing import get_hunt_labels_for_candidates

    cand = db.get(Candidate, candidate_id)
    if not cand:
        return {"status": "error", "error": "Candidate not found"}

    existing = db.scalars(
        select(CandidateTag).where(
            CandidateTag.candidate_id == candidate_id,
            CandidateTag.tag_name == ROGUE_TAG,
        ).limit(1)
    ).first()
    if not existing:
        add_candidate_tag(db, candidate_id, ROGUE_TAG, color=ROGUE_TAG_COLOR)

    hunt_titles = get_hunt_labels_for_candidates(db, [candidate_id]).get(candidate_id, [])
    role_hint = cand.current_title or (hunt_titles[0] if hunt_titles else None)
    entry = _create_entry(
        db,
        entry_type="pass",
        role_context=role_hint,
        candidate_name=cand.full_name,
        candidate_title=cand.current_title,
        candidate_id=cand.id,
        hunt_title=hunt_titles[0] if hunt_titles else None,
        note=note or "Marked as rogue / bad-fit profile.",
        author_name=author_name,
        metadata={"reason": "rogue", "hunts": hunt_titles},
    )
    return {
        "status": "success",
        "action": "rogue",
        "playbook_entry_id": entry.id,
        "candidate_id": candidate_id,
    }


def clear_candidate_rogue(db: Session, candidate_id: int) -> Dict[str, Any]:
    """Remove the Rogue tag from a candidate (does not delete playbook history)."""
    tags = list(
        db.scalars(
            select(CandidateTag).where(
                CandidateTag.candidate_id == candidate_id,
                CandidateTag.tag_name == ROGUE_TAG,
            )
        ).all()
    )
    if not tags:
        return {"status": "success", "action": "clear_rogue", "removed": 0}
    for t in tags:
        db.delete(t)
    db.commit()
    return {"status": "success", "action": "clear_rogue", "removed": len(tags)}
