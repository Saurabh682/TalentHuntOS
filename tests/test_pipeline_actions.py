from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.actions.api import dispatch_action
from app.actions.history import undo_action
from app.actions.models import ActionHistory
from app.candidates.models import Candidate, CandidateTag
from app.hunts.models import HuntActivity, HuntCandidate, HuntStage, PlaybookEntry, TalentHunt
from app.infrastructure.db import Base


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pipeline-actions.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.actions.locks.SessionFactory", factory)


def _seed(factory):
    with factory() as db:
        hunt = TalentHunt(title="Animator Hunt", target_role="Spine Animator")
        candidate = Candidate(full_name="Asha Rao", status="Sourced")
        db.add_all([hunt, candidate])
        db.flush()
        sourced = HuntStage(hunt_id=hunt.id, name="Sourced", position=0, color="#19d3c5")
        screening = HuntStage(hunt_id=hunt.id, name="Screening", position=1, color="#4aa3df")
        db.add_all([sourced, screening])
        db.flush()
        row = HuntCandidate(
            hunt_id=hunt.id,
            candidate_id=candidate.id,
            stage_id=sourced.id,
            full_name=candidate.full_name,
            current_title="2D Animator",
            source_platform="linkedin",
        )
        db.add(row)
        db.flush()
        activity = HuntActivity(
            hunt_id=hunt.id,
            candidate_id=row.id,
            activity_type="candidate_added",
            description="Added Asha Rao.",
        )
        tag = CandidateTag(candidate_id=candidate.id, tag_name=f"Hunt: {hunt.title}", color="#19d3c5")
        db.add_all([activity, tag])
        db.commit()
        return hunt.id, candidate.id, row.id, sourced.id, screening.id, activity.id, tag.id


def test_pipeline_get_and_remove_undo_preserve_master(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    hunt_id, candidate_id, row_id, sourced_id, _, activity_id, _ = _seed(factory)

    board = dispatch_action("pipeline.get", {"hunt_id": hunt_id}, actor_type="agent")
    assert board.success is True
    assert board.data["total_candidates"] == 1
    assert board.data["stages"][0]["candidates"][0]["candidate_id"] == candidate_id

    removed = dispatch_action(
        "pipeline.remove", {"hunt_candidate_id": row_id}, actor_type="ui", session_id="pipeline-ui"
    )
    assert removed.success is True
    assert removed.data["canonical_candidate_preserved"] is True
    with factory() as db:
        assert db.get(Candidate, candidate_id) is not None
        assert db.get(HuntCandidate, row_id) is None
        history_id = removed.data["action_id"]
        undo_action(db, history_id)
        restored = db.get(HuntCandidate, row_id)
        assert restored is not None
        assert restored.candidate_id == candidate_id
        assert restored.stage_id == sourced_id
        assert db.get(HuntActivity, activity_id) is not None


def test_pipeline_keep_and_pass_have_exact_undo(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    hunt_id, candidate_id, row_id, sourced_id, screening_id, activity_id, tag_id = _seed(factory)

    kept = dispatch_action("pipeline.triage", {
        "hunt_candidate_id": row_id, "decision": "keep", "note": "Strong reel"
    }, actor_type="ui")
    assert kept.success is True
    with factory() as db:
        assert db.get(HuntCandidate, row_id).stage_id == screening_id
        assert db.scalar(select(PlaybookEntry.id)) is not None
        undo_action(db, kept.data["action_id"])
        assert db.get(HuntCandidate, row_id).stage_id == sourced_id
        assert db.scalar(select(PlaybookEntry.id)) is None
        assert [row.id for row in db.scalars(select(HuntActivity)).all()] == [activity_id]

    passed = dispatch_action("pipeline.triage", {
        "hunt_candidate_id": row_id, "decision": "pass", "note": "Wrong specialty"
    }, actor_type="agent")
    assert passed.success is True
    with factory() as db:
        assert db.get(HuntCandidate, row_id) is None
        assert db.get(Candidate, candidate_id) is not None
        assert db.get(CandidateTag, tag_id) is None
        undo_action(db, passed.data["action_id"])
        assert db.get(HuntCandidate, row_id) is not None
        assert db.get(HuntActivity, activity_id) is not None
        assert db.get(CandidateTag, tag_id) is not None
        assert db.scalar(select(PlaybookEntry.id)) is None


def test_existing_candidate_move_between_hunts_is_reversible(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    old_hunt_id, candidate_id, old_row_id, _, _, activity_id, old_tag_id = _seed(factory)
    with factory() as db:
        new_hunt = TalentHunt(title="Senior Animator Hunt", target_role="Senior Animator")
        db.add(new_hunt)
        db.flush()
        db.add(HuntStage(hunt_id=new_hunt.id, name="Sourced", position=0, color="#19d3c5"))
        db.commit()
        new_hunt_id = new_hunt.id

    moved = dispatch_action("pipeline.enroll", {
        "candidate_id": candidate_id,
        "hunt_id": new_hunt_id,
        "move_from_other_hunts": True,
        "note": "Better aligned role",
    }, actor_type="ui")
    assert moved.success is True
    with factory() as db:
        assert db.get(HuntCandidate, old_row_id) is None
        target = db.get(HuntCandidate, moved.data["hunt_candidate_id"])
        assert target.hunt_id == new_hunt_id
        assert db.get(CandidateTag, old_tag_id) is None
        undo_action(db, moved.data["action_id"])
        assert db.get(HuntCandidate, moved.data["hunt_candidate_id"]) is None
        restored = db.get(HuntCandidate, old_row_id)
        assert restored.hunt_id == old_hunt_id
        assert db.get(HuntActivity, activity_id) is not None
        assert db.get(CandidateTag, old_tag_id) is not None


def test_pipeline_stage_add_undo_refuses_when_stage_is_in_use(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    hunt_id, _, row_id, sourced_id, _, _, _ = _seed(factory)

    added = dispatch_action("pipeline.stages.add", {
        "hunt_id": hunt_id, "name": "Portfolio Review", "color": "#f2b84b"
    }, actor_type="ui")
    assert added.success is True
    stage_id = added.data["stage_id"]
    with factory() as db:
        db.get(HuntCandidate, row_id).stage_id = stage_id
        db.commit()
        try:
            undo_action(db, added.data["action_id"])
        except ValueError as exc:
            assert "Move them out" in str(exc)
        else:
            raise AssertionError("Undo should refuse to delete a stage that contains candidates")

    with factory() as db:
        db.get(HuntCandidate, row_id).stage_id = sourced_id
        db.commit()
        undo_action(db, added.data["action_id"])
        assert db.get(HuntStage, stage_id) is None
        assert db.get(ActionHistory, added.data["action_id"]).status == "undone"


def test_pipeline_page_has_no_direct_pipeline_mutations():
    page = open("app/ui/pages/pipeline.py", encoding="utf-8").read()
    assert "remove_candidate(db" not in page
    assert "keep_hunt_candidate(" not in page
    assert "pass_hunt_candidate(" not in page
    assert "add_candidate_to_hunt(" not in page
    for action in ("pipeline.remove", "pipeline.triage", "pipeline.stages.add", "candidates.create"):
        assert f'"{action}"' in page or f"'{action}'" in page
    candidates_page = open("app/ui/pages/candidates.py", encoding="utf-8").read()
    assert "'pipeline.enroll'" in candidates_page
    assert "add_candidate_to_hunt(" not in candidates_page
