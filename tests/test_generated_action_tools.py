import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.actions.models import ActionExecution, ActionToolCall
from app.candidates.models import Candidate
from app.communications.models import Communication, EmailAccount
from app.copilot.session_ctx import set_active_session_id
from app.copilot.tools import get_copilot_tools
from app.hunts.models import TalentHunt
from app.infrastructure.db import Base, User


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'generated-tools.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.actions.approvals.SessionFactory", factory)
    monkeypatch.setattr("app.actions.locks.SessionFactory", factory)
    monkeypatch.setattr("app.actions.tool_calls.SessionFactory", factory)


def _tool(name):
    tools = get_copilot_tools()
    assert len({item.name for item in tools}) == len(tools)
    return next(item for item in tools if item.name == name)


def test_registry_generates_unique_typed_copilot_tools():
    tools = {item.name: item for item in get_copilot_tools()}
    expected = {
        "list_candidate_records": "candidates.list",
        "add_candidate_to_database": "candidates.create",
        "get_candidate_record": "candidates.get",
        "find_candidate_duplicates": "candidates.duplicates.list",
        "merge_candidate_records": "candidates.merge",
        "update_candidate_record": "candidates.update",
        "archive_candidate_record": "candidates.archive",
        "add_candidate_tag": "candidates.tags.add",
        "remove_candidate_tag": "candidates.tags.remove",
        "add_candidate_note": "candidates.notes.add",
        "save_candidate_experience": "candidates.experiences.save",
        "remove_candidate_experience": "candidates.experiences.remove",
        "save_candidate_education": "candidates.educations.save",
        "remove_candidate_education": "candidates.educations.remove",
        "apply_candidate_profile_sections": "candidates.profile.apply",
        "set_candidate_rogue_status": "candidates.rogue.set",
        "list_discovery_records": "discoveries.list",
        "get_discovery_record": "discoveries.get",
        "list_common_pool": "discoveries.common_pool.list",
        "archive_discoveries_common_pool": "discoveries.common_pool.archive",
        "approve_discovery": "discoveries.approve",
        "reject_discovery": "discoveries.reject",
        "get_pipeline_board": "pipeline.get",
        "enroll_candidate_in_hunt": "pipeline.enroll",
        "move_pipeline_by_id": "pipeline.move",
        "remove_pipeline_by_id": "pipeline.remove",
        "triage_pipeline_by_id": "pipeline.triage",
        "add_pipeline_stage": "pipeline.stages.add",
        "list_hunt_records": "hunts.list",
        "get_hunt_record": "hunts.get",
        "create_hunt_record": "hunts.create",
        "update_hunt_record": "hunts.update",
        "set_hunt_lifecycle_status": "hunts.status.set",
        "archive_hunt_by_id": "hunts.archive",
        "get_recruiting_kpis": "analytics.kpi",
        "get_recruiting_funnel": "analytics.funnel",
        "get_time_to_fill_analytics": "analytics.time_to_fill",
        "get_sourcing_quality_analytics": "analytics.sourcing_quality",
        "get_outreach_analytics": "analytics.outreach",
        "get_ai_usage_costs": "analytics.ai_cost",
        "get_recruiting_trends": "analytics.trends",
        "create_analytics_report": "reports.analytics.create",
        "list_report_artifacts": "reports.list",
        "get_report_artifact": "reports.get",
        "list_communication_logs": "communications.logs.list",
        "record_communication_log": "communications.logs.create",
        "set_communication_log_status": "communications.logs.status.set",
        "list_message_templates": "communications.templates.list",
        "create_message_template": "communications.templates.create",
        "update_message_template": "communications.templates.update",
        "set_message_template_active": "communications.templates.active.set",
        "list_outreach_sequences": "communications.sequences.list",
        "create_outreach_sequence": "communications.sequences.create",
        "update_outreach_sequence": "communications.sequences.update",
        "set_outreach_sequence_active": "communications.sequences.active.set",
        "add_outreach_sequence_step": "communications.sequence_steps.add",
        "enroll_candidate_in_outreach": "communications.enrollments.create",
        "set_outreach_enrollment_status": "communications.enrollments.status.set",
        "list_due_outreach_deliveries": "communications.deliveries.due.list",
        "send_approved_email": "communications.delivery.send",
        "undo_recent_action": "actions.undo",
        "list_background_jobs": "jobs.list",
        "get_background_job": "jobs.get",
        "cancel_background_job": "jobs.cancel",
        "retry_background_job": "jobs.retry",
        "list_connected_sites": "sites.list",
        "connect_site_login": "sites.connect",
        "reconnect_site_login": "sites.reconnect",
        "verify_site_login": "sites.verify",
        "save_site_login": "sites.connect.save",
        "disconnect_site": "sites.disconnect",
        "get_embedded_ai_status": "ai.runtime.status",
        "install_embedded_ai": "ai.runtime.install",
        "start_embedded_ai": "ai.runtime.start",
        "stop_embedded_ai": "ai.runtime.stop",
        "configure_embedded_ai": "ai.runtime.configure",
    }
    for tool_name, action_name in expected.items():
        assert tools[tool_name].metadata["generated_action"] is True
        assert tools[tool_name].metadata["audited_tool"] is True
        assert tools[tool_name].metadata["action_name"] == action_name
        assert tools[tool_name].args_schema is not None


