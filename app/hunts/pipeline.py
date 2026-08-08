"""Pipeline orchestration service for moving candidates across stages."""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from app.hunts.models import TalentHunt, HuntStage, HuntCandidate, HuntActivity


def move_candidate_stage(
    db: Session, candidate_id: int, new_stage_id: int
) -> Optional[HuntCandidate]:
    """Move a candidate to a new stage in the pipeline and record activity."""
    candidate = db.get(HuntCandidate, candidate_id)
    if not candidate:
        return None

    new_stage = db.get(HuntStage, new_stage_id)
    if not new_stage or new_stage.hunt_id != candidate.hunt_id:
        return None

    old_stage_name = candidate.stage.name if candidate.stage else "Unassigned"
    candidate.stage_id = new_stage_id

    activity = HuntActivity(
        hunt_id=candidate.hunt_id,
        candidate_id=candidate.id,
        activity_type="stage_change",
        description=f"Moved candidate '{candidate.full_name}' from {old_stage_name} -> {new_stage.name}.",
    )
    db.add(activity)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise
    db.refresh(candidate)
    return candidate


def add_candidate_to_hunt(
    db: Session,
    hunt_id: int,
    full_name: str,
    candidate_id: Optional[int] = None,
    stage_id: Optional[int] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    current_title: Optional[str] = None,
    current_company: Optional[str] = None,
    location: Optional[str] = None,
    match_score: Optional[float] = None,
    ai_summary: Optional[str] = None,
    notes: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    github_url: Optional[str] = None,
) -> HuntCandidate:
    """Add a new candidate to a hunt pipeline."""
    if not stage_id:
        stmt = select(HuntStage).where(HuntStage.hunt_id == hunt_id).order_by(HuntStage.position)
        first_stage = db.scalars(stmt).first()
        stage_id = first_stage.id if first_stage else None

    candidate = HuntCandidate(
        hunt_id=hunt_id,
        candidate_id=candidate_id,
        stage_id=stage_id,
        full_name=full_name,
        email=email,
        phone=phone,
        current_title=current_title,
        current_company=current_company,
        location=location,
        match_score=match_score,
        ai_summary=ai_summary,
        notes=notes,
        linkedin_url=linkedin_url,
        github_url=github_url,
    )
    
    # Check if already exists to prevent IntegrityError
    stmt = select(HuntCandidate).where(HuntCandidate.hunt_id == hunt_id, HuntCandidate.candidate_id == candidate_id)
    existing_hc = db.scalars(stmt).first()
    if existing_hc:
        return existing_hc

    db.add(candidate)
    try:
        db.flush()
    except Exception as e:
        db.rollback()
        raise

    activity = HuntActivity(
        hunt_id=hunt_id,
        candidate_id=candidate.id,
        activity_type="candidate_added",
        description=f"Added candidate '{full_name}' ({current_title or 'Candidate'}) to hunt.",
    )
    db.add(activity)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise
    db.refresh(candidate)
    return candidate


def get_pipeline_data(db: Session, hunt_id: int) -> Dict[str, Any]:
    """Retrieve full pipeline structured data for rendering Kanban board."""
    stmt = select(TalentHunt).options(joinedload(TalentHunt.stages), joinedload(TalentHunt.candidates)).where(TalentHunt.id == hunt_id)
    hunt = db.scalars(stmt).unique().first()
    if not hunt:
        return {}

    stages_data = []
    for stage in sorted(hunt.stages, key=lambda s: s.position):
        candidates = [c for c in hunt.candidates if c.stage_id == stage.id]
        stages_data.append({
            "id": stage.id,
            "name": stage.name,
            "position": stage.position,
            "color": stage.color or "#00d4aa",
            "is_terminal": stage.is_terminal,
            "candidates": candidates,
            "count": len(candidates),
        })

    return {
        "hunt_id": hunt.id,
        "hunt_title": hunt.title,
        "target_role": hunt.target_role,
        "status": hunt.status,
        "stages": stages_data,
        "total_candidates": len(hunt.candidates),
    }


def add_stage_to_hunt(
    db: Session, hunt_id: int, name: str, color: Optional[str] = "#00d4aa"
) -> HuntStage:
    """Add a custom stage to a hunt pipeline."""
    stmt = select(HuntStage).where(HuntStage.hunt_id == hunt_id)
    existing_stages = list(db.scalars(stmt).all())
    next_pos = max([s.position for s in existing_stages], default=-1) + 1

    stage = HuntStage(
        hunt_id=hunt_id,
        name=name,
        position=next_pos,
        color=color,
    )
    db.add(stage)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise
    db.refresh(stage)
    return stage


def remove_candidate(db: Session, candidate_id: int) -> bool:
    """Remove a candidate from a pipeline."""
    candidate = db.get(HuntCandidate, candidate_id)
    if not candidate:
        return False
    db.delete(candidate)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise
    return True
