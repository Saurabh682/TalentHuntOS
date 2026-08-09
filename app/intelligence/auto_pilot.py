"""APScheduler background automation engine for TalentHunt OS continuous candidate sourcing."""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    APSCHEDULER_AVAILABLE = True
except ImportError:
    BackgroundScheduler = None
    APSCHEDULER_AVAILABLE = False

from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select

from app.infrastructure.db import SessionFactory
from app.hunts.models import TalentHunt, HuntSearchConfig, HuntStage, HuntCandidate, HuntActivity
from app.candidates.models import Candidate
from app.intelligence.candidate_dna import generate_candidate_dna

logger = logging.getLogger("talenthunt.intelligence.auto_pilot")


def _calculate_candidate_hunt_match(cand: Candidate, search_config: Optional[HuntSearchConfig], target_role: Optional[str]) -> float:
    """Score candidate match quality against search configuration (0.0 to 1.0).

    Starts at 0 — candidates with no title/skill overlap must not auto-match.
    """
    score = 0.0
    evidence = 0

    cand_title = (cand.current_title or "").lower()
    role_target = (target_role or "").lower().strip()
    role_tokens = [w for w in re.split(r"[^a-z0-9]+", role_target) if len(w) > 2]

    # 1. Title match boost (required signal for autopilot)
    if role_target and cand_title:
        if role_target in cand_title or cand_title in role_target:
            score += 0.45
            evidence += 2
        else:
            token_hits = sum(1 for w in role_tokens if w in cand_title)
            if token_hits >= 2:
                score += 0.35
                evidence += 2
            elif token_hits == 1:
                score += 0.15
                evidence += 1

    # 2. Skills match boost
    if search_config:
        req_skills = [s.strip().lower() for s in (search_config.required_skills or "").split(",") if s.strip()]
        pref_skills = [s.strip().lower() for s in (search_config.preferred_skills or "").split(",") if s.strip()]

        cand_skills = []
        if cand.profile and cand.profile.skills_json:
            try:
                cand_skills = [s.lower() for s in json.loads(cand.profile.skills_json)]
            except Exception:
                pass

        skill_blob = " ".join(cand_skills) + " " + cand_title

        if req_skills:
            matched_req = sum(1 for rs in req_skills if rs in skill_blob)
            if matched_req:
                score += (matched_req / len(req_skills)) * 0.35
                evidence += matched_req

        if pref_skills:
            matched_pref = sum(1 for ps in pref_skills if ps in skill_blob)
            if matched_pref:
                score += (matched_pref / len(pref_skills)) * 0.15
                evidence += 1

        # 3. Experience years — hard reject outside band
        if search_config and (
            search_config.experience_years_min is not None
            or search_config.experience_years_max is not None
        ):
            from app.hunts.experience import experience_within_range

            if not experience_within_range(
                years=cand.experience_years,
                exp_min=search_config.experience_years_min,
                exp_max=search_config.experience_years_max,
                title=cand.current_title,
            ):
                return 0.0
            if cand.experience_years is not None:
                score += 0.08
                evidence += 1

    # No meaningful overlap → hard reject
    if evidence < 1:
        return 0.0

    return round(min(1.0, score), 2)


