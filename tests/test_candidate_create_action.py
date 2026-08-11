from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.actions.api import dispatch_action
from app.actions.history import undo_action
from app.actions.models import ActionHistory
from app.candidates.models import Candidate, CandidateNote
from app.communications.models import CommunicationThread  # noqa: F401 - register ORM tables
from app.hunts.models import HuntCandidate, TalentHunt
from app.infrastructure.db import Base


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'candidate-create.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.actions.locks.SessionFactory", factory)
    monkeypatch.setattr("app.candidates.search.candidate_search_index.index_candidate", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.candidates.search.candidate_search_index.delete_candidate", lambda *args, **kwargs: True)


def test_candidate_create_action_links_hunt_and_undoes(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        hunt = TalentHunt(title="Animator Hunt", target_role="Animator")
        db.add(hunt)
        db.commit()
        hunt_id = hunt.id

    result = dispatch_action(
        "candidates.create",
        {
            "full_name": "Nina Shah",
            "email": "nina@example.com",
            "current_title": "Spine Animator",
            "skills": ["Spine", "Photoshop"],
            "hunt_id": hunt_id,
        },
        actor_type="system",
        scopes=["write"],
        session_id="create_candidate_test",
    )
    assert result.success is True
    assert result.data["changed"] is True
    candidate_id = result.data["candidate_id"]
    action_id = result.data["action_id"]
    with factory() as db:
        candidate = db.get(Candidate, candidate_id)
        assert candidate.status == "Sourced"
        assert candidate.profile.skills_json == '["Spine", "Photoshop"]'
        assert db.query(HuntCandidate).filter_by(candidate_id=candidate_id, hunt_id=hunt_id).count() == 1
        assert db.get(ActionHistory, action_id).action_type == "create_candidate"
        undo_action(db, action_id)

    with factory() as db:
        assert db.get(Candidate, candidate_id) is None
        assert db.query(HuntCandidate).filter_by(candidate_id=candidate_id).count() == 0


def test_candidate_create_returns_conflict_without_upsert(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        existing = Candidate(
            full_name="Asha Rao", email="asha@example.com", current_title="Animator", status="Active"
        )
        db.add(existing)
        db.commit()
        existing_id = existing.id

    result = dispatch_action(
        "candidates.create",
        {"full_name": "Asha R.", "email": "asha@example.com", "current_title": "Changed title"},
        actor_type="system",
        scopes=["write"],
    )
    assert result.success is True
    assert result.data["status"] == "conflict"
    assert result.data["changed"] is False
    assert result.data["candidate_id"] == existing_id
    with factory() as db:
        assert db.get(Candidate, existing_id).current_title == "Animator"
        assert db.query(Candidate).count() == 1
        assert db.query(ActionHistory).filter_by(action_type="create_candidate").count() == 0


def test_candidate_creation_undo_refuses_to_remove_later_work(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    result = dispatch_action(
        "candidates.create",
        {"full_name": "Later Work"},
        actor_type="system",
        scopes=["write"],
    )
    candidate_id = result.data["candidate_id"]
    with factory() as db:
        db.add(CandidateNote(candidate_id=candidate_id, author="Recruiter", content="Keep this"))
        db.commit()
        try:
            undo_action(db, result.data["action_id"])
        except ValueError as exc:
            assert "notes or snapshots" in str(exc)
        else:
            raise AssertionError("Undo should refuse to erase later Candidate work")
    with factory() as db:
        assert db.get(Candidate, candidate_id) is not None
