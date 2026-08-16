"""End-to-end functionality & integration test suite for TalentHunt OS core workflows."""

import uuid

import pytest

from app.analytics.service import get_hunt_funnel_data, get_kpi_summary
from app.candidates.service import (
    add_candidate_note,
    add_candidate_tag,
    create_candidate,
    update_candidate,
)
from app.communications.outreach_service import (
    add_step_to_sequence,
    create_sequence,
    enroll_candidate,
    process_due_outreach_steps,
)
from app.communications.service import (
    list_communications,
)
from app.communications.template_engine import generate_candidate_outreach
from app.hunts.pipeline import add_candidate_to_hunt, get_pipeline_data, move_candidate_stage
from app.hunts.service import create_hunt, get_hunt_metrics
from app.infrastructure.db import SessionFactory, init_db
from app.intelligence.auto_pilot import run_autopilot_hunt_job


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Ensure database schema and tables are initialized and cleaned up after test run."""
    init_db()
    yield
    with SessionFactory() as db:
        from app.candidates.models import Candidate
        from app.communications.models import OutreachSequence
        from app.hunts.models import TalentHunt
        db.query(TalentHunt).filter(TalentHunt.title.like("%E2E%") | TalentHunt.title.like("%Kanban%")).delete(synchronize_session=False)
        db.query(Candidate).filter(Candidate.email.like("%example.com%")).delete(synchronize_session=False)
        db.query(OutreachSequence).filter(OutreachSequence.name.like("%E2E Sequence%")).delete(synchronize_session=False)
        db.commit()


def test_e2e_talent_hunt_creation_and_autopilot_sourcing():
    """Test full workflow of creating a Talent Hunt and running AI Auto-Pilot sourcing."""
    uid = uuid.uuid4().hex[:6]
    with SessionFactory() as db:
        # 1. Create a Talent Hunt Campaign
        hunt = create_hunt(
            db,
            title=f"E2E Senior Full Stack Engineer {uid}",
            target_role=f"Full Stack Architect {uid}",
            location="San Francisco, CA",
            salary_range="$160k - $200k",
            description="Leading full-stack engineering initiatives with React & Python.",
            search_config={
                "required_skills": "Python, React, TypeScript, FastAPI",
                "min_experience": "5+ years",
                "locations": "San Francisco, CA",
            }
        )
        assert hunt is not None
        assert hunt.id is not None
        assert f"E2E Senior Full Stack Engineer {uid}" in hunt.title
        assert hunt.status == "Active"
        assert hunt.search_config is not None
        assert hunt.search_config.required_skills == "Python, React, TypeScript, FastAPI"
        hunt_id = hunt.id

        matching_candidate = create_candidate(
            db,
            full_name=f"E2E Matching Architect {uid}",
            email=f"e2e.architect.{uid}@example.com",
            location="San Francisco, CA",
            current_title=f"Full Stack Architect {uid}",
            experience_years=7,
            skills=["Python", "React", "TypeScript", "FastAPI"],
        )
        assert matching_candidate is not None

    # 2. Trigger AI Auto-Pilot Sourcing
    res = run_autopilot_hunt_job(hunt_id)
    assert res["status"] == "success"
    assert res["hunt_id"] == hunt_id
    assert res["candidates_sourced"] > 0

    # 3. Verify metrics and pipeline population
    with SessionFactory() as db:
        metrics = get_hunt_metrics(db, hunt_id)
        assert metrics["total_candidates"] >= 1
        assert metrics["avg_match_score"] > 0.0

        pipeline = get_pipeline_data(db, hunt_id)
        assert pipeline["hunt_id"] == hunt_id
        assert len(pipeline["stages"]) >= 5


def test_e2e_candidate_crm_and_profile_management():
    """Test candidate creation, profile enrichment, tagging, and note additions."""
    uid = uuid.uuid4().hex[:6]
    with SessionFactory() as db:
        # 1. Create Candidate
        cand = create_candidate(
            db,
            full_name=f"E2E Candidate {uid}",
            current_title="Principal DevOps Specialist",
            current_company="CloudScale Inc",
            email=f"e2e.devops.{uid}@example.com",
            location="Austin, TX",
            experience_years=7.5,
            skills=["Kubernetes", "Docker", "Terraform", "AWS", "Python"],
            summary="Cloud architecture expert with deep infrastructure automation experience.",
        )
        assert cand is not None
        assert cand.id is not None
        cand_id = cand.id

        # 2. Add Tag & Note
        tag = add_candidate_tag(db, cand_id, tag_name=f"Lead_{uid}", color="teal")
        assert tag is not None
        assert tag.tag_name == f"Lead_{uid}"

        note = add_candidate_note(db, cand_id, content="Screened on 2026-08-08: Top technical score.")
        assert note is not None
        assert "Screened" in note.content

        # 3. Update Candidate Profile
        updated = update_candidate(
            db,
            cand_id,
            headline="Principal Cloud & DevOps Architect",
            skills=["Kubernetes", "Docker", "Terraform", "AWS", "Python", "Go"],
            status="Active",
        )
        assert updated is not None
        assert updated.profile.headline == "Principal Cloud & DevOps Architect"


def test_e2e_pipeline_kanban_candidate_movement():
    """Test creating hunt, adding candidate, and moving candidate across pipeline stages."""
    uid = uuid.uuid4().hex[:6]
    with SessionFactory() as db:
        hunt = create_hunt(db, title=f"Kanban Test Hunt {uid}", target_role="Backend Developer")
        assert hunt is not None
        hunt_id = hunt.id

        cand = create_candidate(db, full_name=f"Kanban Cand {uid}", email=f"kanban.{uid}@example.com", current_title="Backend Dev")
        assert cand is not None
        cand_id = cand.id

        pipeline_before = get_pipeline_data(db, hunt_id)
        first_stage = pipeline_before["stages"][0]
        second_stage = pipeline_before["stages"][1]

        # Add candidate to first stage
        hc = add_candidate_to_hunt(
            db,
            hunt_id=hunt_id,
            full_name=cand.full_name,
            candidate_id=cand_id,
            email=cand.email,
            current_title=cand.current_title,
            stage_id=first_stage["id"],
            match_score=0.85,
        )
        assert hc is not None
        hc_id = hc.id

        # Move candidate to second stage (e.g. Contacted / Screening)
        moved = move_candidate_stage(db, candidate_id=hc_id, new_stage_id=second_stage["id"])
        assert moved is not None

        db.expire_all()
        pipeline_after = get_pipeline_data(db, hunt_id)
        # Check candidate is in second stage
        target_stage_cands = [s["candidates"] for s in pipeline_after["stages"] if s["id"] == second_stage["id"]][0]
        assert any(c.id == hc_id for c in target_stage_cands)


def test_e2e_communications_outreach_sequence():
    """Test template rendering, drip sequence creation, candidate enrollment, and outreach processing."""
    uid = uuid.uuid4().hex[:6]
    with SessionFactory() as db:
        # 1. Template Rendering
        body_template = "Hi {{candidate_name}}, noticed your expertise in {{skills}}. Join {{company}} as {{job_title}}!"
        context = {
            "full_name": f"Maya Lin {uid}",
            "skills": "Rust, Distributed Systems",
            "company": "NexusAI",
            "job_title": "Staff Engineer",
        }
        rendered = generate_candidate_outreach(body_template, candidate=context, custom_fields=context)
        assert f"Maya Lin {uid}" in rendered
        assert "Rust, Distributed Systems" in rendered
        assert "NexusAI" in rendered

        # 2. Outreach Sequence & Enrollment
        seq = create_sequence(db, name=f"E2E Sequence {uid}", channel="email")
        assert seq is not None

        step = add_step_to_sequence(db, sequence_id=seq.id, step_number=1, delay_days=0, subject="Role Opportunity at {{company}}", body_override=body_template)
        assert step is not None

        cand = create_candidate(db, full_name=f"Maya Lin {uid}", email=f"maya.{uid}@example.com")
        assert cand is not None

        enr = enroll_candidate(db, sequence_id=seq.id, candidate_id=cand.id)
        assert enr is not None
        assert enr.status == "active"

        # 3. The legacy engine cannot bypass R4 recipient approval.
        with pytest.raises(PermissionError, match="R4 approved delivery action"):
            process_due_outreach_steps(db)

        # 4. No communication was manufactured by the rejected legacy path.
        logs = list_communications(db, candidate_id=cand.id)
        assert logs == []


def test_e2e_analytics_and_reporting_service():
    """Test analytics overview metrics and pipeline funnel report generation."""
    with SessionFactory() as db:
        overview = get_kpi_summary(db)
        assert "total_hunts" in overview
        assert "active_hunts" in overview
        assert "total_sourced" in overview

        funnel = get_hunt_funnel_data(db)
        assert isinstance(funnel, dict)
        assert "stages" in funnel
