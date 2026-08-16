from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.actions.api import approve_and_dispatch, dispatch_action, dispatch_preview
from app.actions.history import is_undoable
from app.actions.models import ActionHistory
from app.candidates.models import Candidate
from app.communications.models import (
    Communication,
    EmailAccount,
    OutreachEnrollment,
    OutreachSequence,
    OutreachStep,
)
from app.hunts.models import TalentHunt  # noqa: F401 - registers cross-domain tables
from app.infrastructure.db import Base


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'communications-delivery.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _use_factory(monkeypatch, factory):
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.actions.approvals.SessionFactory", factory)
    monkeypatch.setattr("app.actions.locks.SessionFactory", factory)


def _seed_sender_and_candidate(factory, *, email="asha@example.test"):
    with factory() as db:
        db.add(
            EmailAccount(
                email_address="recruiter@example.test",
                display_name="Talent Recruiter",
                smtp_host="127.0.0.1",
                smtp_port=1025,
                use_ssl=False,
                is_default=True,
                is_active=True,
            )
        )
        candidate = Candidate(full_name="Asha Animator", email=email, status="Active")
        db.add(candidate)
        db.commit()
        return candidate.id


def _provider_success(*, to_email, subject, body, from_account=None, cc=None):
    return {
        "success": True,
        "delivered": True,
        "status": "sent",
        "message_id": "<receipt-123@example.test>",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "from": from_account,
        "to": to_email,
        "cc": cc,
        "subject": subject,
        "body_snippet": body[:100],
        "error": None,
    }


def test_direct_email_requires_exact_r4_approval_and_records_receipt(
    monkeypatch, tmp_path
):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    candidate_id = _seed_sender_and_candidate(factory)
    sent = []

    def provider(**kwargs):
        sent.append(kwargs)
        return _provider_success(**kwargs)

    monkeypatch.setattr("app.communications.email_service.send_email", provider)
    payload = {
        "candidate_id": candidate_id,
        "subject": "Spine Animator role",
        "body": "Hi Asha,\n\nWould you be open to a conversation?",
    }
    blocked = dispatch_action(
        "communications.delivery.send",
        payload,
        actor_type="agent",
        user_id=41,
        session_id="delivery-test",
    )
    assert blocked.success is False
    assert "trusted approval" in blocked.error
    assert sent == []

    preview = dispatch_preview(
        "communications.delivery.send",
        payload,
        actor_type="agent",
        user_id=41,
        session_id="delivery-test",
    )
    assert preview.success is True
    assert "token" not in preview.data
    exact = preview.data["preview"]
    assert exact["risk_level"] == "R4"
    assert exact["send_count"] == 1
    assert exact["sender"] == "recruiter@example.test"
    assert exact["recipient"] == "asha@example.test"
    assert exact["subject"] == payload["subject"]
    assert exact["body"] == payload["body"]
    assert exact["irreversible"] is True

    result = approve_and_dispatch(
        preview.data["approval_id"],
        user_id=41,
        session_id="delivery-test",
    )
    assert result.success is True
    assert result.data["delivered"] is True
    assert result.data["undoable"] is False
    assert result.data["provider_receipt"]["message_id"] == "<receipt-123@example.test>"
    assert len(sent) == 1

    with factory() as db:
        communication = db.query(Communication).one()
        history = db.query(ActionHistory).filter_by(action_type="send_communication_email").one()
        assert communication.status == "sent"
        assert communication.provider_name == "smtp"
        assert communication.provider_message_id == "<receipt-123@example.test>"
        assert communication.delivery_key == exact["delivery_key"]
        assert communication.retry_eligible is False
        assert is_undoable(history) is False

    duplicate = dispatch_preview(
        "communications.delivery.send",
        payload,
        actor_type="agent",
        user_id=41,
        session_id="delivery-duplicate",
    )
    assert duplicate.success is False
    assert "already delivered" in duplicate.error.lower()


