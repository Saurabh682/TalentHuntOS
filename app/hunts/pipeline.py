"""Pipeline orchestration service for moving candidates across stages."""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import select

from app.hunts.models import TalentHunt, HuntStage, HuntCandidate, HuntActivity
from app.candidates.models import Candidate, CandidateTag


def hunt_tag_name(hunt_title: str) -> str:
    return f"Hunt: {(hunt_title or '').strip()}"


def list_active_hunt_candidates(db: Session, hunt_id: Optional[int] = None) -> List[HuntCandidate]:
    """Canonical pipeline rows backed by a visible master Candidate record."""
    stmt = (
        select(HuntCandidate)
        .join(Candidate, HuntCandidate.candidate_id == Candidate.id)
        .options(joinedload(HuntCandidate.candidate), joinedload(HuntCandidate.stage))
        .where(Candidate.status != "Archived")
    )
    if hunt_id is not None:
        stmt = stmt.where(HuntCandidate.hunt_id == hunt_id)
    return list(db.scalars(stmt).unique().all())


def strip_hunt_tag(db: Session, candidate_id: Optional[int], hunt_title: str) -> int:
    """Remove ``Hunt: {title}`` tags from a master candidate. Returns deleted count."""
    if not candidate_id or not hunt_title:
        return 0
    tag = hunt_tag_name(hunt_title)
    rows = list(
        db.scalars(
            select(CandidateTag).where(
                CandidateTag.candidate_id == candidate_id,
                CandidateTag.tag_name == tag,
            )
        ).all()
    )
    for t in rows:
        db.delete(t)
    return len(rows)


def reconcile_hunt_from_tags(db: Session, hunt_id: int) -> Dict[str, Any]:
    """Re-link Candidates tagged ``Hunt: {title}`` onto the pipeline (and drop OOB tags).

    Fixes the common drift: people still show on Candidates with a hunt tag after
    clear/purge removed their Kanban enrollment — so the hunt card showed 1 while
    the pool showed many.
    """
    from app.hunts.experience import (
        estimate_years_from_text,
        experience_within_range,
        band_is_configured,
    )

    hunt = db.get(TalentHunt, hunt_id)
    if not hunt:
        return {"status": "error", "error": f"Hunt {hunt_id} not found"}

    tag = hunt_tag_name(hunt.title)
    sc = hunt.search_config
    exp_min = sc.experience_years_min if sc else None
    exp_max = sc.experience_years_max if sc else None
    require_years = band_is_configured(exp_min, exp_max)
    hunt_location = (hunt.location or "").strip() or "India"
    if sc and sc.locations:
        hunt_location = (sc.locations or hunt_location).strip() or hunt_location

    tagged = list(
        db.scalars(
            select(Candidate)
            .options(selectinload(Candidate.profile), selectinload(Candidate.tags))
            .join(CandidateTag, CandidateTag.candidate_id == Candidate.id)
            .where(CandidateTag.tag_name == tag, Candidate.status != "Archived")
        ).all()
    )

    enrolled_ids = {
        hc.candidate_id
        for hc in db.scalars(
            select(HuntCandidate).where(HuntCandidate.hunt_id == hunt_id)
        ).all()
        if hc.candidate_id
    }

    linked = 0
    stripped = 0
    already = 0

    from app.hunts.location import location_matches_target

    for cand in tagged:
        years = cand.experience_years
        summary = cand.profile.summary if cand.profile else ""
        resume = cand.profile.resume_text if cand.profile else ""
        if years is None:
            years = estimate_years_from_text(
                cand.current_title or "",
                summary or "",
                resume or "",
            )
        ok = experience_within_range(
            years=years,
            exp_min=exp_min,
            exp_max=exp_max,
            title=cand.current_title,
            reject_unknown=require_years,
        )
        loc_ok, _ = location_matches_target(
            candidate_location=cand.location,
            target_location=hunt_location,
            profile_url=cand.linkedin_url or "",
            page_text=f"{summary or ''} {resume or ''}",
            reject_unknown=True,
        )
        if not ok or not loc_ok:
            stripped += strip_hunt_tag(db, cand.id, hunt.title)
            # Also drop pipeline row if somehow still enrolled
            if cand.id in enrolled_ids:
                for hc in db.scalars(
                    select(HuntCandidate).where(
                        HuntCandidate.hunt_id == hunt_id,
                        HuntCandidate.candidate_id == cand.id,
                    )
                ).all():
                    db.delete(hc)
            continue

        if cand.id in enrolled_ids:
            already += 1
            continue

        add_candidate_to_hunt(
            db,
            hunt_id=hunt_id,
            full_name=cand.full_name,
            candidate_id=cand.id,
            current_title=cand.current_title,
            current_company=cand.current_company,
            location=cand.location,
            linkedin_url=cand.linkedin_url,
            match_score=70.0,
            ai_summary=f"Re-linked from Candidates tag '{tag}'.",
            source_platform="relink",
        )
        linked += 1
        enrolled_ids.add(cand.id)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    pipeline_n = len(list_active_hunt_candidates(db, hunt_id))

    return {
        "status": "success",
        "hunt_id": hunt_id,
        "linked": linked,
        "stripped_oob": stripped,
        "already_enrolled": already,
        "pipeline_count": pipeline_n,
    }


