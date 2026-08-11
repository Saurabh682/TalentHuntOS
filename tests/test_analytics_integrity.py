import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analytics.service import (
    get_ai_cost_tracker,
    get_kpi_summary,
    get_sourcing_quality_metrics,
    get_time_to_fill_metrics,
    get_trend_analytics,
)
from app.candidates.models import Candidate, CandidateProfile
from app.communications.models import Communication
from app.hunts.models import HuntActivity, HuntCandidate, HuntStage, TalentHunt
from app.infrastructure.db import Base


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analytics.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_quality_metrics_use_real_scores_sources_and_skills(tmp_path):
    factory = _factory(tmp_path)
    with factory() as db:
        hunt = TalentHunt(title="Honest Analytics", status="Active")
        db.add(hunt)
        db.flush()
        stage = HuntStage(hunt_id=hunt.id, name="Sourced", position=0)
        candidates = [
            Candidate(full_name="Fraction Score", status="Sourced"),
            Candidate(full_name="Percent Score", status="Sourced"),
            Candidate(full_name="No Score", status="Sourced"),
        ]
        db.add_all([stage, *candidates])
        db.flush()
        db.add_all([
            CandidateProfile(candidate_id=candidates[0].id, skills_json=json.dumps(["Python", "SQL"])),
            CandidateProfile(candidate_id=candidates[1].id, skills_json=json.dumps(["Python"])),
            HuntCandidate(hunt_id=hunt.id, stage_id=stage.id, candidate_id=candidates[0].id, full_name="Fraction Score", match_score=0.85, source_platform="linkedin"),
            HuntCandidate(hunt_id=hunt.id, stage_id=stage.id, candidate_id=candidates[1].id, full_name="Percent Score", match_score=92, source_platform="naukri"),
            HuntCandidate(hunt_id=hunt.id, stage_id=stage.id, candidate_id=candidates[2].id, full_name="No Score", match_score=None, source_platform=None),
        ])
        db.commit()

        result = get_sourcing_quality_metrics(db, hunt.id)

        assert result["score_distribution"]["80-89% (Good Match)"] == 1
        assert result["score_distribution"]["90-100% (High Match)"] == 1
        assert result["score_distribution"]["Unscored"] == 1
        assert result["channels"] == {"Linkedin": 1, "Naukri": 1, "Internal Db": 1}
        assert result["top_skills"][0] == {"skill": "Python", "count": 2}


def test_ai_tracker_counts_only_recorded_ai_operations_without_fake_costs(tmp_path):
    factory = _factory(tmp_path)
    with factory() as db:
        hunt = TalentHunt(title="AI Audit", status="Active")
        db.add(hunt)
        db.flush()
        db.add_all([
            HuntActivity(hunt_id=hunt.id, activity_type="created", description="Created"),
            HuntActivity(hunt_id=hunt.id, activity_type="autopilot_match", description="Scored"),
        ])
        db.commit()

        result = get_ai_cost_tracker(db)

        assert result["total_operations"] == 1
        assert result["unattributed_operations"] == 1
        assert result["operation_breakdown"] == {"Candidate Match Scoring": 1}
        assert result["actual_cloud_cost"] == 0.0
        assert result["total_cost_saved"] == 0.0


def test_trends_and_velocity_are_derived_from_records(tmp_path):
    factory = _factory(tmp_path)
    with factory() as db:
        now = datetime.now(timezone.utc)
        hunt = TalentHunt(title="Open Hunt", status="Active", created_at=now)
        candidate = Candidate(full_name="New Person", status="Sourced", created_at=now)
        db.add_all([hunt, candidate])
        db.flush()
        stage = HuntStage(hunt_id=hunt.id, name="Sourced", position=0)
        db.add(stage)
        db.flush()
        db.add(HuntCandidate(hunt_id=hunt.id, stage_id=stage.id, candidate_id=candidate.id, full_name=candidate.full_name, created_at=now))
        db.add(Communication(
            candidate_id=candidate.id,
            channel="email",
            direction="outbound",
            sender="recruiter@example.com",
            recipient="candidate@example.com",
            body="Hello",
            status="sent",
            created_at=now,
        ))
        db.commit()

        trends = get_trend_analytics(db, days=1)
        velocity = get_time_to_fill_metrics(db, hunt.id)
        kpi = get_kpi_summary(db, hunt.id)

        assert trends["candidates_sourced"] == [1]
        assert trends["outreach_sent"] == [1]
        assert trends["hires"] == [0]
        assert velocity["hunts_velocity"][0]["total_candidates"] == 1
        assert velocity["hunts_velocity"][0]["time_to_fill_days"] is None
        assert velocity["stage_bottlenecks"] == {}
        assert kpi["avg_time_to_fill_days"] == 0.0
