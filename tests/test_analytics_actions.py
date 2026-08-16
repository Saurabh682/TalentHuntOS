import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.actions.api import dispatch_action
from app.actions.models import ActionExecution, ActionHistory
from app.analytics.service import (
    get_ai_cost_tracker,
    get_hunt_funnel_data,
    get_kpi_summary,
    get_outreach_analytics,
    get_sourcing_quality_metrics,
    get_time_to_fill_metrics,
    get_trend_analytics,
)
from app.candidates.models import Candidate, CandidateProfile
from app.communications.models import Communication, OutreachEnrollment, OutreachSequence
from app.hunts.models import HuntActivity, HuntCandidate, HuntStage, TalentHunt
from app.infrastructure.db import Base


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analytics-actions.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed(factory):
    now = datetime.now(timezone.utc)
    with factory() as db:
        hunts = [
            TalentHunt(title="Animator Hunt", status="Active", created_at=now),
            TalentHunt(title="Designer Hunt", status="Active", created_at=now),
        ]
        candidates = [
            Candidate(full_name="Animator Person", status="Sourced", created_at=now),
            Candidate(full_name="Designer Person", status="Sourced", created_at=now),
        ]
        db.add_all([*hunts, *candidates])
        db.flush()
        stages = [
            HuntStage(hunt_id=hunts[0].id, name="Sourced", position=0),
            HuntStage(hunt_id=hunts[1].id, name="Sourced", position=0),
        ]
        db.add_all(stages)
        db.flush()
        db.add_all([
            CandidateProfile(candidate_id=candidates[0].id, skills_json=json.dumps(["Spine"])),
            CandidateProfile(candidate_id=candidates[1].id, skills_json=json.dumps(["Figma"])),
            HuntCandidate(
                hunt_id=hunts[0].id,
                stage_id=stages[0].id,
                candidate_id=candidates[0].id,
                full_name=candidates[0].full_name,
                match_score=91,
                source_platform="linkedin",
                created_at=now,
            ),
            HuntCandidate(
                hunt_id=hunts[1].id,
                stage_id=stages[1].id,
                candidate_id=candidates[1].id,
                full_name=candidates[1].full_name,
                match_score=72,
                source_platform="naukri",
                created_at=now,
            ),
            Communication(
                candidate_id=candidates[0].id,
                channel="email",
                direction="outbound",
                sender="recruiter@example.com",
                recipient="animator@example.com",
                body="Hello animator",
                status="sent",
                created_at=now,
            ),
            Communication(
                candidate_id=candidates[1].id,
                channel="linkedin",
                direction="outbound",
                sender="recruiter@example.com",
                recipient="designer@example.com",
                body="Hello designer",
                status="sent",
                created_at=now,
            ),
            HuntActivity(
                hunt_id=hunts[0].id,
                activity_type="autopilot_match",
                description="Scored animator",
                created_at=now,
            ),
            HuntActivity(
                hunt_id=hunts[1].id,
                activity_type="autopilot_match",
                description="Scored designer",
                created_at=now,
            ),
        ])
        sequence = OutreachSequence(name="Candidate outreach", channel="email")
        db.add(sequence)
        db.flush()
        db.add_all([
            OutreachEnrollment(
                sequence_id=sequence.id,
                candidate_id=candidates[0].id,
                status="replied",
            ),
            OutreachEnrollment(
                sequence_id=sequence.id,
                candidate_id=candidates[1].id,
                status="completed",
            ),
        ])
        db.commit()
        return hunts[0].id


def test_analytics_actions_match_canonical_services_and_provenance(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    hunt_id = _seed(factory)

    with factory() as db:
        expected = {
            "analytics.kpi": get_kpi_summary(db, hunt_id=hunt_id),
            "analytics.funnel": get_hunt_funnel_data(db, hunt_id=hunt_id),
            "analytics.time_to_fill": get_time_to_fill_metrics(db, hunt_id=hunt_id),
            "analytics.sourcing_quality": get_sourcing_quality_metrics(db, hunt_id=hunt_id),
            "analytics.outreach": get_outreach_analytics(db, hunt_id=hunt_id),
            "analytics.ai_cost": get_ai_cost_tracker(db, hunt_id=hunt_id),
            "analytics.trends": get_trend_analytics(db, hunt_id=hunt_id, days=1),
        }

    for action_name, expected_data in expected.items():
        payload = {"hunt_id": hunt_id}
        if action_name == "analytics.trends":
            payload["days"] = 1
        result = dispatch_action(
            action_name,
            payload,
            actor_type="agent",
            session_id="analytics-parity",
            user_id=1,
        )
        assert result.success, result.error
        assert result.data["status"] == "success"
        assert result.data["scope"] == {
            "type": "hunt",
            "hunt_id": hunt_id,
            "hunt_title": "Animator Hunt",
        }
        assert result.data["data"] == expected_data
        assert result.data["provenance"]["source_of_truth"] == (
            "canonical TalentHunt database records"
        )
        assert result.metadata["risk_level"] == "R0"

    assert expected["analytics.kpi"]["outreach_sent"] == 1
    assert expected["analytics.outreach"]["direction_counts"]["Outbound Sent"] == 1
    assert expected["analytics.outreach"]["sequence_performance"] == [{
        "sequence_name": "Candidate outreach",
        "channel": "email",
        "enrolled": 1,
        "replied": 1,
        "completed": 0,
        "response_rate": 100.0,
    }]
    assert expected["analytics.ai_cost"]["total_operations"] == 1

    with factory() as db:
        assert db.query(ActionExecution).count() == len(expected)
        assert db.query(ActionHistory).count() == 0


def test_analytics_actions_reject_unknown_scope_and_unbounded_window(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)

    missing = dispatch_action(
        "analytics.kpi",
        {"hunt_id": 999},
        actor_type="agent",
        session_id="analytics-invalid",
        user_id=1,
    )
    assert not missing.success
    assert missing.error == "Talent Hunt not found."

    invalid_window = dispatch_action(
        "analytics.trends",
        {"days": 0},
        actor_type="agent",
        session_id="analytics-invalid",
        user_id=1,
    )
    assert not invalid_window.success
    assert "greater than or equal to 1" in (invalid_window.error or "")