def move_candidate_stage(
    db: Session,
    candidate_id: int,
    new_stage_id: int,
    *,
    actor_type: str = "application",
    session_id: Optional[str] = None,
) -> Optional[HuntCandidate]:
    """Move a candidate to a new stage and record a seven-day undo action."""
    from app.actions.history import record_action

    candidate = db.get(HuntCandidate, candidate_id)
    if not candidate:
        return None

    new_stage = db.get(HuntStage, new_stage_id)
    if not new_stage or new_stage.hunt_id != candidate.hunt_id:
        return None

    old_stage_id = candidate.stage_id
    old_stage_name = candidate.stage.name if candidate.stage else "Unassigned"
    if old_stage_id == new_stage_id:
        return candidate
    candidate.stage_id = new_stage_id

    activity = HuntActivity(
        hunt_id=candidate.hunt_id,
        candidate_id=candidate.id,
        activity_type="stage_change",
        description=f"Moved candidate '{candidate.full_name}' from {old_stage_name} -> {new_stage.name}.",
    )
    db.add(activity)

    try:
        record_action(
            db,
            action_type="move_pipeline_candidate",
            summary=(
                f"Moved {candidate.full_name} from {old_stage_name} to {new_stage.name}"
            ),
            payload={
                "hunt_candidate_id": candidate.id,
                "from_stage_id": old_stage_id,
                "to_stage_id": new_stage_id,
            },
            undo_payload={
                "hunt_candidate_id": candidate.id,
                "stage_id": old_stage_id,
                "stage_name": old_stage_name,
            },
            actor_type=actor_type,
            session_id=session_id,
        )
    except Exception:
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
    source_platform: Optional[str] = None,
    source_query: Optional[str] = None,
    commit: bool = True,
) -> HuntCandidate:
    """Add a canonical master Candidate to a hunt pipeline."""
    if candidate_id is None:
        from app.candidates.service import create_candidate

        master = create_candidate(
            db,
            full_name=full_name,
            email=email,
            phone=phone,
            location=location,
            current_title=current_title,
            current_company=current_company,
            linkedin_url=linkedin_url,
            github_url=github_url,
            status="Sourced",
            summary=ai_summary,
        )
        if master is None:
            raise ValueError("Could not create or resolve the master Candidate record")
        candidate_id = master.id

    if not stage_id:
        stmt = select(HuntStage).where(HuntStage.hunt_id == hunt_id).order_by(HuntStage.position)
        first_stage = db.scalars(stmt).first()
        stage_id = first_stage.id if first_stage else None

    # Check if already exists to prevent IntegrityError
    if candidate_id is not None:
        stmt = select(HuntCandidate).where(
            HuntCandidate.hunt_id == hunt_id, HuntCandidate.candidate_id == candidate_id
        )
        existing_hc = db.scalars(stmt).first()
        if existing_hc:
            if source_platform and not existing_hc.source_platform:
                existing_hc.source_platform = source_platform
            if source_query and not existing_hc.source_query:
                existing_hc.source_query = source_query
            if commit:
                try:
                    db.commit()
                    db.refresh(existing_hc)
                except Exception:
                    db.rollback()
            else:
                db.flush()
            return existing_hc

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
        source_platform=source_platform,
        source_query=source_query,
    )

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

    if commit:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            raise
    else:
        db.flush()
    db.refresh(candidate)
    return candidate


