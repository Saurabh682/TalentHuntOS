from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.actions.api import dispatch_action
from app.actions.history import undo_action
from app.hunts.models import TalentHunt
from app.infrastructure.db import Base
from app.jobs.models import BackgroundJob


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'hunt-actions.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.actions.locks.SessionFactory", factory)


def _create_hunt():
    return dispatch_action("hunts.create", {
        "title": "Spine Animator Hunt",
        "target_role": "Spine Animator",
        "location": "Noida, India",
        "salary_range": "12-18 LPA",
        "description": "Build game animation rigs.",
        "required_skills": "Spine, 2D Animation",
        "preferred_skills": "After Effects",
        "experience": "4-8 years",
        "industry": "Gaming",
        "target_platforms": ["linkedin", "naukri"],
    }, actor_type="ui", session_id="hunt-create")


def test_hunt_create_list_get_update_status_and_undo(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)

    created = _create_hunt()
    assert created.success is True
    hunt_id = created.data["hunt_id"]

    listed = dispatch_action("hunts.list", {"search": "spine"}, actor_type="agent")
    assert listed.success is True
    assert listed.data["count"] == 1
    assert listed.data["hunts"][0]["id"] == hunt_id

    fetched = dispatch_action("hunts.get", {"hunt_id": hunt_id}, actor_type="agent")
    hunt = fetched.data["hunt"]
    assert hunt["search_config"]["experience_years_min"] == 4
    assert hunt["search_config"]["experience_years_max"] == 8
    assert len(hunt["stages"]) == 7

    updated = dispatch_action("hunts.update", {
        "hunt_id": hunt_id,
        "title": "Senior Spine Animator Hunt",
        "location": "Remote, India",
        "salary_range": None,
        "required_skills": "Spine, Unity",
        "experience": "6+",
        "industry": None,
    }, actor_type="ui", session_id=f"hunt_{hunt_id}")
    assert updated.success is True
    assert set(updated.data["changed_fields"]) >= {
        "title", "location", "salary_range", "required_skills", "experience", "industry"
    }
    with factory() as db:
        row = db.get(TalentHunt, hunt_id)
        assert row.title == "Senior Spine Animator Hunt"
        assert row.salary_range is None
        assert row.search_config.experience_years_min == 6
        assert row.search_config.experience_years_max is None
        undo_action(db, updated.data["action_id"])
        row = db.get(TalentHunt, hunt_id)
        assert row.title == "Spine Animator Hunt"
        assert row.salary_range == "12-18 LPA"
        assert row.search_config.required_skills == "Spine, 2D Animation"
        assert row.search_config.industry == "Gaming"

    paused = dispatch_action("hunts.status.set", {
        "hunt_id": hunt_id, "status": "Paused"
    }, actor_type="agent")
    assert paused.success is True
    with factory() as db:
        assert db.get(TalentHunt, hunt_id).status == "Paused"
        undo_action(db, paused.data["action_id"])
        assert db.get(TalentHunt, hunt_id).status == "Active"

    with factory() as db:
        undo_action(db, created.data["action_id"])
        assert db.get(TalentHunt, hunt_id) is None


def test_hunt_creation_undo_refuses_after_background_work(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    created = _create_hunt()
    hunt_id = created.data["hunt_id"]
    with factory() as db:
        db.add(BackgroundJob(
            id="huntjob1", kind="sourcing", status="done", hunt_id=hunt_id,
            hunt_title="Spine Animator Hunt", label="Sourcing", message="Done",
        ))
        db.commit()
        try:
            undo_action(db, created.data["action_id"])
        except ValueError as exc:
            assert "workflow history" in str(exc)
        else:
            raise AssertionError("Creation Undo should preserve Hunts with sourcing history")
        assert db.get(TalentHunt, hunt_id) is not None


def test_hunts_ui_and_copilot_do_not_directly_mutate_lifecycle():
    hunts_page = open("app/ui/pages/hunts.py", encoding="utf-8").read()
    management_tools = open("app/copilot/mgmt_tools.py", encoding="utf-8").read()
    launcher = open("app/hunts/launch.py", encoding="utf-8").read()
    assert "update_hunt(db" not in hunts_page
    assert "HuntSearchConfig(" not in hunts_page
    assert "update_hunt(db" not in management_tools
    assert '"hunts.update"' in management_tools
    assert '"hunts.status.set"' in management_tools
    assert '"hunts.create"' in launcher
