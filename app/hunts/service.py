"""CRUD and management service for Talent Hunt campaigns."""

import json
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.hunts.models import (
    TalentHunt,
    HuntSearchConfig,
    HuntStage,
    HuntCandidate,
    HuntActivity,
)
from app.config.constants import DEFAULT_PIPELINE_STAGES

logger = logging.getLogger(__name__)

STAGE_COLOR_MAP: Dict[str, str] = {
    "Sourced": "#00d4aa",
    "Contacted": "#3b82f6",
    "Screening": "#a855f7",
    "Interview": "#f5a623",
    "Offer": "#10b981",
    "Hired": "#22c55e",
    "Rejected": "#ef4444",
}


def create_hunt(
    db: Session,
    title: str,
    description: Optional[str] = None,
    target_role: Optional[str] = None,
    location: Optional[str] = None,
    salary_range: Optional[str] = None,
    search_config: Optional[Dict[str, Any]] = None,
    custom_stages: Optional[List[str]] = None,
    commit: bool = True,
) -> Optional[TalentHunt]:
    """Create a new Talent Hunt campaign with search config and pipeline stages.
    
    Args:
        db (Session): Database session object.
        title (str): Title of the hunt.
        description (Optional[str]): Description of the hunt. Defaults to None.
        target_role (Optional[str]): Target role. Defaults to None.
        location (Optional[str]): Location of the role. Defaults to None.
        salary_range (Optional[str]): Expected salary range. Defaults to None.
        search_config (Optional[Dict[str, Any]]): Search configuration dictionary. Defaults to None.
        custom_stages (Optional[List[str]]): Custom pipeline stages. Defaults to None.

    Returns:
        Optional[TalentHunt]: The newly created TalentHunt object, or None if an error occurs.
    """
    try:
        hunt = TalentHunt(
            title=title,
            description=description,
            target_role=target_role,
            location=location,
            salary_range=salary_range,
            status="Active",
        )
        db.add(hunt)
        db.flush()

        if search_config:
            try:
                target_platforms = search_config.get("target_platforms")
                if isinstance(target_platforms, list):
                    parsed_platforms: Optional[str] = json.dumps(target_platforms)
                else:
                    parsed_platforms = target_platforms
            except (TypeError, ValueError) as e:
                logger.error(f"Error parsing target_platforms for hunt {hunt.id}: {e}")
                parsed_platforms = None

            keywords_val = search_config.get("keywords")
            min_exp = search_config.get("min_experience")
            if min_exp and not keywords_val:
                keywords_val = f"Exp: {min_exp}"
            elif min_exp and keywords_val:
                keywords_val = f"Exp: {min_exp} | {keywords_val}"

            from app.hunts.experience import parse_experience_range

            exp_min = search_config.get("experience_years_min")
            exp_max = search_config.get("experience_years_max")
            if (exp_min is None or exp_max is None) and min_exp:
                parsed_min, parsed_max = parse_experience_range(str(min_exp))
                if exp_min is None:
                    exp_min = parsed_min
                if exp_max is None:
                    exp_max = parsed_max

            cfg = HuntSearchConfig(
                hunt_id=hunt.id,
                keywords=keywords_val,
                required_skills=search_config.get("required_skills"),
                preferred_skills=search_config.get("preferred_skills"),
                experience_years_min=exp_min,
                experience_years_max=exp_max,
                locations=search_config.get("locations"),
                industry=search_config.get("industry"),
                remote_policy=search_config.get("remote_policy"),
                target_platforms=parsed_platforms,
            )
            db.add(cfg)

        stage_names = custom_stages if custom_stages else DEFAULT_PIPELINE_STAGES
        for pos, stage_name in enumerate(stage_names):
            stage = HuntStage(
                hunt_id=hunt.id,
                name=stage_name,
                position=pos,
                color=STAGE_COLOR_MAP.get(stage_name, "#00d4aa"),
                is_terminal=(stage_name in ["Hired", "Rejected"]),
            )
            db.add(stage)

        activity = HuntActivity(
            hunt_id=hunt.id,
            activity_type="created",
            description=f"Created Talent Hunt '{title}' with target role '{target_role or title}'.",
        )
        db.add(activity)

        if commit:
            db.commit()
        else:
            db.flush()
        db.refresh(hunt)
        return hunt
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error while creating hunt '{title}': {e}")
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error while creating hunt '{title}': {e}")
        return None


def get_hunt(db: Session, hunt_id: int) -> Optional[TalentHunt]:
    """Retrieve a single Talent Hunt by ID.
    
    Args:
        db (Session): Database session object.
        hunt_id (int): ID of the TalentHunt to retrieve.

    Returns:
        Optional[TalentHunt]: The retrieved TalentHunt object, or None if not found or an error occurs.
    """
    try:
        stmt = select(TalentHunt).options(
            joinedload(TalentHunt.candidates),
            joinedload(TalentHunt.stages),
            joinedload(TalentHunt.search_config),
        ).where(TalentHunt.id == hunt_id)
        return db.scalars(stmt).unique().first()
    except SQLAlchemyError as e:
        logger.error(f"Database error while retrieving hunt {hunt_id}: {e}")
        return None