def test_generated_action_tool_records_and_links_execution(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        candidate = Candidate(full_name="Generated Tool Candidate", status="Active")
        db.add(candidate)
        db.commit()
        candidate_id = candidate.id

    set_active_session_id("hunt_generated")
    try:
        payload = json.loads(_tool("get_candidate_record").invoke({"candidate_id": candidate_id}))
    finally:
        set_active_session_id(None)
    assert payload["status"] == "success"
    with factory() as db:
        call = db.query(ActionToolCall).one()
        execution = db.query(ActionExecution).one()
        assert call.tool_name == "get_candidate_record"
        assert call.action_name == "candidates.get"
        assert call.action_execution_id == execution.id
        assert call.session_id == "hunt_generated"
        assert call.status == "completed"
        assert json.loads(call.input_json) == {"candidate_id": candidate_id}
        assert call.duration_ms is not None


def test_generated_tool_failure_and_secret_redaction_are_audited(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    set_active_session_id("audit_failure")
    try:
        payload = json.loads(_tool("get_candidate_record").invoke({"candidate_id": 999}))
    finally:
        set_active_session_id(None)
    assert payload["status"] == "error"

    from app.actions.tool_calls import begin_tool_call, finish_tool_call

    row_id, started = begin_tool_call(
        tool_name="secret-test",
        action_name=None,
        session_id="audit_failure",
        input_payload={"api_key": "should-not-persist", "nested": {"password": "hidden"}},
    )
    finish_tool_call(row_id, started, output={"status": "success"})
    with factory() as db:
        failed = db.query(ActionToolCall).filter_by(tool_name="get_candidate_record").one()
        secret = db.query(ActionToolCall).filter_by(tool_name="secret-test").one()
        assert failed.status == "failed"
        assert failed.error == "Candidate not found."
        assert json.loads(secret.input_json) == {
            "api_key": "[REDACTED]",
            "nested": {"password": "[REDACTED]"},
        }


def test_generated_r3_tool_only_creates_trusted_preview(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        db.add(User(username="admin", role="admin", is_active=True))
        hunt = TalentHunt(title="Preview Hunt", target_role="Animator")
        db.add(hunt)
        db.commit()
        hunt_id = hunt.id

    set_active_session_id(f"hunt_{hunt_id}")
    try:
        payload = json.loads(_tool("archive_hunt_by_id").invoke({"hunt_id": hunt_id}))
    finally:
        set_active_session_id(None)
    assert payload["status"] == "success"
    assert payload["data"]["status"] == "pending"
    assert "token" not in payload["data"]
    with factory() as db:
        assert db.get(TalentHunt, hunt_id).status == "Active"
        call = db.query(ActionToolCall).one()
        assert call.status == "completed"
        assert call.action_name == "hunts.archive"


def test_generated_r4_email_tool_only_creates_preview(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    with factory() as db:
        db.add(User(username="admin", role="admin", is_active=True))
        db.add(
            EmailAccount(
                email_address="recruiter@example.test",
                smtp_host="127.0.0.1",
                smtp_port=1025,
                use_ssl=False,
                is_default=True,
                is_active=True,
            )
        )
        candidate = Candidate(
            full_name="Preview Candidate",
            email="preview@example.test",
            status="Active",
        )
        db.add(candidate)
        db.commit()
        candidate_id = candidate.id

    monkeypatch.setattr(
        "app.communications.email_service.send_email",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("Generated R4 tool invoked SMTP without UI approval.")
        ),
    )
    set_active_session_id("communications-r4-preview")
    try:
        payload = json.loads(
            _tool("send_approved_email").invoke(
                {
                    "candidate_id": candidate_id,
                    "subject": "Reviewed subject",
                    "body": "Reviewed body",
                }
            )
        )
    finally:
        set_active_session_id(None)
    assert payload["status"] == "success"
    assert payload["data"]["status"] == "pending"
    assert payload["data"]["preview"]["risk_level"] == "R4"
    assert "token" not in payload["data"]
    with factory() as db:
        assert db.query(Communication).count() == 0
        call = db.query(ActionToolCall).one()
        assert call.action_name == "communications.delivery.send"
        assert call.action_execution_id is None