def run_autopilot_hunt_job(hunt_id: int) -> Dict[str, Any]:
    """Execute AutoPilot scan for a specific Talent Hunt campaign."""
    db: Session = SessionFactory()
    try:
        hunt_stmt = select(TalentHunt).where(TalentHunt.id == hunt_id)
        hunt = db.scalars(hunt_stmt).first()
        if not hunt or hunt.status != "Active":
            logger.info(f"AutoPilot skipped hunt {hunt_id}: Hunt not found or inactive.")
            autopilot_scheduler.remove_hunt_job(hunt_id)
            return {"status": "skipped", "reason": "Hunt inactive or not found"}

        search_config = hunt.search_config
        target_role = hunt.target_role or hunt.title

        # Ensure default stages exist for this hunt
        stage_stmt = select(HuntStage).where(HuntStage.hunt_id == hunt_id).order_by(HuntStage.position)
        stages = list(db.scalars(stage_stmt).all())
        if not stages:
            default_stages = ["Sourced", "Screening", "Interview", "Offer", "Hired"]
            stages = []
            for idx, st_name in enumerate(default_stages):
                st = HuntStage(hunt_id=hunt_id, name=st_name, position=idx, color="teal" if idx == 0 else "blue")
                db.add(st)
            db.flush()
            stage_stmt = select(HuntStage).where(HuntStage.hunt_id == hunt_id).order_by(HuntStage.position)
            stages = list(db.scalars(stage_stmt).all())

        first_stage = stages[0] if stages else None
        stage_id = first_stage.id if first_stage else None

        # Get existing candidates linked to hunt to prevent duplicates
        existing_cand_stmt = select(HuntCandidate).where(HuntCandidate.hunt_id == hunt_id)
        existing_cands = list(db.scalars(existing_cand_stmt).all())
        existing_cand_ids = set(c.candidate_id for c in existing_cands if c.candidate_id)
        existing_names = set(c.full_name.lower() for c in existing_cands if c.full_name)

        # Fetch active candidate pool (include Sourced, Active, Passive candidates)
        cand_stmt = select(Candidate).options(
            selectinload(Candidate.profile),
            selectinload(Candidate.experiences),
            selectinload(Candidate.educations)
        ).where(Candidate.status != "Archived").limit(500)
        all_candidates = db.scalars(cand_stmt).all()

        scanned_count = len(all_candidates)
        matched_count = 0
        added_count = 0

        for cand in all_candidates:
            if cand.id in existing_cand_ids or (cand.full_name and cand.full_name.lower() in existing_names):
                continue

            match_score = _calculate_candidate_hunt_match(cand, search_config, target_role)

            # Require real overlap (old 0.40 base score matched everyone)
            if match_score >= 0.55:
                matched_count += 1
                dna = generate_candidate_dna(cand)
                ai_summary = (
                    f"AutoPilot matched candidate '{cand.full_name}' with {int(match_score * 100)}% relevance. "
                    f"Seniority index: {dna.seniority_index}, Stability: {dna.tenure_stability_score}. "
                    f"Skills: {', '.join(dna.normalized_skills[:5]) if dna.normalized_skills else 'N/A'}."
                )

                hunt_cand = HuntCandidate(
                    hunt_id=hunt.id,
                    candidate_id=cand.id,
                    stage_id=stage_id,
                    full_name=cand.full_name,
                    email=cand.email,
                    phone=cand.phone,
                    current_title=cand.current_title,
                    current_company=cand.current_company,
                    location=cand.location,
                    linkedin_url=cand.linkedin_url,
                    github_url=cand.github_url,
                    portfolio_url=cand.portfolio_url,
                    match_score=match_score,
                    ai_summary=ai_summary,
                    status="Active",
                )
                db.add(hunt_cand)
                db.flush()

                # Tag master candidate with hunt heading so Candidates page shows the label
                try:
                    from app.candidates.service import add_candidate_tag
                    from app.candidates.models import CandidateTag
                    hunt_tag = f"Hunt: {hunt.title}"
                    has_tag = db.scalars(
                        select(CandidateTag).where(
                            CandidateTag.candidate_id == cand.id,
                            CandidateTag.tag_name == hunt_tag,
                        ).limit(1)
                    ).first()
                    if not has_tag:
                        db.add(CandidateTag(candidate_id=cand.id, tag_name=hunt_tag, color="#19d3c5"))
                except Exception as tag_exc:
                    logger.warning("Could not tag candidate %s with hunt label: %s", cand.id, tag_exc)

                activity = HuntActivity(
                    hunt_id=hunt.id,
                    candidate_id=hunt_cand.id,
                    activity_type="autopilot_match",
                    description=f"AutoPilot continuously flagged candidate {cand.full_name} ({int(match_score * 100)}% match).",
                    metadata_json=json.dumps({"match_score": match_score, "scanned_at": datetime.now(timezone.utc).isoformat()}),
                )
                db.add(activity)
                added_count += 1

        # Removed dummy candidate auto-sourcing to ensure only real profiles are added to the pipeline.

        db.commit()
        logger.info(f"AutoPilot hunt {hunt_id} completed: Scanned {scanned_count}, Matched {matched_count}, Added {added_count}")
        return {
            "status": "success",
            "hunt_id": hunt_id,
            "scanned": scanned_count,
            "matched": matched_count,
            "added": added_count,
            "candidates_sourced": added_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error during AutoPilot execution for hunt {hunt_id}: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


class AutoPilotScheduler:
    """Manager for background APScheduler hunt jobs."""

    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler() if APSCHEDULER_AVAILABLE and BackgroundScheduler else None
        self._running = False

    def start(self) -> None:
        """Start the background scheduler."""
        if not APSCHEDULER_AVAILABLE or not self.scheduler:
            logger.warning("APScheduler package not installed. AutoPilot background scheduler disabled.")
            return
        if not self._running:
            try:
                self.scheduler.start()
                self._running = True
                logger.info("AutoPilot APScheduler background worker started.")
            except Exception as e:
                logger.error(f"Failed to start AutoPilot scheduler: {e}")

    def shutdown(self) -> None:
        """Shutdown the background scheduler."""
        if self._running and self.scheduler:
            self.scheduler.shutdown(wait=False)
            self._running = False
            logger.info("AutoPilot APScheduler stopped.")

    def schedule_hunt_job(self, hunt_id: int, interval_minutes: int = 30) -> None:
        """Add or update repetitive search job for a hunt."""
        self.start()
        if not self.scheduler:
            logger.warning(f"Cannot schedule hunt job {hunt_id}: APScheduler unavailable.")
            return
        job_id = f"autopilot_hunt_{hunt_id}"
        self.scheduler.add_job(
            func=run_autopilot_hunt_job,
            trigger="interval",
            minutes=interval_minutes,
            args=[hunt_id],
            id=job_id,
            replace_existing=True,
        )
        logger.info(f"Scheduled AutoPilot job '{job_id}' every {interval_minutes} minutes.")

    def remove_hunt_job(self, hunt_id: int) -> None:
        """Remove background search job for a hunt."""
        if not self.scheduler:
            return
        job_id = f"autopilot_hunt_{hunt_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed AutoPilot job '{job_id}'.")

    def get_active_jobs(self) -> List[Dict[str, Any]]:
        """Get summary list of active scheduled hunt jobs."""
        if not self._running:
            return []
        jobs = []
        for j in self.scheduler.get_jobs():
            jobs.append({
                "job_id": j.id,
                "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None,
                "trigger": str(j.trigger),
            })
        return jobs

    def run_hunt_now(self, hunt_id: int) -> Dict[str, Any]:
        """Trigger an immediate AutoPilot scan for a hunt."""
        return run_autopilot_hunt_job(hunt_id)


autopilot_scheduler = AutoPilotScheduler()


def start_global_autopilot(interval_minutes: int = 30) -> None:
    """Scan database for active hunts and register autopilot background jobs."""
    autopilot_scheduler.start()
    db: Session = SessionFactory()
    try:
        active_hunts_stmt = select(TalentHunt).where(TalentHunt.status == "Active")
        active_hunts = db.scalars(active_hunts_stmt).all()
        for hunt in active_hunts:
            autopilot_scheduler.schedule_hunt_job(hunt.id, interval_minutes=interval_minutes)
        logger.info(f"Global AutoPilot initialized with {len(active_hunts)} active hunts.")
    except Exception as e:
        logger.error(f"Error starting global autopilot: {e}")
    finally:
        db.close()
