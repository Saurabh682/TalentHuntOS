from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.actions.api import approve_and_dispatch, dispatch_action, dispatch_preview
from app.actions.history import undo_action
from app.candidates.models import (
    Candidate,
    CandidateExperience,
    CandidateNote,
    CandidateProfile,
    CandidateTag,
    DiscoveredProfile,
)
from app.communications.models import Communication, CommunicationThread, OutreachEnrollment, OutreachSequence
from app.hunts.models import HuntActivity, HuntCandidate, TalentHunt
from app.infrastructure.db import Base


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'candidate-merge.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.actions.approvals.SessionFactory", factory)
    monkeypatch.setattr("app.actions.locks.SessionFactory", factory)
    monkeypatch.setattr("app.candidates.service._reindex_candidate", lambda *args: None)


def test_duplicate_search_uses_exact_identity_and_name_context(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        db.add_all([
            Candidate(full_name="Asha Rao", linkedin_url="https://linkedin.com/in/asha/?trk=x", status="Active"),
            Candidate(full_name="Different Display", linkedin_url="https://www.linkedin.com/in/asha", status="Active"),
            Candidate(full_name="Nina Shah", current_company="Studio One", status="Active"),
            Candidate(full_name="Nina Shah", current_company="Studio One", status="Passive"),
            Candidate(full_name="Nina Shah", current_company="Other Studio", location="Mumbai", status="Active"),
        ])
        db.commit()

    result = dispatch_action("candidates.duplicates.list", {}, actor_type="system", scopes=["read"])
    assert result.success is True
    assert result.data["count"] == 2
    reasons = [reason for pair in result.data["duplicates"] for reason in pair["reasons"]]
    assert "Same LinkedIn URL" in reasons
    assert "Same name and company" in reasons


def test_approved_candidate_merge_preserves_refs_and_undoes_exactly(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        survivor = Candidate(full_name="Anas Khan", phone="9999999999", status="Active")
        source = Candidate(
            full_name="Anas Khan", email="anas@example.com", current_company="Phonato Studios",
            linkedin_url="https://linkedin.com/in/anas-khan", status="Sourced",
        )
        db.add_all([survivor, source])
        db.flush()
        survivor.profile = CandidateProfile(candidate_id=survivor.id, skills_json='["Spine"]')
        source.profile = CandidateProfile(
            candidate_id=source.id, summary="Long verified profile summary", skills_json='["Spine", "Photoshop"]'
        )
        db.add_all([
            CandidateExperience(candidate_id=source.id, company="Phonato", title="Animator", start_date="2022-07"),
            CandidateTag(candidate_id=source.id, tag_name="Verified", color="#00d4aa"),
            CandidateNote(candidate_id=source.id, author="Recruiter", content="Strong reel"),
        ])
        hunt = TalentHunt(title="Spine Hunt", target_role="Animator")
        db.add(hunt)
        db.flush()
        survivor_hc = HuntCandidate(hunt_id=hunt.id, candidate_id=survivor.id, full_name=survivor.full_name)
        source_hc = HuntCandidate(hunt_id=hunt.id, candidate_id=source.id, full_name=source.full_name)
        db.add_all([survivor_hc, source_hc])
        db.flush()
        activity = HuntActivity(
            hunt_id=hunt.id, candidate_id=source_hc.id, activity_type="added", description="Source added"
        )
        thread = CommunicationThread(candidate_id=source.id, subject="Hello")
        db.add(thread)
        db.flush()
        message = Communication(
            thread_id=thread.id, candidate_id=source.id, sender="r", recipient="c", body="Hi"
        )
        sequence = OutreachSequence(name="Animator outreach")
        db.add(sequence)
        db.flush()
        enrollment = OutreachEnrollment(sequence_id=sequence.id, candidate_id=source.id)
        discovery = DiscoveredProfile(
            normalized_url="https://linkedin.com/in/anas-khan", source_url="https://linkedin.com/in/anas-khan",
            platform="linkedin", candidate_id=source.id,
        )
        db.add_all([activity, message, enrollment, discovery])
        db.commit()
        ids = {
            "survivor": survivor.id, "source": source.id, "source_hc": source_hc.id,
            "survivor_hc": survivor_hc.id, "activity": activity.id, "thread": thread.id,
            "message": message.id, "enrollment": enrollment.id, "discovery": discovery.id,
        }

    session_id = "candidate_merge_test"
    blocked = dispatch_action(
        "candidates.merge", {"survivor_id": ids["survivor"], "source_id": ids["source"]},
        actor_type="agent", user_id=41, session_id=session_id,
    )
    assert blocked.success is False
    assert "trusted approval" in blocked.error

    preview = dispatch_preview(
        "candidates.merge", {"survivor_id": ids["survivor"], "source_id": ids["source"]},
        actor_type="agent", user_id=41, session_id=session_id,
    )
    assert preview.success is True
    assert preview.data["preview"]["overlapping_hunts"] == 1
    with factory() as db:
        assert db.get(Candidate, ids["source"]).status == "Sourced"

    result = approve_and_dispatch(
        preview.data["approval_id"], user_id=41, session_id=session_id, actor_type="ui"
    )
    assert result.success is True
    action_id = result.data["action_id"]
    with factory() as db:
        survivor = db.get(Candidate, ids["survivor"])
        source = db.get(Candidate, ids["source"])
        assert survivor.email == "anas@example.com"
        assert source.email is None
        assert source.status == "Archived"
        assert {tag.tag_name for tag in survivor.tags} == {"Verified"}
        assert {exp.title for exp in survivor.experiences} == {"Animator"}
        assert db.get(CommunicationThread, ids["thread"]).candidate_id == survivor.id
        assert db.get(Communication, ids["message"]).candidate_id == survivor.id
        assert db.get(OutreachEnrollment, ids["enrollment"]).candidate_id == survivor.id
        assert db.get(DiscoveredProfile, ids["discovery"]).candidate_id == survivor.id
        assert db.get(HuntCandidate, ids["source_hc"]) is None
        assert db.get(HuntActivity, ids["activity"]).candidate_id == ids["survivor_hc"]

        undone = undo_action(db, action_id)
        assert undone.status == "undone"

    with factory() as db:
        survivor = db.get(Candidate, ids["survivor"])
        source = db.get(Candidate, ids["source"])
        assert survivor.email is None
        assert source.email == "anas@example.com"
        assert source.status == "Sourced"
        assert not survivor.tags and not survivor.notes and not survivor.experiences
        assert db.get(CommunicationThread, ids["thread"]).candidate_id == source.id
        assert db.get(Communication, ids["message"]).candidate_id == source.id
        assert db.get(OutreachEnrollment, ids["enrollment"]).candidate_id == source.id
        assert db.get(DiscoveredProfile, ids["discovery"]).candidate_id == source.id
        assert db.get(HuntCandidate, ids["source_hc"]).candidate_id == source.id
        assert db.get(HuntActivity, ids["activity"]).candidate_id == ids["source_hc"]