def get_pipeline_data(db: Session, hunt_id: int) -> Dict[str, Any]:
    """Retrieve full pipeline structured data for rendering Kanban board."""
    stmt = select(TalentHunt).options(joinedload(TalentHunt.stages)).where(TalentHunt.id == hunt_id)
    hunt = db.scalars(stmt).unique().first()
    if not hunt:
        return {}

    active_candidates = list_active_hunt_candidates(db, hunt_id)
    stages_data = []
    for stage in sorted(hunt.stages, key=lambda s: s.position):
        candidates = [c for c in active_candidates if c.stage_id == stage.id]
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
        "total_candidates": len(active_candidates),
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
    """Remove a candidate from a pipeline (by HuntCandidate row id)."""
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


def clear_hunt_candidates(
    db: Session,
    hunt_id: int,
    *,
    name_contains: Optional[str] = None,
    stage_name: Optional[str] = None,
    actor_type: str = "application",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Remove hunt pipeline enrollments (does not delete master Candidate profiles).

    Optional filters:
    - name_contains: case-insensitive substring match on full_name
    - stage_name: only remove from a stage (e.g. 'Sourced')
    """
    hunt = db.get(TalentHunt, hunt_id)
    if not hunt:
        return {"removed": 0, "error": f"Hunt {hunt_id} not found"}

    stmt = select(HuntCandidate).where(HuntCandidate.hunt_id == hunt_id)
    rows = list(db.scalars(stmt).all())
    removed_names: List[str] = []
    removed_rows: List[Dict[str, Any]] = []
    needle = (name_contains or "").strip().lower()
    stage_needle = (stage_name or "").strip().lower()

    for hc in rows:
        if needle and needle not in (hc.full_name or "").lower():
            continue
        if stage_needle:
            stage = db.get(HuntStage, hc.stage_id) if hc.stage_id else None
            if not stage or stage_needle not in (stage.name or "").lower():
                continue
        removed_names.append(hc.full_name or f"id:{hc.id}")
        removed_rows.append({
            "id": hc.id,
            "hunt_id": hc.hunt_id,
            "candidate_id": hc.candidate_id,
            "stage_id": hc.stage_id,
            "full_name": hc.full_name,
            "email": hc.email,
            "phone": hc.phone,
            "current_title": hc.current_title,
            "current_company": hc.current_company,
            "location": hc.location,
            "linkedin_url": hc.linkedin_url,
            "github_url": hc.github_url,
            "portfolio_url": hc.portfolio_url,
            "match_score": hc.match_score,
            "ai_summary": hc.ai_summary,
            "notes": hc.notes,
            "source_platform": hc.source_platform,
            "source_query": hc.source_query,
            "status": hc.status,
            "created_at": hc.created_at.isoformat() if hc.created_at else None,
            "updated_at": hc.updated_at.isoformat() if hc.updated_at else None,
            "activities": [
                {
                    "id": activity.id,
                    "activity_type": activity.activity_type,
                    "description": activity.description,
                    "metadata_json": activity.metadata_json,
                    "created_at": activity.created_at.isoformat() if activity.created_at else None,
                }
                for activity in hc.activities
            ],
        })
        if hunt and hc.candidate_id:
            strip_hunt_tag(db, hc.candidate_id, hunt.title)
        db.delete(hc)

    try:
        if removed_rows:
            from app.actions.history import record_action

            record_action(
                db,
                action_type="clear_hunt_candidates",
                summary=f"Removed {len(removed_rows)} candidate(s) from {hunt.title}",
                payload={
                    "hunt_id": hunt_id,
                    "candidate_count": len(removed_rows),
                    "name_contains": name_contains,
                    "stage_name": stage_name,
                },
                undo_payload={
                    "hunt_id": hunt_id,
                    "hunt_title": hunt.title,
                    "rows": removed_rows,
                },
                actor_type=actor_type,
                session_id=session_id,
            )
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "removed": len(removed_names),
        "hunt_id": hunt_id,
        "hunt_title": hunt.title,
        "names": removed_names[:50],
    }
