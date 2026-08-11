import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.actions.history import list_recent_actions, record_action, serialize_action, undo_action
from app.actions.models import ActionHistory  # noqa: F401
from app.candidates.intake_service import (
    apply_intake_submission,
    create_intake_request,
    submit_intake,
)
from app.candidates.models import Candidate, CandidateExperience, CandidateProfile
from app.candidates.service import replace_or_merge_profile_sections
from app.communications.models import BrowserSession
from app.communications.service import deactivate_browser_sessions_for_platform
from app.copilot.direct_actions import (
    parse_clear_and_source,
    parse_global_candidate_delete,
    parse_pending_hunt_clear_confirmation,
    run_global_candidate_delete,
    run_confirmed_hunt_clear,
)
from app.copilot.tools import remove_candidates_from_hunt
from app.infrastructure.db import Base
from app.hunts.models import HuntActivity, HuntCandidate, HuntStage, TalentHunt
from app.hunts.pipeline import clear_hunt_candidates, move_candidate_stage
from app.hunts.service import delete_hunt, list_hunts


def test_action_history_filters_by_session_and_builds_safe_record_target(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'action-cards.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        candidate = Candidate(full_name="Card Candidate", status="Active")
        db.add(candidate)
        db.commit()
        expected_id = candidate.id
        record_action(
            db,
            action_type="update_candidate_profile",
            summary="Updated Card Candidate",
            session_id="hunt_1",
            payload={"candidate_id": expected_id},
            undo_payload={"candidate_state": {"id": expected_id}},
        )
        record_action(
            db,
            action_type="archive_candidates",
            summary="Other session action",
            session_id="default",
            payload={"candidate_ids": []},
            undo_payload={"previous_statuses": {}},
        )

        scoped = list_recent_actions(db, session_id="hunt_1")
        assert len(scoped) == 1
        card = serialize_action(scoped[0], db)
        assert card["target"] == {
            "url": f"/candidates/{expected_id}",
            "label": "Open candidate",
        }
        assert card["resource_keys"] == [f"candidate:{expected_id}"]


def test_global_candidate_delete_is_previewed_and_undoable(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'actions.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)

    with factory() as db:
        db.add_all([
            Candidate(full_name="Ada", status="Active"),
            Candidate(full_name="Grace", status="Passive"),
        ])
        db.commit()

    preview = run_global_candidate_delete(session_id="default", confirm=False)
    assert "2 candidates" in preview
    with factory() as db:
        assert not list_recent_actions(db)

    result = run_global_candidate_delete(session_id="default", confirm=True)
    assert "Archived **2 candidates**" in result
    assert "ui-refresh:candidates" in result
    with factory() as db:
        assert {c.status for c in db.query(Candidate).all()} == {"Archived"}
        action = list_recent_actions(db)[0]
        assert action.action_type == "archive_candidates"
        undo_action(db, action.id)
        assert {c.status for c in db.query(Candidate).all()} == {"Active", "Passive"}


def test_global_delete_does_not_route_to_hunt_clear():
    text = "delete all the candidates in the database"
    assert parse_global_candidate_delete(text) == {"confirm": False}
    assert parse_clear_and_source(text) is None
    assert parse_global_candidate_delete("confirm delete all candidates") == {"confirm": True}


def _pipeline_fixture(db):
    candidate = Candidate(full_name="Lin Pipeline", status="Sourced")
    hunt = TalentHunt(title="Platform Hunt", target_role="Engineer")
    db.add_all([candidate, hunt])
    db.flush()
    sourced = HuntStage(hunt_id=hunt.id, name="Sourced", position=0)
    contacted = HuntStage(hunt_id=hunt.id, name="Contacted", position=1)
    db.add_all([sourced, contacted])
    db.flush()
    enrollment = HuntCandidate(
        hunt_id=hunt.id,
        candidate_id=candidate.id,
        stage_id=sourced.id,
        full_name=candidate.full_name,
        source_platform="manual",
    )
    db.add(enrollment)
    db.flush()
    db.add(HuntActivity(
        hunt_id=hunt.id,
        candidate_id=enrollment.id,
        activity_type="candidate_added",
        description="Added for action-history test.",
    ))
    db.commit()
    return hunt.id, enrollment.id, sourced.id, contacted.id, candidate.id


def test_pipeline_stage_move_is_recorded_and_undoable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'move-actions.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as db:
        _, enrollment_id, sourced_id, contacted_id, _ = _pipeline_fixture(db)
        moved = move_candidate_stage(
            db, enrollment_id, contacted_id, actor_type="ui"
        )
        assert moved.stage_id == contacted_id
        action = list_recent_actions(db)[0]
        assert action.action_type == "move_pipeline_candidate"
        undo_action(db, action.id)
        assert db.get(HuntCandidate, enrollment_id).stage_id == sourced_id


def test_clear_hunt_candidates_restores_enrollment_tag_and_activity(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'clear-actions.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as db:
        hunt_id, enrollment_id, sourced_id, _, candidate_id = _pipeline_fixture(db)
        result = clear_hunt_candidates(
            db, hunt_id, actor_type="copilot", session_id="audit-session"
        )
        assert result["removed"] == 1
        assert db.get(HuntCandidate, enrollment_id) is None
        action = list_recent_actions(db)[0]
        assert action.action_type == "clear_hunt_candidates"

        undo_action(db, action.id)
        restored = db.get(HuntCandidate, enrollment_id)
        assert restored is not None
        assert restored.candidate_id == candidate_id
        assert restored.stage_id == sourced_id
        assert any(a.activity_type == "candidate_added" for a in restored.activities)
        assert any(tag.tag_name == "Hunt: Platform Hunt" for tag in db.get(Candidate, candidate_id).tags)


def test_copilot_confirmed_hunt_clear_records_undo(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'copilot-clear-actions.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)

    with factory() as db:
        hunt_id, _, _, _, _ = _pipeline_fixture(db)

    result = json.loads(remove_candidates_from_hunt.invoke({
        "hunt_id": str(hunt_id),
        "confirm": True,
    }))
    assert result["status"] == "success"
    assert result["removed"] == 1
    assert "undone" in result["message"]

    with factory() as db:
        action = list_recent_actions(db)[0]
        assert action.action_type == "clear_hunt_candidates"
        assert action.actor_type == "copilot"


def test_short_confirmation_is_scoped_and_rechecks_the_preview(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'copilot-pending-clear.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)

    with factory() as db:
        hunt_id, enrollment_id, _, _, _ = _pipeline_fixture(db)

    original_preview = {
        "role": "assistant",
        "content": (
            "I found **2 candidates** in your hunt pipeline. "
            f"Would you confirm removal from Hunt #{hunt_id}? Type `yes` or `confirm`."
        ),
    }
    pending = parse_pending_hunt_clear_confirmation(
        "yes",
        [
            {
                "role": "user",
                "content": "remove all candidates from the campaign and add 25 new ones",
            },
            original_preview,
        ],
    )
    assert pending == {
        "hunt_id": hunt_id,
        "expected_count": 2,
        "source_target": 25,
    }

    stale_result = run_confirmed_hunt_clear(
        session_id=f"hunt_{hunt_id}",
        hunt_id=hunt_id,
        expected_count=2,
    )
    assert "Nothing was removed" in stale_result
    assert f"pending-action:hunt-clear:{hunt_id}:1" in stale_result
    with factory() as db:
        assert db.get(HuntCandidate, enrollment_id) is not None

    refreshed = parse_pending_hunt_clear_confirmation(
        "confirm removal of 1 candidate",
        [{"role": "assistant", "content": stale_result}],
    )
    assert refreshed == {"hunt_id": hunt_id, "expected_count": 1}
    completed = run_confirmed_hunt_clear(
        session_id=f"hunt_{hunt_id}",
        hunt_id=hunt_id,
        expected_count=1,
    )
    assert "Removed **1 candidate(s)**" in completed
    with factory() as db:
        assert db.get(HuntCandidate, enrollment_id) is None


def test_yes_does_not_confirm_an_unrelated_assistant_message():
    assert parse_pending_hunt_clear_confirmation(
        "yes",
        [{"role": "assistant", "content": "Would you like a shortlist summary?"}],
    ) is None


def test_candidate_timeline_correction_is_undoable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'timeline-actions.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as db:
        candidate = Candidate(
            full_name="Timeline Person",
            experience_years=8.0,
            current_title="Old title",
            current_company="Old company",
        )
        db.add(candidate)
        db.flush()
        db.add(CandidateProfile(candidate_id=candidate.id, headline="Old headline"))
        db.add(CandidateExperience(
            candidate_id=candidate.id,
            company="Old company",
            title="Old title",
            start_date="2020-01",
            end_date="2021-01",
        ))
        db.commit()

        previous_rows = [{
            "company": "Old company",
            "title": "Old title",
            "start_date": "2020-01",
            "end_date": "2021-01",
            "location": None,
            "is_current": False,
            "description": None,
        }]
        candidate.experience_years = 5.4
        candidate.current_title = "Current title"
        candidate.current_company = "Current company"
        candidate.profile.headline = "Current headline"
        for experience in list(candidate.experiences):
            db.delete(experience)
        db.commit()
        action = record_action(
            db,
            action_type="correct_candidate_timeline",
            summary="Corrected Timeline Person experience",
            payload={"candidate_id": candidate.id},
            undo_payload={
                "candidate_id": candidate.id,
                "experience_years": 8.0,
                "current_title": "Old title",
                "current_company": "Old company",
                "headline": "Old headline",
                "experiences": previous_rows,
            },
        )

        undo_action(db, action.id)
        db.refresh(candidate)
        assert candidate.experience_years == 8.0
        assert candidate.current_title == "Old title"
        assert candidate.current_company == "Old company"
        assert candidate.profile.headline == "Old headline"
        assert len(candidate.experiences) == 1


def test_hunt_archive_preserves_graph_and_is_undoable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'hunt-archive-actions.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as db:
        hunt_id, enrollment_id, _, _, _ = _pipeline_fixture(db)
        assert delete_hunt(db, hunt_id, actor_type="copilot")
        assert db.get(TalentHunt, hunt_id).status == "Archived"
        assert db.get(HuntCandidate, enrollment_id) is not None
        assert list_hunts(db) == []

        action = list_recent_actions(db)[0]
        assert action.action_type == "archive_hunt"
        undo_action(db, action.id)
        assert db.get(TalentHunt, hunt_id).status == "Active"
        assert len(list_hunts(db)) == 1


def test_profile_replacement_restores_complete_prior_state(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'profile-actions.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as db:
        candidate = Candidate(
            full_name="Profile Person",
            current_title="Original role",
            current_company="Original company",
            experience_years=3.0,
        )
        db.add(candidate)
        db.flush()
        db.add(CandidateProfile(
            candidate_id=candidate.id,
            headline="Original headline",
            skills_json=json.dumps(["Python"]),
        ))
        db.add(CandidateExperience(
            candidate_id=candidate.id,
            company="Original company",
            title="Original role",
            start_date="2021-01",
            end_date="2024-01",
        ))
        db.commit()
        candidate_id = candidate.id

        updated = replace_or_merge_profile_sections(
            db,
            candidate_id,
            experiences=[{
                "company": "New company",
                "title": "New role",
                "start_date": "2024-02",
                "end_date": "Present",
                "is_current": True,
            }],
            skills=["Rust"],
            headline="New headline",
            mode="replace",
            actor_type="copilot",
        )
        assert updated.current_title == "New role"
        assert updated.profile.skills_json == json.dumps(["Rust"])

        action = list_recent_actions(db)[0]
        assert action.action_type == "update_candidate_profile"
        undo_action(db, action.id)
        restored = db.get(Candidate, candidate_id)
        assert restored.current_title == "Original role"
        assert restored.current_company == "Original company"
        assert restored.profile.headline == "Original headline"
        assert json.loads(restored.profile.skills_json) == ["Python"]
        assert [(row.company, row.title) for row in restored.experiences] == [
            ("Original company", "Original role")
        ]


def test_intake_application_restores_profile_review_state_and_note(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'intake-actions.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as db:
        candidate = Candidate(full_name="Intake Person", email="old@example.com")
        db.add(candidate)
        db.commit()
        req = create_intake_request(db, candidate.id)
        sub, message = submit_intake(db, req.token, {
            "contact": {"email": "new@example.com"},
            "skills": ["Spine"],
            "jd_fit": {"availability": "Immediate"},
        })
        assert message == "ok"
        result = apply_intake_submission(db, sub.id, mode="replace")
        assert result["status"] == "success"
        assert db.get(Candidate, candidate.id).email == "new@example.com"

        action = list_recent_actions(db)[0]
        assert action.action_type == "apply_intake_submission"
        undo_action(db, action.id)
        restored = db.get(Candidate, candidate.id)
        assert restored.email == "old@example.com"
        assert restored.notes == []
        assert sub.review_status == "pending"
        assert req.status == "submitted"


def test_site_disconnect_retains_encrypted_data_and_is_undoable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'disconnect-actions.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as db:
        browser_session = BrowserSession(
            platform="linkedin",
            session_name="Primary",
            cookies_json="sealed-cookie-payload",
            headers_json="sealed-header-payload",
            is_active=True,
        )
        db.add(browser_session)
        db.commit()
        session_id = browser_session.id

        assert deactivate_browser_sessions_for_platform(db, "linkedin") == 1
        row = db.get(BrowserSession, session_id)
        assert row.is_active is False
        assert row.cookies_json == "sealed-cookie-payload"
        assert row.headers_json == "sealed-header-payload"

        action = list_recent_actions(db)[0]
        assert action.action_type == "disconnect_site"
        undo_action(db, action.id)
        assert db.get(BrowserSession, session_id).is_active is True
