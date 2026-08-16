import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.actions.api import dispatch_action
from app.actions.history import undo_action
from app.candidates.intake_service import submit_intake
from app.candidates.models import (
    Candidate,
    CandidateIntakeRequest,
    CandidateIntakeSubmission,
)
from app.hunts.models import PlaybookEntry
from app.infrastructure.db import Base


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'playbook-intake-actions.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.actions.locks.SessionFactory", factory)


def _candidate(factory, *, name="Intake Person"):
    with factory() as db:
        candidate = Candidate(
            full_name=name,
            email="old@example.com",
            experience_years=2.0,
        )
        db.add(candidate)
        db.commit()
        return candidate.id


def test_playbook_query_add_and_undo(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)

    added = dispatch_action(
        "playbook.insights.add",
        {
            "worked": True,
            "note": "Search exact animation tools before broad titles.",
            "role_context": "Spine Animator",
            "platform": "linkedin",
            "query_text": '"Spine" animator',
            "author_name": "Recruiter",
        },
        actor_type="ui",
        session_id="playbook",
    )
    assert added.success is True
    assert added.data["undoable"] is True

    listed = dispatch_action(
        "playbook.list",
        {"entry_type": "Insights", "role": "Spine", "limit": 10},
        actor_type="agent",
    )
    assert listed.success is True
    assert listed.data["count"] == 1
    assert listed.data["entries"][0]["note"].startswith("Search exact")

    with factory() as db:
        undo_action(db, added.data["action_id"])
        assert db.scalar(select(PlaybookEntry.id)) is None


def test_intake_link_creation_and_dependency_guarded_undo(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    candidate_id = _candidate(factory)

    created = dispatch_action(
        "intake.requests.create",
        {"candidate_id": candidate_id, "expires_in_days": 7},
        actor_type="ui",
        session_id=f"candidate_{candidate_id}",
    )
    assert created.success is True
    assert created.data["sent"] is False
    assert created.data["url"].startswith("http://127.0.0.1:8080/intake/")

    with factory() as db:
        undo_action(db, created.data["action_id"])
        assert db.get(CandidateIntakeRequest, created.data["request_id"]) is None


def test_intake_reject_and_accept_are_atomic_and_undoable(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    candidate_id = _candidate(factory)

    created = dispatch_action(
        "intake.requests.create",
        {"candidate_id": candidate_id},
        actor_type="ui",
        session_id=f"candidate_{candidate_id}",
    )
    with factory() as db:
        request = db.get(CandidateIntakeRequest, created.data["request_id"])
        submission, message = submit_intake(db, request.token, {
            "contact": {"email": "new@example.com"},
            "experiences": [{"company": "Studio", "title": "Animator"}],
            "skills": ["Spine", "After Effects"],
            "summary": "Candidate supplied summary",
            "jd_fit": {"availability": "Immediate"},
        })
        assert message == "ok"
        submission_id = submission.id

    rejected = dispatch_action(
        "intake.submissions.review",
        {"submission_id": submission_id, "accept": False},
        actor_type="ui",
        session_id=f"candidate_{candidate_id}",
    )
    assert rejected.success is True
    with factory() as db:
        assert db.get(CandidateIntakeSubmission, submission_id).review_status == "rejected"
        undo_action(db, rejected.data["action_id"])
        assert db.get(CandidateIntakeSubmission, submission_id).review_status == "pending"

    accepted = dispatch_action(
        "intake.submissions.review",
        {
            "submission_id": submission_id,
            "accept": True,
            "mode": "replace",
            "profile_payload": {
                "experiences": [{"company": "Reviewed Studio", "title": "Senior Animator"}],
                "educations": [],
                "skills": ["Spine"],
                "summary": "Reviewed summary",
                "experience_years": 5.0,
            },
        },
        actor_type="ui",
        session_id=f"candidate_{candidate_id}",
    )
    assert accepted.success is True
    with factory() as db:
        candidate = db.get(Candidate, candidate_id)
        submission = db.get(CandidateIntakeSubmission, submission_id)
        assert candidate.email == "new@example.com"
        assert candidate.experience_years == 5.0
        assert candidate.experiences[0].company == "Reviewed Studio"
        assert json.loads(candidate.profile.skills_json) == ["Spine"]
        assert submission.review_status == "accepted"
        undo_action(db, accepted.data["action_id"])
        restored = db.get(Candidate, candidate_id)
        assert restored.email == "old@example.com"
        assert restored.experience_years == 2.0
        assert restored.experiences == []
        assert db.get(CandidateIntakeSubmission, submission_id).review_status == "pending"