def test_delivery_rejects_changed_recipient_after_preview(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    candidate_id = _seed_sender_and_candidate(factory)
    monkeypatch.setattr(
        "app.communications.email_service.send_email",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("Changed approved delivery reached SMTP.")
        ),
    )
    preview = dispatch_preview(
        "communications.delivery.send",
        {"candidate_id": candidate_id, "subject": "Hello", "body": "Reviewed body"},
        actor_type="agent",
        user_id=42,
        session_id="delivery-drift",
    )
    with factory() as db:
        db.get(Candidate, candidate_id).email = "changed@example.test"
        db.commit()

    result = approve_and_dispatch(
        preview.data["approval_id"], user_id=42, session_id="delivery-drift"
    )
    assert result.success is False
    assert "changed after approval" in result.error.lower()
    with factory() as db:
        assert db.query(Communication).count() == 0


def test_failed_provider_attempt_is_durable_retryable_and_not_undoable(
    monkeypatch, tmp_path
):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    candidate_id = _seed_sender_and_candidate(factory)
    monkeypatch.setattr(
        "app.communications.email_service.send_email",
        lambda **kwargs: {
            "success": False,
            "delivered": False,
            "status": "failed",
            "message_id": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": "SMTP test failure",
        },
    )
    payload = {"candidate_id": candidate_id, "subject": "Hello", "body": "One message"}
    preview = dispatch_preview(
        "communications.delivery.send",
        payload,
        actor_type="agent",
        user_id=43,
        session_id="delivery-failure",
    )
    result = approve_and_dispatch(
        preview.data["approval_id"], user_id=43, session_id="delivery-failure"
    )
    assert result.success is False
    assert "SMTP test failure" in result.error
    with factory() as db:
        communication = db.query(Communication).one()
        history = db.query(ActionHistory).filter_by(action_type="send_communication_email").one()
        assert communication.status == "failed"
        assert communication.failure_reason == "SMTP test failure"
        assert communication.retry_eligible is True
        assert is_undoable(history) is False

    retry = dispatch_preview(
        "communications.delivery.send",
        payload,
        actor_type="agent",
        user_id=43,
        session_id="delivery-retry",
    )
    assert retry.success is True
    assert retry.data["preview"]["retry_of_communication_id"] == communication.id


def test_approved_sequence_step_advances_once_after_provider_receipt(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    _use_factory(monkeypatch, factory)
    candidate_id = _seed_sender_and_candidate(factory)
    monkeypatch.setattr("app.communications.email_service.send_email", _provider_success)
    with factory() as db:
        sequence = OutreachSequence(name="Animator follow-up", is_active=True)
        db.add(sequence)
        db.flush()
        db.add_all(
            [
                OutreachStep(
                    sequence_id=sequence.id,
                    step_number=1,
                    delay_days=0,
                    channel="email",
                    subject="Hello {{candidate_name}}",
                    body_override="Hi {{candidate_name}}, first message.",
                ),
                OutreachStep(
                    sequence_id=sequence.id,
                    step_number=2,
                    delay_days=3,
                    channel="email",
                    subject="Following up",
                    body_override="Second message.",
                ),
            ]
        )
        enrollment = OutreachEnrollment(
            sequence_id=sequence.id,
            candidate_id=candidate_id,
            current_step_number=1,
            status="active",
            next_step_due_at=datetime.now(timezone.utc),
        )
        db.add(enrollment)
        db.commit()
        enrollment_id = enrollment.id

    due = dispatch_action(
        "communications.deliveries.due.list",
        {},
        actor_type="agent",
        user_id=44,
        session_id="delivery-sequence",
    )
    assert due.success is True
    assert due.data["count"] == 1
    assert due.data["deliveries"][0]["recipient"] == "asha@example.test"

    preview = dispatch_preview(
        "communications.delivery.send",
        {"enrollment_id": enrollment_id},
        actor_type="agent",
        user_id=44,
        session_id="delivery-sequence",
    )
    assert preview.data["preview"]["body"] == "Hi Asha Animator, first message."
    result = approve_and_dispatch(
        preview.data["approval_id"], user_id=44, session_id="delivery-sequence"
    )
    assert result.success is True
    with factory() as db:
        enrollment = db.get(OutreachEnrollment, enrollment_id)
        assert enrollment.current_step_number == 2
        assert enrollment.status == "active"
        assert enrollment.last_step_sent_at is not None
        assert enrollment.next_step_due_at is not None
        assert db.query(Communication).filter_by(status="sent").count() == 1
