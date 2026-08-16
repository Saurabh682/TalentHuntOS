"""Analytics & Intelligence Calculation Service for TalentHunt OS.

Calculates recruitment metrics, funnel progression, time-to-fill velocity,
candidate match quality, outreach performance, AI cost tracking, and trend analytics.
"""

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.candidates.models import Candidate, CandidateProfile
from app.communications.models import Communication, OutreachSequence
from app.hunts.models import HuntActivity, HuntCandidate, TalentHunt

logger = logging.getLogger(__name__)

# Standard pipeline stage order for funnel computation
DEFAULT_FUNNEL_STAGES: List[str] = [
    "Sourced",
    "Contacted",
    "Screening",
    "Interview",
    "Offer",
    "Hired",
]

AI_ACTIVITY_LABELS: Dict[str, str] = {
    "autopilot_match": "Candidate Match Scoring",
    "candidate_profile_enriched": "Profile Enrichment",
    "profile_enriched": "Profile Enrichment",
    "sourcing_completed": "Multi-Platform Talent Search",
    "talent_search": "Multi-Platform Talent Search",
    "outreach_drafted": "Outreach Drafting",
    "voice_screened": "Voice AI Screening",
}


def _recorded_ai_activities(activities: List[HuntActivity]) -> List[HuntActivity]:
    """Return only activity rows that explicitly represent an AI operation."""
    return [activity for activity in activities if activity.activity_type in AI_ACTIVITY_LABELS]


def _percent_score(value: Optional[float]) -> Optional[float]:
    """Normalize legacy 0..1 and current 0..100 match-score formats."""
    if value is None:
        return None
    score = float(value)
    return score * 100 if 0 <= score <= 1 else score