def list_hunts(
    db: Session,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[TalentHunt]:
    """List all Talent Hunt campaigns with optional status filtering.
    
    Args:
        db (Session): Database session object.
        status (Optional[str]): Filter by status. Defaults to None.
        skip (int): Number of records to skip. Defaults to 0.
        limit (int): Maximum number of records to return. Defaults to 100.

    Returns:
        List[TalentHunt]: A list of TalentHunt objects matching the criteria.
    """
    try:
        stmt = select(TalentHunt)
        if status and status != "All":
            stmt = stmt.where(TalentHunt.status == status)
        else:
            stmt = stmt.where(TalentHunt.status != "Archived")
        stmt = stmt.order_by(TalentHunt.created_at.desc()).offset(skip).limit(limit)
        return list(db.scalars(stmt).all())
    except SQLAlchemyError as e:
        logger.error(f"Database error while listing hunts: {e}")
        return []


def update_hunt(db: Session, hunt_id: int, **kwargs: Any) -> Optional[TalentHunt]:
    """Update fields on a Talent Hunt.
    
    Args:
        db (Session): Database session object.
        hunt_id (int): ID of the TalentHunt to update.
        **kwargs (Any): Fields to update on the TalentHunt.

    Returns:
        Optional[TalentHunt]: The updated TalentHunt object, or None if not found or an error occurs.
    """
    try:
        hunt = get_hunt(db, hunt_id)
        if not hunt:
            logger.warning(f"Hunt {hunt_id} not found for update.")
            return None

        for key, value in kwargs.items():
            if key in ("search_config", "candidates", "stages"):
                continue
            if hasattr(hunt, key) and value is not None:
                setattr(hunt, key, value)

        db.commit()
        db.refresh(hunt)
        return hunt
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error while updating hunt {hunt_id}: {e}")
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error while updating hunt {hunt_id}: {e}")
        return None


def delete_hunt(
    db: Session,
    hunt_id: int,
    *,
    actor_type: str = "ui",
    session_id: str | None = None,
) -> bool:
    """Archive a Talent Hunt campaign with a seven-day undo record.
    
    Args:
        db (Session): Database session object.
        hunt_id (int): ID of the TalentHunt to delete.

    Returns:
        bool: True if deleted successfully, False if not found or an error occurs.
    """
    try:
        hunt = get_hunt(db, hunt_id)
        if not hunt:
            logger.warning(f"Hunt {hunt_id} not found for deletion.")
            return False

        if hunt.status == "Archived":
            return False

        from app.actions.history import record_action

        previous_status = hunt.status
        hunt.status = "Archived"
        record_action(
            db,
            action_type="archive_hunt",
            summary=f"Archived Talent Hunt '{hunt.title}'",
            actor_type=actor_type,
            session_id=session_id,
            payload={"hunt_id": hunt.id, "title": hunt.title},
            undo_payload={"hunt_id": hunt.id, "previous_status": previous_status},
        )
        return True
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error while deleting hunt {hunt_id}: {e}")
        return False
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error while deleting hunt {hunt_id}: {e}")
        return False


def get_hunt_metrics(db: Session, hunt_id: int, *, reconcile: bool = True) -> Dict[str, Any]:
    """Calculate and return key performance metrics for a specific hunt.

    Args:
        db (Session): Database session object.
        hunt_id (int): ID of the TalentHunt.
        reconcile: When True, re-link tagged Candidates onto the pipeline so the
            card count matches the Candidates pool for this hunt.

    Returns:
        Dict[str, Any]: A dictionary containing key metrics.
    """
    try:
        if reconcile:
            try:
                from app.hunts.pipeline import reconcile_hunt_from_tags
                reconcile_hunt_from_tags(db, hunt_id)
                db.expire_all()
            except Exception as sync_exc:
                logger.warning("Hunt reconcile failed for %s: %s", hunt_id, sync_exc)

        hunt = get_hunt(db, hunt_id)
        if not hunt:
            logger.warning(f"Hunt {hunt_id} not found for metrics calculation.")
            return {}

        from app.hunts.pipeline import list_active_hunt_candidates

        active_candidates = list_active_hunt_candidates(db, hunt_id)
        total_candidates = len(active_candidates)
        
        stage_breakdown: Dict[str, int] = {}
        for stage in hunt.stages:
            stage_breakdown[stage.name] = len([c for c in active_candidates if c.stage_id == stage.id])

        scores = [c.match_score for c in active_candidates if c.match_score is not None]
        if scores:
            raw_avg = sum(scores) / len(scores)
            avg_score = round(raw_avg * 100 if raw_avg <= 1.0 else raw_avg, 1)
        else:
            avg_score = 0.0
        hired_count = stage_breakdown.get("Hired", 0)

        return {
            "hunt_id": hunt_id,
            "title": hunt.title,
            "status": hunt.status,
            "total_candidates": total_candidates,
            "hired_count": hired_count,
            "avg_match_score": avg_score,
            "stage_counts": stage_breakdown,
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error while calculating metrics for hunt {hunt_id}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error while calculating metrics for hunt {hunt_id}: {e}")
        return {}
