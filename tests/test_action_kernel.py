import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.actions.api import (
    approve_and_dispatch,
    cancel_approval,
    dispatch_action,
    dispatch_preview,
    ensure_core_actions_registered,
)
from app.actions.approvals import approve_pending_approval
from app.actions.history import undo_action
from app.actions.context import ActionContext
from app.actions.locks import acquire_resource_locks, release_resource_locks
from app.actions.models import ActionExecution, ActionHistory, ActionResourceLock
from app.actions.registry import list_actions, register_action
from app.candidates.discovery import record_discovery
from app.candidates.models import Candidate, DiscoveryHuntMatch
from app.candidates.service import create_candidate
from app.hunts.models import HuntCandidate, HuntStage, TalentHunt
from app.infrastructure.db import Base


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'action-kernel.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.actions.approvals.SessionFactory", factory)
    monkeypatch.setattr("app.actions.locks.SessionFactory", factory)
    monkeypatch.setattr(
        "app.candidates.search.candidate_search_index.index_candidate",
        lambda **kwargs: None,
    )
    monkeypatch.setattr("app.candidates.service._reindex_candidate", lambda *args: None)


def test_core_action_manifest_has_risk_scope_and_version():
    ensure_core_actions_registered()
    actions = {item["name"]: item for item in list_actions()}
    assert set(actions) >= {
        "candidates.list",
        "candidates.create",
        "candidates.get",
        "candidates.duplicates.list",
        "candidates.merge",
        "candidates.update",
        "candidates.archive",
        "candidates.tags.add",
        "candidates.tags.remove",
        "candidates.notes.add",
        "candidates.experiences.save",
        "candidates.experiences.remove",
        "candidates.educations.save",
        "candidates.educations.remove",
        "candidates.profile.apply",
        "candidates.rogue.set",
        "discoveries.list",
        "discoveries.get",
        "discoveries.common_pool.list",
        "discoveries.approve",
        "discoveries.reject",
        "pipeline.get",
        "pipeline.enroll",
        "pipeline.move",
        "pipeline.remove",
        "pipeline.triage",
        "pipeline.stages.add",
        "hunts.list",
        "hunts.get",
        "hunts.create",
        "hunts.update",
        "hunts.status.set",
        "hunts.archive",
        "actions.undo",
        "jobs.retry",
    }
    assert actions["candidates.get"]["risk_level"] == "R0"
    assert actions["candidates.list"]["risk_level"] == "R0"
    assert actions["candidates.create"]["risk_level"] == "R2"
    assert actions["candidates.duplicates.list"]["risk_level"] == "R0"
    assert actions["candidates.merge"]["risk_level"] == "R3"
    assert actions["candidates.merge"]["requires_approval"] is True
    assert actions["candidates.merge"]["has_preview"] is True
    assert actions["discoveries.common_pool.list"]["risk_level"] == "R0"
    assert actions["pipeline.get"]["risk_level"] == "R0"
    assert actions["pipeline.remove"]["risk_level"] == "R2"
    assert actions["pipeline.triage"]["risk_level"] == "R2"
    assert actions["candidates.get"]["required_scopes"] == ["read"]
    assert actions["candidates.update"]["risk_level"] == "R2"
    assert actions["candidates.update"]["version"] == 1
    assert actions["hunts.archive"]["risk_level"] == "R3"
    assert actions["hunts.list"]["risk_level"] == "R0"
    assert actions["hunts.get"]["risk_level"] == "R0"
    assert actions["hunts.create"]["risk_level"] == "R2"
    assert actions["hunts.update"]["risk_level"] == "R2"
    assert actions["hunts.status.set"]["risk_level"] == "R2"
    assert actions["hunts.archive"]["requires_approval"] is True
    assert actions["hunts.archive"]["has_preview"] is True
    assert actions["hunts.archive"]["uses_resource_locks"] is True
    assert actions["candidates.get"]["uses_resource_locks"] is False
    assert actions["actions.undo"]["risk_level"] == "R2"
    assert actions["actions.undo"]["uses_resource_locks"] is True
    assert actions["actions.undo"]["copilot_enabled"] is True
    assert actions["actions.undo"]["copilot_tool_name"] == "undo_recent_action"
    assert actions["jobs.retry"]["risk_level"] == "R2"
    assert actions["jobs.retry"]["copilot_tool_name"] == "retry_background_job"


