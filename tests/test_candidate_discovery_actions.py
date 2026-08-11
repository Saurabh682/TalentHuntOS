import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.actions.api import dispatch_action
from app.actions.history import undo_action
from app.actions.models import ActionHistory
from app.candidates.discovery import record_discovery
from app.candidates.models import Candidate, CandidateEducation, CandidateExperience, CandidateNote, CandidateTag
from app.hunts.models import PlaybookEntry, TalentHunt
from app.infrastructure.db import Base


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'candidate-discovery-actions.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.actions.approvals.SessionFactory", factory)
    monkeypatch.setattr("app.actions.locks.SessionFactory", factory)
    monkeypatch.setattr("app.candidates.service._reindex_candidate", lambda *args: None)


def test_candidate_queries_and_reversible_controls(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        candidate = Candidate(
            full_name="Asha Animator",
            current_title="Spine Animator",
            location="Noida",
            status="Active",
        )
        db.add(candidate)
        db.commit()
        candidate_id = candidate.id

    listed = dispatch_action(
        "candidates.list",
        {"search": "Spine", "limit": 10},
        actor_type="ui",
    )
    assert listed.success is True
    assert listed.data["candidates"][0]["id"] == candidate_id

    added_tag = dispatch_action(
        "candidates.tags.add",
        {"candidate_id": candidate_id, "tag_name": "Priority"},
        actor_type="ui",
        session_id=f"candidate_{candidate_id}",
    )
    assert added_tag.success is True
    with factory() as db:
        assert db.scalar(select(CandidateTag).where(CandidateTag.candidate_id == candidate_id))
        undo_action(db, added_tag.data["action_id"])
        assert db.scalar(select(CandidateTag).where(CandidateTag.candidate_id == candidate_id)) is None

    added_note = dispatch_action(
        "candidates.notes.add",
        {"candidate_id": candidate_id, "content": "Strong reel."},
        actor_type="agent",
        session_id=f"candidate_{candidate_id}",
    )
    assert added_note.success is True
    with factory() as db:
        assert db.get(CandidateNote, added_note.data["note_id"])
        undo_action(db, added_note.data["action_id"])
        assert db.get(CandidateNote, added_note.data["note_id"]) is None

    archived = dispatch_action(
        "candidates.archive",
        {"candidate_id": candidate_id},
        actor_type="ui",
        session_id=f"candidate_{candidate_id}",
    )
    assert archived.success is True
    with factory() as db:
        assert db.get(Candidate, candidate_id).status == "Archived"
        undo_action(db, archived.data["action_id"])
        assert db.get(Candidate, candidate_id).status == "Active"


def test_removed_candidate_tag_can_be_restored(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        candidate = Candidate(full_name="Tagged Candidate", status="Active")
        db.add(candidate)
        db.flush()
        tag = CandidateTag(candidate_id=candidate.id, tag_name="Reviewed", color="#123456")
        db.add(tag)
        db.commit()
        candidate_id, tag_id = candidate.id, tag.id

    removed = dispatch_action(
        "candidates.tags.remove",
        {"candidate_id": candidate_id, "tag_id": tag_id},
        actor_type="ui",
    )
    assert removed.success is True
    with factory() as db:
        undo_action(db, removed.data["action_id"])
        restored = db.scalar(select(CandidateTag).where(CandidateTag.candidate_id == candidate_id))
        assert restored.tag_name == "Reviewed"
        assert restored.color == "#123456"


def test_discovery_and_common_pool_queries_share_retained_records(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        hunt = TalentHunt(title="Spine Hunt", target_role="Spine Animator")
        db.add(hunt)
        db.commit()
        profile, match = record_discovery(
            db,
            hunt_id=hunt.id,
            url="https://example.test/profile/asha",
            platform="naukri",
            source_query="Spine Animator Noida",
            full_name="Asha Animator",
            headline="Senior Spine Animator",
            location="Noida",
            status="rejected",
            rejection_reason="Location mismatch",
        )
        hunt_id, profile_id, match_id = hunt.id, profile.id, match.id

    discoveries = dispatch_action(
        "discoveries.list",
        {"hunt_id": hunt_id, "statuses": ["rejected"]},
        actor_type="agent",
    )
    assert discoveries.success is True
    assert discoveries.data["discoveries"][0]["match_id"] == match_id

    detail = dispatch_action(
        "discoveries.get", {"match_id": match_id}, actor_type="agent"
    )
    assert detail.success is True
    assert detail.data["discovery"]["profile"]["id"] == profile_id

    pool = dispatch_action(
        "discoveries.common_pool.list",
        {"search": "Asha", "limit": 10},
        actor_type="agent",
    )
    assert pool.success is True
    assert pool.data["total"] == 1
    assert pool.data["profiles"][0]["id"] == profile_id
    assert pool.data["profiles"][0]["hunt_matches"][0]["status"] == "rejected"

    with factory() as db:
        action_types = set(db.scalars(select(ActionHistory.action_type)).all())
        assert action_types == set()


def test_candidate_action_works_from_a_cold_worker_process(tmp_path):
    env = os.environ.copy()
    env["TALENTHUNT_DATA_DIR"] = str(tmp_path / "cold-worker-data")
    script = """
from app.actions.api import dispatch_action, ensure_core_actions_registered
from app.infrastructure.db import Base, engine
ensure_core_actions_registered()
Base.metadata.create_all(engine)
result = dispatch_action('candidates.list', {'limit': 1}, actor_type='system')
assert result.success, result.error
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.fspath(Path(__file__).parents[1]),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_experience_and_education_actions_round_trip_through_undo(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        candidate = Candidate(full_name="Structured Profile", status="Active")
        db.add(candidate)
        db.commit()
        candidate_id = candidate.id

    experience = dispatch_action(
        "candidates.experiences.save",
        {
            "candidate_id": candidate_id,
            "company": "Animation House",
            "title": "Spine Animator",
            "start_date": "2022-01",
            "end_date": "2024-01",
            "skills": ["Spine", "Rigging"],
        },
        actor_type="ui",
    )
    assert experience.success is True
    experience_id = experience.data["experience_id"]
    with factory() as db:
        row = db.get(CandidateExperience, experience_id)
        assert row.title == "Spine Animator"
        assert db.get(Candidate, candidate_id).experience_years == 2.1
        undo_action(db, experience.data["action_id"])
        assert db.get(CandidateExperience, experience_id) is None

    education = dispatch_action(
        "candidates.educations.save",
        {
            "candidate_id": candidate_id,
            "institution": "Design University",
            "degree": "BFA",
            "start_year": 2016,
            "end_year": 2020,
        },
        actor_type="agent",
    )
    assert education.success is True
    education_id = education.data["education_id"]
    with factory() as db:
        assert db.get(CandidateEducation, education_id).degree == "BFA"

    updated = dispatch_action(
        "candidates.educations.save",
        {
            "candidate_id": candidate_id,
            "education_id": education_id,
            "institution": "Design University",
            "degree": "MFA",
            "start_year": 2016,
            "end_year": 2020,
        },
        actor_type="agent",
    )
    assert updated.success is True
    with factory() as db:
        assert db.get(CandidateEducation, education_id).degree == "MFA"
        undo_action(db, updated.data["action_id"])
        assert db.get(CandidateEducation, education_id).degree == "BFA"

    removed = dispatch_action(
        "candidates.educations.remove",
        {"candidate_id": candidate_id, "education_id": education_id},
        actor_type="ui",
    )
    assert removed.success is True
    with factory() as db:
        assert db.get(CandidateEducation, education_id) is None
        undo_action(db, removed.data["action_id"])
        assert db.get(CandidateEducation, education_id).degree == "BFA"


def test_profile_apply_and_rogue_status_are_reversible(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        candidate = Candidate(full_name="Profile Candidate", status="Active")
        db.add(candidate)
        db.commit()
        candidate_id = candidate.id

    applied = dispatch_action(
        "candidates.profile.apply",
        {
            "candidate_id": candidate_id,
            "mode": "replace",
            "summary": "Reviewed profile summary",
            "resume_text": "Full reviewed resume text",
            "skills": ["Spine", "Photoshop"],
            "experiences": [{
                "company": "Studio One",
                "title": "Animator",
                "start_date": "2020-01",
                "end_date": "2022-01",
            }],
        },
        actor_type="ui",
    )
    assert applied.success is True
    with factory() as db:
        candidate = db.get(Candidate, candidate_id)
        assert candidate.profile.resume_text == "Full reviewed resume text"
        assert len(candidate.experiences) == 1
        undo_action(db, applied.data["action_id"])
        candidate = db.get(Candidate, candidate_id)
        assert candidate.profile is None
        assert candidate.experiences == []

    marked = dispatch_action(
        "candidates.rogue.set",
        {"candidate_id": candidate_id, "enabled": True, "note": "Wrong discipline"},
        actor_type="ui",
    )
    assert marked.success is True
    with factory() as db:
        assert db.scalar(select(CandidateTag).where(CandidateTag.candidate_id == candidate_id))
        assert db.scalar(select(PlaybookEntry).where(PlaybookEntry.candidate_id == candidate_id))
        undo_action(db, marked.data["action_id"])
        assert db.scalar(select(CandidateTag).where(CandidateTag.candidate_id == candidate_id)) is None
        assert db.scalar(select(PlaybookEntry).where(PlaybookEntry.candidate_id == candidate_id)) is None
