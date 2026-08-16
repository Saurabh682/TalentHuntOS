from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.actions.api import dispatch_action
from app.actions.history import undo_action
from app.candidates.models import Candidate
from app.communications.models import (
    Communication,
    CommunicationThread,
    MessageTemplate,
    OutreachEnrollment,
    OutreachSequence,
    OutreachStep,
)
from app.hunts.models import TalentHunt  # noqa: F401 - registers cross-domain tables
from app.infrastructure.db import Base


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'communications-actions.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.actions.locks.SessionFactory", factory)


def _dispatch(name, payload):
    result = dispatch_action(
        name,
        payload,
        actor_type="agent",
        session_id="communications-test",
    )
    assert result.success, result.error
    return result.data


def test_local_communication_log_never_sends_and_undo_removes_auto_thread(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        candidate = Candidate(full_name="Ada Animator", email="ada@example.test", status="Active")
        db.add(candidate)
        db.commit()
        candidate_id = candidate.id

    def fail_if_sent(*args, **kwargs):
        raise AssertionError("A local communication action attempted external delivery.")

    monkeypatch.setattr("app.communications.email_service.send_email", fail_if_sent)
    result = _dispatch(
        "communications.logs.create",
        {
            "candidate_id": candidate_id,
            "channel": "email",
            "direction": "outbound",
            "subject": "Recorded follow-up",
            "body": "This is a historical log only.",
        },
    )
    assert result["sent"] is False
    assert result["communication"]["status"] == "logged"
    with factory() as db:
        assert db.query(Communication).count() == 1
        assert db.query(CommunicationThread).count() == 1
        undo_action(db, result["history_id"])
        assert db.query(Communication).count() == 0
        assert db.query(CommunicationThread).count() == 0


def test_template_lifecycle_has_exact_undo(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    created = _dispatch(
        "communications.templates.create",
        {
            "name": "Animator intro",
            "channel": "email",
            "subject": "Hello {{candidate_name}}",
            "body_template": "Hi {{candidate_name}}",
            "variables": ["candidate_name"],
        },
    )
    template_id = created["template"]["id"]
    updated = _dispatch(
        "communications.templates.update",
        {"template_id": template_id, "name": "Animator introduction", "subject": "A role for you"},
    )
    archived = _dispatch(
        "communications.templates.active.set",
        {"template_id": template_id, "is_active": False},
    )

    with factory() as db:
        assert db.get(MessageTemplate, template_id).is_active is False
        undo_action(db, archived["history_id"])
        row = db.get(MessageTemplate, template_id)
        assert row.is_active is True
        undo_action(db, updated["history_id"])
        row = db.get(MessageTemplate, template_id)
        assert row.name == "Animator intro"
        assert row.subject == "Hello {{candidate_name}}"
        assert row.variables_json == '["candidate_name"]'
        undo_action(db, created["history_id"])
        assert db.get(MessageTemplate, template_id) is None


def test_sequence_step_enrollment_and_resume_are_local_and_reversible(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        candidate = Candidate(full_name="Sam Spine", email="sam@example.test", status="Active")
        db.add(candidate)
        db.commit()
        candidate_id = candidate.id

    sequence_result = _dispatch(
        "communications.sequences.create",
        {
            "name": "Spine outreach",
            "description": "Draft-only sequence",
            "initial_subject": "Spine role",
            "initial_body": "Hi {{candidate_name}}",
        },
    )
    sequence_id = sequence_result["sequence"]["id"]
    step_result = _dispatch(
        "communications.sequence_steps.add",
        {
            "sequence_id": sequence_id,
            "step_number": 2,
            "delay_days": 3,
            "subject": "Following up",
            "body_override": "Would you like to talk?",
        },
    )
    enrollment_result = _dispatch(
        "communications.enrollments.create",
        {"sequence_id": sequence_id, "candidate_id": candidate_id},
    )
    enrollment_id = enrollment_result["enrollment"]["id"]
    assert enrollment_result["enrollment"]["status"] == "paused"
    resumed = _dispatch(
        "communications.enrollments.status.set",
        {"enrollment_id": enrollment_id, "status": "active"},
    )
    assert resumed["sent"] is False

    listed = _dispatch("communications.sequences.list", {"include_inactive": True})
    assert listed["count"] == 1
    assert len(listed["sequences"][0]["steps"]) == 2
    assert listed["sequences"][0]["enrollments"][0]["status"] == "active"

    with factory() as db:
        undo_action(db, resumed["history_id"])
        enrollment = db.get(OutreachEnrollment, enrollment_id)
        assert enrollment.status == "paused"
        assert enrollment.next_step_due_at is None
        undo_action(db, enrollment_result["history_id"])
        assert db.get(OutreachEnrollment, enrollment_id) is None
        undo_action(db, step_result["history_id"])
        assert db.query(OutreachStep).filter_by(sequence_id=sequence_id).count() == 1
        undo_action(db, sequence_result["history_id"])
        assert db.get(OutreachSequence, sequence_id) is None


def test_communications_page_has_no_direct_delivery_or_mutation_bypass():
    source = (Path(__file__).parents[1] / "app" / "ui" / "pages" / "communications.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "send_email(",
        "process_due_outreach_steps(",
        "log_communication(",
        "delete_template(",
        "create_template(",
        "create_sequence(",
        "add_step_to_sequence(",
        "enroll_candidate(",
    )
    for call in forbidden:
        assert call not in source
    assert "dispatch_action(" in source