def test_resource_lock_blocks_concurrent_mutation_then_releases(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    started = threading.Event()
    finish = threading.Event()
    first_result = {}

    @register_action(
        "tests.locked-mutation",
        resource_resolver=lambda data, ctx: ["candidate:77"],
    )
    def locked_mutation(data, ctx):
        started.set()
        assert finish.wait(3)
        return {"status": "success"}

    worker = threading.Thread(
        target=lambda: first_result.setdefault(
            "result",
            dispatch_action("tests.locked-mutation", actor_type="ui", session_id="first"),
        )
    )
    worker.start()
    assert started.wait(2)

    blocked = dispatch_action(
        "tests.locked-mutation",
        actor_type="agent",
        session_id="second",
    )
    assert blocked.success is False
    assert "Resource busy" in blocked.error
    assert blocked.metadata["lock_conflicts"][0]["resource_key"] == "candidate:77"

    finish.set()
    worker.join(3)
    assert first_result["result"].success is True
    with factory() as db:
        assert db.query(ActionResourceLock).filter_by(status="active").count() == 0


def test_expired_resource_lock_is_recovered(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        db.add(ActionResourceLock(
            lease_id="stale",
            resource_key="hunt:3",
            action_name="tests.crashed",
            request_id="old-request",
            status="active",
            acquired_at=datetime.now(timezone.utc) - timedelta(hours=1),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        ))
        db.commit()

    lease = acquire_resource_locks(
        ["hunt:3"],
        action_name="tests.recovered",
        ctx=ActionContext.create(actor_type="system", session_id="recovery"),
    )
    assert lease
    release_resource_locks(lease)
    with factory() as db:
        assert db.query(ActionResourceLock).filter_by(lease_id="stale").one().status == "expired"
        assert db.query(ActionResourceLock).filter_by(lease_id=lease).one().status == "released"


def test_resource_lock_releases_when_handler_fails(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)

    @register_action(
        "tests.failing-locked-mutation",
        resource_resolver=lambda data, ctx: ["candidate:91"],
    )
    def failing_mutation(data, ctx):
        raise RuntimeError("planned failure")

    failed = dispatch_action("tests.failing-locked-mutation", session_id="failure-test")
    assert failed.success is False
    assert failed.error == "planned failure"
    lease = acquire_resource_locks(
        ["candidate:91"],
        action_name="tests.after-failure",
        ctx=ActionContext.create(actor_type="system", session_id="recovery"),
    )
    assert lease
    release_resource_locks(lease)


def test_lock_conflict_does_not_consume_hunt_approval(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        hunt = TalentHunt(title="Locked Hunt", target_role="Animator")
        db.add(hunt)
        db.commit()
        hunt_id = hunt.id

    session_id = f"hunt_{hunt_id}"
    preview = dispatch_preview(
        "hunts.archive",
        {"hunt_id": hunt_id},
        actor_type="agent",
        user_id=13,
        session_id=session_id,
    )
    blocker = acquire_resource_locks(
        [f"hunt:{hunt_id}"],
        action_name="tests.long-hunt-action",
        ctx=ActionContext.create(actor_type="system", session_id="background"),
    )
    blocked = approve_and_dispatch(
        preview.data["approval_id"],
        user_id=13,
        session_id=session_id,
    )
    assert blocked.success is False
    assert "Resource busy" in blocked.error
    assert blocked.metadata["approval_reopened"] is True

    release_resource_locks(blocker)
    completed = approve_and_dispatch(
        preview.data["approval_id"],
        user_id=13,
        session_id=session_id,
    )
    assert completed.success is True


def test_hunt_archive_requires_exact_one_time_trusted_approval(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        hunt = TalentHunt(title="Animator Hunt", target_role="Animator")
        db.add(hunt)
        db.flush()
        db.add(HuntCandidate(hunt_id=hunt.id, full_name="Asha Rao", status="Active"))
        db.commit()
        hunt_id = hunt.id

    blocked = dispatch_action(
        "hunts.archive",
        {"hunt_id": hunt_id},
        actor_type="agent",
        user_id=7,
        session_id=f"hunt_{hunt_id}",
    )
    assert blocked.success is False
    assert "trusted approval" in blocked.error

    preview = dispatch_preview(
        "hunts.archive",
        {"hunt_id": hunt_id},
        actor_type="agent",
        user_id=7,
        session_id=f"hunt_{hunt_id}",
    )
    assert preview.success is True
    assert "token" not in preview.data
    assert preview.data["preview"]["pipeline_candidates"] == 1

    result = approve_and_dispatch(
        preview.data["approval_id"],
        user_id=7,
        session_id=f"hunt_{hunt_id}",
    )
    assert result.success is True
    assert result.data["new_status"] == "Archived"
    assert result.data["undoable"] is True

    replay = approve_and_dispatch(
        preview.data["approval_id"],
        user_id=7,
        session_id=f"hunt_{hunt_id}",
    )
    assert replay.success is False
    assert "consumed" in replay.error

    with factory() as db:
        assert db.get(TalentHunt, hunt_id).status == "Archived"
        assert db.query(ActionHistory).filter_by(action_type="archive_hunt").count() == 1


def test_hunt_archive_approval_rejects_parameter_or_session_substitution(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        first = TalentHunt(title="First Hunt", target_role="Animator")
        second = TalentHunt(title="Second Hunt", target_role="Designer")
        db.add_all([first, second])
        db.commit()
        first_id, second_id = first.id, second.id

    preview = dispatch_preview(
        "hunts.archive",
        {"hunt_id": first_id},
        actor_type="agent",
        user_id=9,
        session_id=f"hunt_{first_id}",
    )
    approved = approve_pending_approval(
        preview.data["approval_id"],
        user_id=9,
        session_id=f"hunt_{first_id}",
    )
    changed = dispatch_action(
        "hunts.archive",
        {"hunt_id": second_id},
        actor_type="ui",
        user_id=9,
        session_id=f"hunt_{first_id}",
        approval_token=approved["token"],
        request_id=approved["request_id"],
    )
    assert changed.success is False
    assert "parameters changed" in changed.error.lower()

    wrong_session = dispatch_action(
        "hunts.archive",
        {"hunt_id": first_id},
        actor_type="ui",
        user_id=9,
        session_id="hunt_other",
        approval_token=approved["token"],
        request_id=approved["request_id"],
    )
    assert wrong_session.success is False
    assert "different user or session" in wrong_session.error.lower()
    with factory() as db:
        assert db.get(TalentHunt, first_id).status == "Active"
        assert db.get(TalentHunt, second_id).status == "Active"


def test_cancelled_hunt_archive_cannot_be_approved(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        hunt = TalentHunt(title="Cancelled Hunt", target_role="Animator")
        db.add(hunt)
        db.commit()
        hunt_id = hunt.id

    preview = dispatch_preview(
        "hunts.archive",
        {"hunt_id": hunt_id},
        actor_type="agent",
        user_id=11,
        session_id=f"hunt_{hunt_id}",
    )
    cancelled = cancel_approval(
        preview.data["approval_id"],
        user_id=11,
        session_id=f"hunt_{hunt_id}",
    )
    assert cancelled.success is True
    result = approve_and_dispatch(
        preview.data["approval_id"],
        user_id=11,
        session_id=f"hunt_{hunt_id}",
    )
    assert result.success is False
    assert "cancelled" in result.error


def test_candidate_update_is_audited_idempotent_and_undoable(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        candidate = create_candidate(
            db,
            full_name="Asha Rao",
            current_title="Animator",
            location="Noida",
            skills=["Spine"],
        )
        candidate_id = candidate.id

    denied = dispatch_action(
        "candidates.update",
        {"candidate_id": candidate_id, "current_title": "Lead Animator"},
        actor_type="agent",
        scopes=["read"],
    )
    assert denied.success is False
    assert "write" in denied.error

    first = dispatch_action(
        "candidates.update",
        {
            "candidate_id": candidate_id,
            "current_title": "Lead Animator",
            "skills": ["Spine", "After Effects"],
        },
        actor_type="agent",
        session_id="hunt_1",
        idempotency_key="candidate-update-1",
    )
    assert first.success is True
    assert first.data["changed"] is True
    assert first.data["undoable"] is True

    replay = dispatch_action(
        "candidates.update",
        {
            "candidate_id": candidate_id,
            "current_title": "Lead Animator",
            "skills": ["Spine", "After Effects"],
        },
        actor_type="agent",
        session_id="hunt_1",
        idempotency_key="candidate-update-1",
    )
    assert replay.success is True
    assert replay.metadata["idempotent_replay"] is True
    assert replay.metadata["execution_id"] == first.metadata["execution_id"]

    with factory() as db:
        assert db.query(ActionExecution).count() == 1
        assert db.query(ActionHistory).count() == 1
        updated = db.get(Candidate, candidate_id)
        assert updated.current_title == "Lead Animator"
        action_id = db.scalar(select(ActionHistory.id))
        undo_action(db, action_id)
        assert db.get(Candidate, candidate_id).current_title == "Animator"


def test_candidate_get_returns_structured_profile(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        candidate = create_candidate(
            db,
            full_name="Asha Rao",
            current_title="Animator",
            skills=["Spine"],
        )
        candidate_id = candidate.id

    result = dispatch_action(
        "candidates.get",
        {"candidate_id": candidate_id},
        actor_type="agent",
        scopes=["read"],
    )
    assert result.success is True
    assert result.data["candidate"]["full_name"] == "Asha Rao"
    assert result.data["candidate"]["skills"] == ["Spine"]
    assert result.metadata["risk_level"] == "R0"


def test_registered_undo_restores_candidate_through_shared_kernel(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        candidate = create_candidate(db, full_name="Undo Candidate", current_title="Animator")
        candidate_id = candidate.id

    changed = dispatch_action(
        "candidates.update",
        {"candidate_id": candidate_id, "current_title": "Lead Animator"},
        actor_type="agent",
        session_id="hunt_undo",
    )
    assert changed.success is True
    action_id = changed.data["action_id"]

    undone = dispatch_action(
        "actions.undo",
        {"action_id": action_id},
        actor_type="ui",
        session_id="hunt_undo",
    )
    assert undone.success is True
    assert undone.data["action"]["status"] == "undone"
    assert undone.data["action"]["target"]["url"] == f"/candidates/{candidate_id}"
    assert undone.metadata["resource_keys"] == [f"candidate:{candidate_id}"]
    with factory() as db:
        assert db.get(Candidate, candidate_id).current_title == "Animator"
        assert db.get(ActionHistory, action_id).status == "undone"
        assert db.query(ActionExecution).filter_by(action_name="actions.undo").count() == 1


def test_discovery_reject_is_retained_audited_and_undoable(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        hunt = TalentHunt(title="Animator Hunt", target_role="Animator")
        db.add(hunt)
        db.commit()
        profile, match = record_discovery(
            db,
            hunt_id=hunt.id,
            url="https://linkedin.com/in/asha-rao",
            platform="linkedin",
            source_query="animator",
            full_name="Asha Rao",
            status="shortlisted",
        )
        match_id = match.id
        profile_id = profile.id

    result = dispatch_action(
        "discoveries.reject",
        {"match_id": match_id, "reason": "Role mismatch"},
        actor_type="ui",
        session_id="hunt_1",
    )
    assert result.success is True
    assert result.data["undoable"] is True

    with factory() as db:
        match = db.get(DiscoveryHuntMatch, match_id)
        assert match.status == "rejected"
        assert match.discovered_profile_id == profile_id
        action = db.scalar(
            select(ActionHistory).where(ActionHistory.action_type == "reject_discovered_profile")
        )
        undo_action(db, action.id)
        assert db.get(DiscoveryHuntMatch, match_id).status == "shortlisted"


def test_discovery_approve_starts_background_scan(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    called = threading.Event()
    received = {}

    def fake_import(match_id, *, actor_type):
        received.update({"match_id": match_id, "actor_type": actor_type})
        called.set()
        return {"status": "success"}

    monkeypatch.setattr("app.candidates.discovery.import_approved_discovery", fake_import)
    with factory() as db:
        hunt = TalentHunt(title="Animator Hunt", target_role="Animator")
        db.add(hunt)
        db.commit()
        _, match = record_discovery(
            db,
            hunt_id=hunt.id,
            url="https://linkedin.com/in/asha-rao",
            platform="linkedin",
            source_query="animator",
            full_name="Asha Rao",
            status="shortlisted",
        )
        match_id = match.id

    result = dispatch_action(
        "discoveries.approve",
        {"match_id": match_id},
        actor_type="agent",
        session_id="hunt_1",
    )
    assert result.success is True
    assert result.data["started"] is True
    assert called.wait(2)
    assert received == {"match_id": match_id, "actor_type": "copilot"}
    with factory() as db:
        assert db.get(DiscoveryHuntMatch, match_id).status == "approved"


def test_pipeline_move_uses_shared_action_and_undo(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        hunt = TalentHunt(title="Animator Hunt", target_role="Animator")
        db.add(hunt)
        db.flush()
        sourced = HuntStage(hunt_id=hunt.id, name="Sourced", position=0)
        screening = HuntStage(hunt_id=hunt.id, name="Screening", position=1)
        db.add_all([sourced, screening])
        db.flush()
        row = HuntCandidate(
            hunt_id=hunt.id,
            stage_id=sourced.id,
            full_name="Asha Rao",
            status="Active",
        )
        db.add(row)
        db.commit()
        row_id, sourced_id, screening_id = row.id, sourced.id, screening.id

    result = dispatch_action(
        "pipeline.move",
        {"hunt_candidate_id": row_id, "stage_id": screening_id},
        actor_type="ui",
        session_id="hunt_1",
    )
    assert result.success is True
    assert result.data["stage"] == "Screening"

    with factory() as db:
        assert db.get(HuntCandidate, row_id).stage_id == screening_id
        action = db.scalar(
            select(ActionHistory).where(ActionHistory.action_type == "move_pipeline_candidate")
        )
        undo_action(db, action.id)
        assert db.get(HuntCandidate, row_id).stage_id == sourced_id


def test_target_ui_commands_and_copilot_use_action_dispatcher():
    root = Path(__file__).parents[1]
    candidate_page = (root / "app/ui/pages/candidate_detail.py").read_text(encoding="utf-8")
    discoveries_page = (root / "app/ui/pages/discoveries.py").read_text(encoding="utf-8")
    pipeline_page = (root / "app/ui/pages/pipeline.py").read_text(encoding="utf-8")
    hunts_page = (root / "app/ui/pages/hunts.py").read_text(encoding="utf-8")
    management_tools = (root / "app/copilot/mgmt_tools.py").read_text(encoding="utf-8")
    copilot_panel = (root / "app/ui/panels/copilot_panel.py").read_text(encoding="utf-8")
    copilot_tools = (root / "app/copilot/tools.py").read_text(encoding="utf-8")

    assert '"candidates.update"' in candidate_page
    assert '"candidates.tags.add"' in candidate_page
    assert '"candidates.tags.remove"' in candidate_page
    assert '"candidates.notes.add"' in candidate_page
    assert '"candidates.experiences.save"' in candidate_page
    assert '"candidates.educations.save"' in candidate_page
    profile_review = (root / "app/ui/components/profile_review_dialog.py").read_text(encoding="utf-8")
    assert '"candidates.profile.apply"' in profile_review
    candidate_list_page = (root / "app/ui/pages/candidates.py").read_text(encoding="utf-8")
    assert '"candidates.archive"' in candidate_list_page
    assert '"candidates.create"' in candidate_list_page
    assert "create_candidate(" not in candidate_list_page
    assert '"candidates.rogue.set"' in candidate_list_page
    assert '"candidates.duplicates.list"' in candidate_list_page
    assert '"candidates.merge"' in candidate_list_page
    assert "delete_candidate(" not in candidate_list_page
    assert "mark_candidate_rogue(" not in candidate_list_page
    assert "clear_candidate_rogue(" not in candidate_list_page
    assert '"discoveries.approve"' in discoveries_page
    assert '"discoveries.reject"' in discoveries_page
    assert '"pipeline.move"' in pipeline_page
    assert '"pipeline.move"' in management_tools
    assert "move_candidate_stage(" not in pipeline_page
    assert '"hunts.archive"' in hunts_page
    assert '"hunts.archive"' in management_tools
    assert "from app.hunts.service import delete_hunt" not in hunts_page
    assert "from app.hunts.service import delete_hunt" not in management_tools
    assert "'actions.undo'" in copilot_panel
    assert '"actions.undo"' in copilot_tools
    assert "undo_action(undo_db" not in copilot_panel
    assert "_refresh_completed_action_cards" in copilot_panel