def get_kpi_summary(db: Session, hunt_id: Optional[int] = None) -> Dict[str, Any]:
    """Calculate executive KPI overview metrics.

    Args:
        db (Session): The SQLAlchemy database session.
        hunt_id (Optional[int]): The ID of a specific hunt to filter by. Defaults to None.

    Returns:
        Dict[str, Any]: A dictionary containing the KPI summary metrics.
    """
    try:
        # Hunts query
        hunts_stmt = select(TalentHunt)
        if hunt_id:
            hunts_stmt = hunts_stmt.where(TalentHunt.id == hunt_id)
        hunts = list(db.scalars(hunts_stmt).all())
        
        total_hunts = len(hunts)
        active_hunts = len([h for h in hunts if h.status == "Active"])
        completed_hunts = len([h for h in hunts if h.status in ["Completed", "Closed"]])

        # Candidates in hunts query
        from app.hunts.pipeline import list_active_hunt_candidates

        hunt_cands = list_active_hunt_candidates(db, hunt_id)

        # Global candidate count fallback if no hunt_id
        if not hunt_id:
            total_sourced = db.scalar(
                select(func.count(Candidate.id)).where(Candidate.status != "Archived")
            ) or 0
        else:
            total_sourced = len(hunt_cands)

        # Calculate hired & interviewing
        hired_count = 0
        interviewing_count = 0
        for hc in hunt_cands:
            stage_name = hc.stage.name if hc.stage else ""
            if stage_name == "Hired":
                hired_count += 1
            elif stage_name in ["Screening", "Interview", "Offer"]:
                interviewing_count += 1

        # Conversion Rate
        conversion_rate = round((hired_count / total_sourced * 100), 1) if total_sourced > 0 else 0.0

        # Time-to-fill calculation
        ttf_days = _calculate_avg_time_to_fill(hunts, hunt_cands)

        # Outreach communications query
        comm_stmt = select(Communication)
        if hunt_id:
            candidate_ids = {
                item.candidate_id for item in hunt_cands if item.candidate_id is not None
            }
            comms = (
                list(db.scalars(comm_stmt.where(Communication.candidate_id.in_(candidate_ids))).all())
                if candidate_ids
                else []
            )
        else:
            comms = list(db.scalars(comm_stmt).all())
        outbound_count = len([c for c in comms if c.direction == "outbound"])
        inbound_count = len([c for c in comms if c.direction == "inbound"])
        response_rate = round((inbound_count / outbound_count * 100), 1) if outbound_count > 0 else 0.0

        # AI Activity & Cost
        activities_stmt = select(HuntActivity)
        if hunt_id:
            activities_stmt = activities_stmt.where(HuntActivity.hunt_id == hunt_id)
        activities = list(db.scalars(activities_stmt).all())
        ai_actions = len(_recorded_ai_activities(activities))

        # Provider token/cost telemetry is not persisted yet, so reporting a cost
        # estimate here would manufacture data. Keep these values explicitly zero.
        cloud_cost_est = 0.0
        net_cost_saved = 0.0

        return {
            "total_hunts": total_hunts,
            "active_hunts": active_hunts,
            "completed_hunts": completed_hunts,
            "total_sourced": total_sourced,
            "interviewing_candidates": interviewing_count,
            "hired_candidates": hired_count,
            "conversion_rate": conversion_rate,
            "avg_time_to_fill_days": ttf_days,
            "outreach_sent": outbound_count,
            "outreach_replied": inbound_count,
            "response_rate": response_rate,
            "ai_actions": ai_actions,
            "estimated_cloud_cost": cloud_cost_est,
            "estimated_cost_saved": net_cost_saved,
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_kpi_summary: {e}", exc_info=True)
        return {}
    except Exception as e:
        logger.error(f"Unexpected error in get_kpi_summary: {e}", exc_info=True)
        return {}


def get_hunt_funnel_data(db: Session, hunt_id: Optional[int] = None) -> Dict[str, Any]:
    """Compute talent sourcing funnel breakdown and stage conversion rates.

    Args:
        db (Session): The SQLAlchemy database session.
        hunt_id (Optional[int]): The ID of a specific hunt to filter by. Defaults to None.

    Returns:
        Dict[str, Any]: A dictionary containing the talent sourcing funnel metrics.
    """
    try:
        from app.hunts.pipeline import list_active_hunt_candidates

        hunt_cands = list_active_hunt_candidates(db, hunt_id)

        # Map candidate counts by stage name
        stage_counts: Dict[str, int] = {stage: 0 for stage in DEFAULT_FUNNEL_STAGES}
        stage_counts["Rejected"] = 0

        for hc in hunt_cands:
            stage_name = hc.stage.name if hc.stage else "Sourced"
            if stage_name in stage_counts:
                stage_counts[stage_name] += 1
            else:
                stage_counts["Sourced"] += 1

        # Fallback mock distribution removed

        total_initial = sum(stage_counts.values())
        funnel_stages: List[Dict[str, Any]] = []
        prev_count = total_initial

        for stage_name in DEFAULT_FUNNEL_STAGES:
            count = stage_counts.get(stage_name, 0)
            overall_pct = round((count / total_initial * 100), 1) if total_initial > 0 else 0.0
            dropoff_pct = round(((prev_count - count) / prev_count * 100), 1) if prev_count > 0 and count < prev_count else 0.0
            
            funnel_stages.append({
                "stage": stage_name,
                "count": count,
                "overall_conversion": overall_pct,
                "dropoff_rate": dropoff_pct,
            })
            if count > 0:
                prev_count = count

        return {
            "total_candidates": total_initial,
            "stages": funnel_stages,
            "rejected_count": stage_counts.get("Rejected", 0),
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_hunt_funnel_data: {e}", exc_info=True)
        return {}
    except Exception as e:
        logger.error(f"Unexpected error in get_hunt_funnel_data: {e}", exc_info=True)
        return {}


def get_time_to_fill_metrics(db: Session, hunt_id: Optional[int] = None) -> Dict[str, Any]:
    """Compute time-to-fill metrics and stage duration bottleneck analysis.

    Args:
        db (Session): The SQLAlchemy database session.
        hunt_id (Optional[int]): The ID of a specific hunt to filter by. Defaults to None.

    Returns:
        Dict[str, Any]: A dictionary containing time-to-fill metrics.
    """
    try:
        hunts_stmt = select(TalentHunt)
        if hunt_id:
            hunts_stmt = hunts_stmt.where(TalentHunt.id == hunt_id)
        hunts = list(db.scalars(hunts_stmt).all())

        hunt_velocity_list: List[Dict[str, Any]] = []
        for h in hunts:
            from app.hunts.pipeline import list_active_hunt_candidates

            active_candidates = list_active_hunt_candidates(db, h.id)
            cands_count = len(active_candidates)
            hired = [c for c in active_candidates if c.stage and c.stage.name == "Hired"]
            hired_count = len(hired)
            
            # Calculate days open
            created_dt = h.created_at
            if created_dt:
                now_dt = datetime.now(timezone.utc) if created_dt.tzinfo is not None else datetime.now()
                days_open = max(1, (now_dt - created_dt).days)
            else:
                days_open = 1
            fill_dates = [candidate.updated_at for candidate in hired if candidate.updated_at]
            if fill_dates and created_dt:
                normalized_created = (
                    created_dt.replace(tzinfo=timezone.utc)
                    if created_dt.tzinfo is None
                    else created_dt
                )
                normalized_fills = [
                    value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
                    for value in fill_dates
                ]
                time_to_fill = max(0, (min(normalized_fills) - normalized_created).days)
            else:
                time_to_fill = None

            hunt_velocity_list.append({
                "hunt_id": h.id,
                "title": h.title,
                "target_role": h.target_role or h.title,
                "status": h.status,
                "total_candidates": cands_count,
                "hired_count": hired_count,
                "days_open": days_open,
                "time_to_fill_days": time_to_fill,
            })

        # Stage-entry timestamps are not stored, so bottleneck durations cannot be
        # computed honestly yet.
        stage_durations: Dict[str, float] = {}
        completed_durations = [
            item["time_to_fill_days"]
            for item in hunt_velocity_list
            if item["time_to_fill_days"] is not None
        ]
        avg_ttf = (
            round(sum(completed_durations) / len(completed_durations), 1)
            if completed_durations
            else 0.0
        )

        return {
            "overall_avg_time_to_fill": avg_ttf,
            "stage_bottlenecks": stage_durations,
            "hunts_velocity": hunt_velocity_list,
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_time_to_fill_metrics: {e}", exc_info=True)
        return {}
    except Exception as e:
        logger.error(f"Unexpected error in get_time_to_fill_metrics: {e}", exc_info=True)
        return {}


def get_sourcing_quality_metrics(db: Session, hunt_id: Optional[int] = None) -> Dict[str, Any]:
    """Compute candidate match score distribution and sourcing channel quality.

    Args:
        db (Session): The SQLAlchemy database session.
        hunt_id (Optional[int]): The ID of a specific hunt to filter by. Defaults to None.

    Returns:
        Dict[str, Any]: A dictionary containing metrics related to sourcing quality.
    """
    try:
        from app.hunts.pipeline import list_active_hunt_candidates

        cands = list_active_hunt_candidates(db, hunt_id)

        score_brackets: Dict[str, int] = {
            "90-100% (High Match)": 0,
            "80-89% (Good Match)": 0,
            "70-79% (Moderate Match)": 0,
            "< 70% (Low Match)": 0,
            "Unscored": 0,
        }

        for c in cands:
            score = _percent_score(c.match_score)
            if score is None:
                score_brackets["Unscored"] += 1
                continue
            if score >= 90:
                score_brackets["90-100% (High Match)"] += 1
            elif score >= 80:
                score_brackets["80-89% (Good Match)"] += 1
            elif score >= 70:
                score_brackets["70-79% (Moderate Match)"] += 1
            else:
                score_brackets["< 70% (Low Match)"] += 1

        # Sourcing channels breakdown
        channels_breakdown: Dict[str, int] = {}
        for candidate in cands:
            source = (candidate.source_platform or "Internal DB").strip().title()
            channels_breakdown[source] = channels_breakdown.get(source, 0) + 1

        skill_counts: Counter[str] = Counter()
        candidate_ids = {candidate.candidate_id for candidate in cands if candidate.candidate_id}
        if candidate_ids:
            profiles = db.scalars(
                select(CandidateProfile).where(CandidateProfile.candidate_id.in_(candidate_ids))
            ).all()
            for profile in profiles:
                if not profile.skills_json:
                    continue
                try:
                    skills = json.loads(profile.skills_json)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(skills, list):
                    continue
                for skill in skills:
                    clean = str(skill).strip()
                    if clean:
                        skill_counts[clean] += 1
        top_skills = [
            {"skill": skill, "count": count}
            for skill, count in skill_counts.most_common(10)
        ]

        return {
            "score_distribution": score_brackets,
            "channels": channels_breakdown,
            "top_skills": top_skills,
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_sourcing_quality_metrics: {e}", exc_info=True)
        return {}
    except Exception as e:
        logger.error(f"Unexpected error in get_sourcing_quality_metrics: {e}", exc_info=True)
        return {}


def get_outreach_analytics(db: Session, hunt_id: Optional[int] = None) -> Dict[str, Any]:
    """Compute communication metrics by channel, direction, and outreach sequence performance.

    Args:
        db (Session): The SQLAlchemy database session.
        hunt_id (Optional[int]): The ID of a specific hunt to filter by. Defaults to None.

    Returns:
        Dict[str, Any]: A dictionary containing communication and outreach sequence metrics.
    """
    try:
        candidate_ids: set[int] | None = None
        if hunt_id:
            from app.hunts.pipeline import list_active_hunt_candidates

            candidate_ids = {
                item.candidate_id
                for item in list_active_hunt_candidates(db, hunt_id)
                if item.candidate_id is not None
            }
        comm_stmt = select(Communication)
        comms = (
            list(db.scalars(comm_stmt.where(Communication.candidate_id.in_(candidate_ids))).all())
            if candidate_ids is not None and candidate_ids
            else ([] if candidate_ids is not None else list(db.scalars(comm_stmt).all()))
        )

        channel_counts: Dict[str, int] = {
            "email": 0,
            "linkedin": 0,
            "naukri": 0,
            "whatsapp": 0,
            "voice_ai": 0,
        }

        direction_counts: Dict[str, int] = {"outbound": 0, "inbound": 0}

        for comm in comms:
            ch = comm.channel.lower() if comm.channel else "email"
            if ch in channel_counts:
                channel_counts[ch] += 1
            else:
                channel_counts["email"] += 1

            d = comm.direction.lower() if comm.direction else "outbound"
            if d in direction_counts:
                direction_counts[d] += 1

        # Fallback demo numbers removed
        else:
            # Standardize keys for presentation
            channel_counts = {
                "Email": channel_counts.get("email", 0),
                "LinkedIn InMail": channel_counts.get("linkedin", 0),
                "Naukri Connect": channel_counts.get("naukri", 0),
                "Voice AI Screen": channel_counts.get("voice_ai", 0),
                "WhatsApp Direct": channel_counts.get("whatsapp", 0),
            }
            direction_counts = {
                "Outbound Sent": direction_counts.get("outbound", 0),
                "Inbound Replies": direction_counts.get("inbound", 0),
            }

        seq_stmt = select(OutreachSequence)
        sequences = list(db.scalars(seq_stmt).all())
        sequence_perf: List[Dict[str, Any]] = []
        for seq in sequences:
            enrollments = list(seq.enrollments)
            if candidate_ids is not None:
                enrollments = [
                    enrollment
                    for enrollment in enrollments
                    if enrollment.candidate_id in candidate_ids
                ]
                if not enrollments:
                    continue
            total_enrolled = len(enrollments)
            replied = len([e for e in enrollments if e.status == "replied"])
            completed = len([e for e in enrollments if e.status == "completed"])
            rate = round((replied / total_enrolled * 100), 1) if total_enrolled > 0 else 0.0
            
            sequence_perf.append({
                "sequence_name": seq.name,
                "channel": seq.channel,
                "enrolled": total_enrolled,
                "replied": replied,
                "completed": completed,
                "response_rate": rate,
            })

        pass # Fallback sequence perf removed

        return {
            "channel_counts": channel_counts,
            "direction_counts": direction_counts,
            "sequence_performance": sequence_perf,
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_outreach_analytics: {e}", exc_info=True)
        return {}
    except Exception as e:
        logger.error(f"Unexpected error in get_outreach_analytics: {e}", exc_info=True)
        return {}


def get_ai_cost_tracker(db: Session, hunt_id: Optional[int] = None) -> Dict[str, Any]:
    """Compute AI engine operations count, cloud API token cost vs local GGUF model cost savings.

    Args:
        db (Session): The SQLAlchemy database session.
        hunt_id (Optional[int]): The ID of a specific hunt to filter by. Defaults to None.

    Returns:
        Dict[str, Any]: A dictionary containing AI usage and cost metrics.
    """
    try:
        activities_stmt = select(HuntActivity)
        if hunt_id:
            activities_stmt = activities_stmt.where(HuntActivity.hunt_id == hunt_id)
        activities = list(db.scalars(activities_stmt).all())
        
        ai_activities = _recorded_ai_activities(activities)
        total_ai_ops = len(ai_activities)
        op_breakdown: Counter[str] = Counter(
            AI_ACTIVITY_LABELS[activity.activity_type] for activity in ai_activities
        )

        # Hunt activities currently do not persist provider, token, or billing
        # telemetry. Expose that absence instead of assuming a local/cloud split.
        local_ops_count = 0
        cloud_ops_count = 0
        unattributed_ops_count = total_ai_ops

        return {
            "total_operations": total_ai_ops,
            "local_operations": local_ops_count,
            "cloud_operations": cloud_ops_count,
            "unattributed_operations": unattributed_ops_count,
            "local_tokens_processed": 0,
            "cloud_tokens_processed": 0,
            "hypothetical_full_cloud_cost": 0.0,
            "actual_cloud_cost": 0.0,
            "local_execution_cost": 0.0,
            "total_cost_saved": 0.0,
            "operation_breakdown": dict(op_breakdown),
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_ai_cost_tracker: {e}", exc_info=True)
        return {}
    except Exception as e:
        logger.error(f"Unexpected error in get_ai_cost_tracker: {e}", exc_info=True)
        return {}


def get_trend_analytics(
    db: Session,
    days: int = 30,
    hunt_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Generate time-series daily trend data for charts.

    Args:
        db (Session): The SQLAlchemy database session.
        days (int): Number of days for trend analysis. Defaults to 30.

    Returns:
        Dict[str, Any]: A dictionary containing daily trend time-series data.
    """
    try:
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days - 1)

        if hunt_id:
            from app.hunts.pipeline import list_active_hunt_candidates

            hunt_candidates = list_active_hunt_candidates(db, hunt_id)
            sourced_dates = [item.created_at for item in hunt_candidates]
            candidate_ids = {item.candidate_id for item in hunt_candidates if item.candidate_id}
            hired_dates = [
                item.updated_at
                for item in hunt_candidates
                if item.stage and item.stage.name == "Hired"
            ]
            communications = (
                list(db.scalars(select(Communication).where(Communication.candidate_id.in_(candidate_ids))).all())
                if candidate_ids
                else []
            )
        else:
            sourced_dates = list(db.scalars(
                select(Candidate.created_at).where(Candidate.status != "Archived")
            ).all())
            from app.hunts.pipeline import list_active_hunt_candidates

            active_hunt_candidates = list_active_hunt_candidates(db)
            hired_dates = [
                item.updated_at
                for item in active_hunt_candidates
                if item.stage and item.stage.name == "Hired"
            ]
            communications = list(db.scalars(select(Communication)).all())

        sourced_by_day = Counter(value.date() for value in sourced_dates if value)
        outreach_by_day = Counter(
            item.created_at.date()
            for item in communications
            if item.direction == "outbound" and item.created_at
        )
        hired_by_day = Counter(value.date() for value in hired_dates if value)

        date_labels: List[str] = []
        candidates_sourced_series: List[int] = []
        outreach_sent_series: List[int] = []
        hires_series: List[int] = []
        curr = start_date

        while curr <= end_date:
            date_str = curr.strftime("%b %d")
            date_labels.append(date_str)
            
            candidates_sourced_series.append(sourced_by_day.get(curr, 0))
            outreach_sent_series.append(outreach_by_day.get(curr, 0))
            hires_series.append(hired_by_day.get(curr, 0))

            curr += timedelta(days=1)

        return {
            "date_labels": date_labels,
            "candidates_sourced": candidates_sourced_series,
            "outreach_sent": outreach_sent_series,
            "hires": hires_series,
        }
    except Exception as e:
        logger.error(f"Unexpected error in get_trend_analytics: {e}", exc_info=True)
        return {}


def get_all_analytics_data(db: Session, hunt_id: Optional[int] = None, days: int = 30) -> Dict[str, Any]:
    """Master analytics data aggregator.

    Args:
        db (Session): The SQLAlchemy database session.
        hunt_id (Optional[int]): The ID of a specific hunt to filter by. Defaults to None.
        days (int): Number of days for trend analysis. Defaults to 30.

    Returns:
        Dict[str, Any]: A dictionary aggregating all analytics metrics.
    """
    return {
        "kpi": get_kpi_summary(db, hunt_id=hunt_id),
        "funnel": get_hunt_funnel_data(db, hunt_id=hunt_id),
        "velocity": get_time_to_fill_metrics(db, hunt_id=hunt_id),
        "sourcing": get_sourcing_quality_metrics(db, hunt_id=hunt_id),
        "outreach": get_outreach_analytics(db, hunt_id=hunt_id),
        "ai_cost": get_ai_cost_tracker(db, hunt_id=hunt_id),
        "trends": get_trend_analytics(db, days=days, hunt_id=hunt_id),
    }


def _calculate_avg_time_to_fill(hunts: List[TalentHunt], hunt_cands: List[HuntCandidate]) -> float:
    """Helper to calculate average time-to-fill in days.

    Args:
        hunts (List[TalentHunt]): A list of TalentHunt objects.
        hunt_cands (List[HuntCandidate]): A list of HuntCandidate objects.

    Returns:
        float: The calculated average time-to-fill in days.
    """
    try:
        if not hunts:
            return 0.0

        durations: List[float] = []
        for h in hunts:
            hired = [c for c in hunt_cands if c.hunt_id == h.id and c.stage and c.stage.name == "Hired"]
            h_created = h.created_at.replace(tzinfo=timezone.utc) if h.created_at and h.created_at.tzinfo is None else h.created_at
            if not h_created:
                continue
            if hired:
                for candidate in hired:
                    if candidate.updated_at:
                        c_updated = candidate.updated_at.replace(tzinfo=timezone.utc) if candidate.updated_at.tzinfo is None else candidate.updated_at
                        days = max(1, (c_updated - h_created).days)
                        durations.append(float(days))
        return round(sum(durations) / len(durations), 1) if durations else 0.0
    except Exception as e:
        logger.error(f"Unexpected error in _calculate_avg_time_to_fill: {e}", exc_info=True)
        return 0.0
