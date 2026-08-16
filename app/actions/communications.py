"""Registered Communications actions shared by Copilot and NiceGUI."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.actions.context import ActionContext
from app.actions.history import record_action
from app.actions.registry import register_action

Channel = Literal["email", "linkedin", "naukri", "whatsapp", "phone", "voice_ai"]
Direction = Literal["outbound", "inbound"]
CommunicationStatus = Literal["draft", "logged", "pending", "sent", "received", "read", "failed"]
EnrollmentStatus = Literal["active", "paused", "completed", "replied", "bounced"]


def _actor(ctx: ActionContext) -> str:
    return "copilot" if ctx.actor_type == "agent" else ctx.actor_type


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _communication_payload(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "thread_id": row.thread_id,
        "candidate_id": row.candidate_id,
        "candidate_name": row.candidate.full_name if row.candidate else None,
        "channel": row.channel,
        "direction": row.direction,
        "sender": row.sender,
        "recipient": row.recipient,
        "subject": row.subject,
        "body": row.body,
        "status": row.status,
        "sent_at": _iso(row.sent_at),
        "read_at": _iso(row.read_at),
        "provider_name": row.provider_name,
        "provider_message_id": row.provider_message_id,
        "failure_reason": row.failure_reason,
        "retry_eligible": row.retry_eligible,
        "delivery_key": row.delivery_key,
        "created_at": _iso(row.created_at),
    }


def _template_payload(row) -> dict[str, Any]:
    try:
        variables = json.loads(row.variables_json or "[]")
    except (TypeError, ValueError):
        variables = []
    return {
        "id": row.id,
        "name": row.name,
        "channel": row.channel,
        "category": row.category,
        "subject": row.subject,
        "body_template": row.body_template,
        "variables": variables if isinstance(variables, list) else [],
        "is_active": row.is_active,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _step_payload(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "sequence_id": row.sequence_id,
        "step_number": row.step_number,
        "delay_days": row.delay_days,
        "template_id": row.template_id,
        "channel": row.channel,
        "subject": row.subject,
        "body_override": row.body_override,
    }


def _enrollment_payload(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "sequence_id": row.sequence_id,
        "candidate_id": row.candidate_id,
        "candidate_name": row.candidate.full_name if row.candidate else None,
        "current_step_number": row.current_step_number,
        "status": row.status,
        "enrolled_at": _iso(row.enrolled_at),
        "last_step_sent_at": _iso(row.last_step_sent_at),
        "next_step_due_at": _iso(row.next_step_due_at),
    }


def _sequence_payload(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "channel": row.channel,
        "is_active": row.is_active,
        "steps": [_step_payload(step) for step in row.steps],
        "enrollments": [_enrollment_payload(item) for item in row.enrollments],
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


class CommunicationListInput(BaseModel):
    candidate_id: int | None = Field(default=None, ge=1)
    thread_id: int | None = Field(default=None, ge=1)
    channel: Channel | None = None
    limit: int = Field(default=50, ge=1, le=200)


class CommunicationLogInput(BaseModel):
    candidate_id: int | None = Field(default=None, ge=1)
    thread_id: int | None = Field(default=None, ge=1)
    channel: Channel = "email"
    direction: Direction = "outbound"
    sender: str | None = Field(default=None, max_length=120)
    recipient: str | None = Field(default=None, max_length=120)
    subject: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=100_000)
    status: CommunicationStatus | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommunicationStatusInput(BaseModel):
    communication_id: int = Field(ge=1)
    status: CommunicationStatus


class TemplateListInput(BaseModel):
    channel: Channel | None = None
    include_inactive: bool = False


class TemplateCreateInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    channel: Channel = "email"
    category: str | None = Field(default="Outreach", max_length=50)
    subject: str | None = Field(default=None, max_length=255)
    body_template: str = Field(min_length=1, max_length=100_000)
    variables: list[str] = Field(default_factory=list, max_length=100)


class TemplateUpdateInput(BaseModel):
    template_id: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    channel: Channel | None = None
    category: str | None = Field(default=None, max_length=50)
    subject: str | None = Field(default=None, max_length=255)
    body_template: str | None = Field(default=None, min_length=1, max_length=100_000)
    variables: list[str] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_change(self):
        if not (self.model_fields_set - {"template_id"}):
            raise ValueError("At least one template field must be supplied.")
        return self


class TemplateActiveInput(BaseModel):
    template_id: int = Field(ge=1)
    is_active: bool


class SequenceListInput(BaseModel):
    include_inactive: bool = True


class SequenceCreateInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=10_000)
    channel: Channel = "email"
    initial_subject: str | None = Field(default=None, max_length=255)
    initial_body: str | None = Field(default=None, max_length=100_000)
    initial_template_id: int | None = Field(default=None, ge=1)


class SequenceUpdateInput(BaseModel):
    sequence_id: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=10_000)
    channel: Channel | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not (self.model_fields_set - {"sequence_id"}):
            raise ValueError("At least one sequence field must be supplied.")
        return self


class SequenceActiveInput(BaseModel):
    sequence_id: int = Field(ge=1)
    is_active: bool


class SequenceStepAddInput(BaseModel):
    sequence_id: int = Field(ge=1)
    step_number: int = Field(ge=1, le=100)
    delay_days: int = Field(default=0, ge=0, le=3650)
    template_id: int | None = Field(default=None, ge=1)
    channel: Channel = "email"
    subject: str | None = Field(default=None, max_length=255)
    body_override: str | None = Field(default=None, max_length=100_000)

    @model_validator(mode="after")
    def require_content(self):
        if self.template_id is None and not (self.body_override or "").strip():
            raise ValueError("A template_id or body_override is required.")
        return self


class EnrollmentCreateInput(BaseModel):
    sequence_id: int = Field(ge=1)
    candidate_id: int = Field(ge=1)


class EnrollmentStatusInput(BaseModel):
    enrollment_id: int = Field(ge=1)
    status: EnrollmentStatus


class DeliveryDueListInput(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)


class DeliverySendInput(BaseModel):
    candidate_id: int | None = Field(default=None, ge=1)
    enrollment_id: int | None = Field(default=None, ge=1)
    subject: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=100_000)
    cc: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_one_delivery_mode(self):
        if (self.candidate_id is None) == (self.enrollment_id is None):
            raise ValueError("Supply either candidate_id or enrollment_id, but not both.")
        if self.candidate_id is not None:
            if not (self.subject or "").strip() or not (self.body or "").strip():
                raise ValueError("Direct email requires a subject and body.")
        elif self.subject is not None or self.body is not None:
            raise ValueError(
                "Sequence delivery renders its subject and body from the stored current step."
            )
        return self


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _delivery_digest(parts: dict[str, Any]) -> str:
    canonical = json.dumps(
        parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _valid_email_address(value: str) -> bool:
    if not value or "\r" in value or "\n" in value:
        return False
    _, address = parseaddr(value)
    return address == value and "@" in address and not address.startswith("@")


def _validate_delivery_headers(*, recipient: str, subject: str, cc: str | None) -> None:
    if not _valid_email_address(recipient):
        raise ValueError("Candidate needs a valid email address before delivery can be reviewed.")
    if "\r" in subject or "\n" in subject:
        raise ValueError("Email subject cannot contain line breaks.")
    if cc:
        addresses = [item.strip() for item in cc.split(",") if item.strip()]
        if not addresses or any(not _valid_email_address(item) for item in addresses):
            raise ValueError("CC must contain valid comma-separated email addresses.")


def _resolve_sequence_delivery(db, enrollment_id: int) -> dict[str, Any]:
    from app.candidates.models import Candidate
    from app.communications.models import (
        MessageTemplate,
        OutreachEnrollment,
        OutreachSequence,
        OutreachStep,
    )
    from app.communications.template_engine import generate_candidate_outreach, render_template

    enrollment = db.get(OutreachEnrollment, enrollment_id)
    if not enrollment:
        raise ValueError("Outreach enrollment not found.")
    if enrollment.status != "active":
        raise ValueError("Outreach enrollment must be active before delivery can be reviewed.")
    if not enrollment.next_step_due_at or _aware(enrollment.next_step_due_at) > datetime.now(
        timezone.utc
    ):
        raise ValueError("The current outreach step is not due yet.")
    sequence = db.get(OutreachSequence, enrollment.sequence_id)
    if not sequence or not sequence.is_active:
        raise ValueError("Outreach sequence is paused or unavailable.")
    candidate = db.get(Candidate, enrollment.candidate_id)
    if not candidate:
        raise ValueError("Candidate not found.")
    recipient = (candidate.email or "").strip()

    step = db.scalar(
        select(OutreachStep).where(
            OutreachStep.sequence_id == enrollment.sequence_id,
            OutreachStep.step_number == enrollment.current_step_number,
        )
    )
    if not step:
        raise ValueError("The outreach sequence has no current step to deliver.")
    if step.channel != "email":
        raise ValueError("Only email delivery is available in this approval flow.")

    subject = step.subject or f"Outreach Step {step.step_number}"
    body_template = step.body_override
    if step.template_id:
        template = db.get(MessageTemplate, step.template_id)
        if template:
            body_template = body_template or template.body_template
            subject = step.subject or template.subject or subject
    body_template = body_template or (
        "Hi {{candidate_name}}, following up regarding an opportunity with our team."
    )
    candidate_name = (candidate.full_name or "Candidate").strip()
    context = {
        "candidate_name": candidate_name,
        "first_name": candidate_name.split()[0] if candidate_name else "there",
        "company": "our team",
        "job_title": "Open Role",
        "recruiter_name": "Talent Hunt Recruiter",
    }
    body = generate_candidate_outreach(
        template_body=body_template,
        candidate=candidate,
        recruiter_name="Talent Hunt Recruiter",
        job_title="Open Role",
        company="our team",
    )
    rendered_subject = render_template(subject, context).strip()
    _validate_delivery_headers(recipient=recipient, subject=rendered_subject, cc=None)
    return {
        "mode": "sequence",
        "candidate_id": candidate.id,
        "candidate_name": candidate_name,
        "enrollment_id": enrollment.id,
        "sequence_id": enrollment.sequence_id,
        "sequence_name": sequence.name,
        "step_number": step.step_number,
        "recipient": recipient,
        "subject": rendered_subject,
        "body": body.strip(),
        "cc": None,
        "delivery_key": _delivery_digest(
            {"enrollment_id": enrollment.id, "step_number": step.step_number}
        ),
    }


def _resolve_delivery(data: DeliverySendInput) -> dict[str, Any]:
    from app.candidates.models import Candidate
    from app.communications.email_service import get_delivery_account_summary
    from app.communications.models import Communication
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        if data.enrollment_id is not None:
            resolved = _resolve_sequence_delivery(db, data.enrollment_id)
        else:
            candidate = db.get(Candidate, data.candidate_id)
            if not candidate:
                raise ValueError("Candidate not found.")
            recipient = (candidate.email or "").strip()
            subject = (data.subject or "").strip()
            body = (data.body or "").strip()
            cc = (data.cc or "").strip() or None
            _validate_delivery_headers(recipient=recipient, subject=subject, cc=cc)
            resolved = {
                "mode": "direct",
                "candidate_id": candidate.id,
                "candidate_name": candidate.full_name,
                "enrollment_id": None,
                "sequence_id": None,
                "sequence_name": None,
                "step_number": None,
                "recipient": recipient,
                "subject": subject,
                "body": body,
                "cc": cc,
                "delivery_key": _delivery_digest(
                    {
                        "candidate_id": candidate.id,
                        "recipient": recipient.casefold(),
                        "cc": (cc or "").casefold(),
                        "subject": subject,
                        "body": body,
                    }
                ),
            }

        existing = db.scalar(
            select(Communication).where(
                Communication.delivery_key == resolved["delivery_key"]
            )
        )
        if existing and existing.status == "sent":
            raise ValueError("This exact email was already delivered and cannot be sent twice.")
        if existing and existing.status == "pending":
            raise ValueError(
                "This email has an unresolved delivery attempt. Reconcile it before retrying."
            )
        resolved["retry_of_communication_id"] = (
            existing.id if existing and existing.status == "failed" else None
        )

    account = get_delivery_account_summary()
    if not account["configured"] or not account["email_address"]:
        raise ValueError("Configure and verify an SMTP account before requesting send approval.")
    resolved["sender"] = account["email_address"]
    resolved["sender_name"] = account["display_name"]
    return resolved


def _preview_delivery(data: DeliverySendInput, ctx: ActionContext) -> dict[str, Any]:
    resolved = _resolve_delivery(data)
    return {
        "kind": "communication_delivery",
        "risk_level": "R4",
        "title": f"Send email to {resolved['candidate_name']}",
        "summary": (
            "This external action is irreversible. Review the exact recipient and rendered "
            "message before approving one send."
        ),
        "send_count": 1,
        "channel": "email",
        "irreversible": True,
        **resolved,
    }


def _approved_delivery_preview(ctx: ActionContext) -> dict[str, Any]:
    from app.actions.models import PendingActionApproval
    from app.infrastructure.db import SessionFactory

    approval_id = ctx.metadata.get("approval_id")
    if not approval_id:
        raise PermissionError("The immutable delivery approval preview is unavailable.")
    with SessionFactory() as db:
        approval = db.get(PendingActionApproval, int(approval_id))
        if not approval or approval.action_name != "communications.delivery.send":
            raise PermissionError("The approval is not bound to this delivery action.")
        if approval.user_id != ctx.user_id or approval.session_id != ctx.session_id:
            raise PermissionError("The delivery approval belongs to a different user or session.")
        preview = json.loads(approval.preview_json)
    if preview.get("kind") != "communication_delivery":
        raise PermissionError("The persisted approval preview is not a delivery preview.")
    return preview


def _communication_resource(
    data: CommunicationLogInput | CommunicationStatusInput, ctx: ActionContext
) -> list[str]:
    if isinstance(data, CommunicationStatusInput):
        return [f"communication:{data.communication_id}"]
    keys = ["communications:logs"]
    if data.candidate_id:
        keys.append(f"candidate:{data.candidate_id}")
    if data.thread_id:
        keys.append(f"communication-thread:{data.thread_id}")
    return keys


def _template_resource(data: Any, ctx: ActionContext) -> list[str]:
    template_id = getattr(data, "template_id", None)
    return [f"message-template:{template_id}" if template_id else "message-templates"]


def _sequence_resource(data: Any, ctx: ActionContext) -> list[str]:
    sequence_id = getattr(data, "sequence_id", None)
    keys = [f"outreach-sequence:{sequence_id}" if sequence_id else "outreach-sequences"]
    candidate_id = getattr(data, "candidate_id", None)
    if candidate_id:
        keys.append(f"candidate:{candidate_id}")
    return keys


def _enrollment_resource(data: EnrollmentStatusInput, ctx: ActionContext) -> list[str]:
    return [f"outreach-enrollment:{data.enrollment_id}"]


def _delivery_resource(data: DeliverySendInput, ctx: ActionContext) -> list[str]:
    if data.enrollment_id is not None:
        return [f"outreach-enrollment:{data.enrollment_id}"]
    return [f"candidate:{data.candidate_id}", "communications:delivery"]


@register_action(
    "communications.logs.list",
    description="Read recorded communication history. This never sends a message.",
    input_model=CommunicationListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="list_communication_logs",
)
def list_communication_logs_action(
    data: CommunicationListInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.communications.models import Communication
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        stmt = select(Communication).options(joinedload(Communication.candidate))
        if data.candidate_id is not None:
            stmt = stmt.where(Communication.candidate_id == data.candidate_id)
        if data.thread_id is not None:
            stmt = stmt.where(Communication.thread_id == data.thread_id)
        if data.channel is not None:
            stmt = stmt.where(Communication.channel == data.channel)
        rows = (
            db.scalars(stmt.order_by(Communication.created_at.desc()).limit(data.limit))
            .unique()
            .all()
        )
        return {"count": len(rows), "communications": [_communication_payload(row) for row in rows]}


@register_action(
    "communications.logs.create",
    description="Record a historical inbound or outbound communication. This action never sends anything.",
    input_model=CommunicationLogInput,
    resource_resolver=_communication_resource,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="record_communication_log",
)
def create_communication_log_action(
    data: CommunicationLogInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.candidates.models import Candidate
    from app.communications.models import Communication, CommunicationThread
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = db.get(Candidate, data.candidate_id) if data.candidate_id else None
        if data.candidate_id and not candidate:
            raise ValueError("Candidate not found.")
        thread = db.get(CommunicationThread, data.thread_id) if data.thread_id else None
        if data.thread_id and not thread:
            raise ValueError("Communication thread not found.")
        if thread and data.candidate_id and thread.candidate_id not in {None, data.candidate_id}:
            raise ValueError("The selected thread belongs to another candidate.")

        created_thread = False
        if thread is None and candidate is not None:
            thread = CommunicationThread(
                candidate_id=candidate.id,
                subject=data.subject or f"{data.channel.title()} Thread",
                channel=data.channel,
                status="active",
            )
            db.add(thread)
            db.flush()
            created_thread = True

        default_party = candidate.email or candidate.full_name if candidate else None
        sender = (
            data.sender
            or ("recruiter@talenthunt.os" if data.direction == "outbound" else default_party)
            or ""
        ).strip()
        recipient = (
            data.recipient
            or (default_party if data.direction == "outbound" else "recruiter@talenthunt.os")
            or ""
        ).strip()
        if not sender or not recipient:
            raise ValueError("Sender and recipient could not be resolved.")
        status = data.status or ("logged" if data.direction == "outbound" else "received")
        now = datetime.now(timezone.utc)
        communication = Communication(
            thread_id=thread.id if thread else None,
            candidate_id=data.candidate_id,
            channel=data.channel,
            direction=data.direction,
            sender=sender,
            recipient=recipient,
            subject=(data.subject or "").strip() or None,
            body=data.body.strip(),
            status=status,
            sent_at=now if status in {"sent", "received"} else None,
            metadata_json=json.dumps(data.metadata) if data.metadata else None,
        )
        db.add(communication)
        if thread:
            thread.updated_at = now
        db.flush()
        history = record_action(
            db,
            action_type="create_communication_log",
            summary=f"Recorded {data.direction} {data.channel} communication",
            payload={
                "communication_id": communication.id,
                "candidate_id": data.candidate_id,
                "thread_id": communication.thread_id,
            },
            undo_payload={
                "communication_id": communication.id,
                "created_thread_id": thread.id if created_thread else None,
            },
            actor_type=_actor(ctx),
            session_id=ctx.session_id,
        )
        db.refresh(communication)
        return {
            "status": "success",
            "communication": _communication_payload(communication),
            "history_id": history.id,
            "undoable": True,
            "sent": False,
        }


@register_action(
    "communications.logs.status.set",
    description="Correct the stored status of a communication log. This never performs delivery.",
    input_model=CommunicationStatusInput,
    resource_resolver=_communication_resource,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="set_communication_log_status",
)
def set_communication_status_action(
    data: CommunicationStatusInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.communications.models import Communication
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        row = db.get(Communication, data.communication_id)
        if not row:
            raise ValueError("Communication not found.")
        previous = {
            "status": row.status,
            "sent_at": _iso(row.sent_at),
            "read_at": _iso(row.read_at),
        }
        row.status = data.status
        now = datetime.now(timezone.utc)
        if data.status == "read" and row.read_at is None:
            row.read_at = now
        if data.status in {"sent", "received"} and row.sent_at is None:
            row.sent_at = now
        history = record_action(
            db,
            action_type="set_communication_status",
            summary=f"Set communication #{row.id} status to {data.status}",
            payload={
                "communication_id": row.id,
                "candidate_id": row.candidate_id,
                "status": data.status,
            },
            undo_payload={"communication_id": row.id, **previous},
            actor_type=_actor(ctx),
            session_id=ctx.session_id,
        )
        return {
            "status": "success",
            "communication_id": row.id,
            "new_status": row.status,
            "history_id": history.id,
            "undoable": True,
            "sent": False,
        }


@register_action(
    "communications.templates.list",
    description="Read reusable communication templates, optionally including archived templates.",
    input_model=TemplateListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="list_message_templates",
)
def list_templates_action(data: TemplateListInput, ctx: ActionContext) -> dict[str, Any]:
    from app.communications.models import MessageTemplate
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        stmt = select(MessageTemplate)
        if data.channel is not None:
            stmt = stmt.where(MessageTemplate.channel == data.channel)
        if not data.include_inactive:
            stmt = stmt.where(MessageTemplate.is_active.is_(True))
        rows = db.scalars(stmt.order_by(MessageTemplate.name.asc())).all()
        return {"count": len(rows), "templates": [_template_payload(row) for row in rows]}


@register_action(
    "communications.templates.create",
    description="Create a reusable draft template. Creating a template never sends a message.",
    input_model=TemplateCreateInput,
    resource_resolver=_template_resource,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="create_message_template",
)
def create_template_action(data: TemplateCreateInput, ctx: ActionContext) -> dict[str, Any]:
    from app.communications.models import MessageTemplate
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        row = MessageTemplate(
            name=data.name.strip(),
            channel=data.channel,
            category=(data.category or "").strip() or None,
            subject=(data.subject or "").strip() or None,
            body_template=data.body_template.strip(),
            variables_json=json.dumps(data.variables),
            is_active=True,
        )
        db.add(row)
        db.flush()
        history = record_action(
            db,
            action_type="create_message_template",
            summary=f"Created message template '{row.name}'",
            payload={"template_id": row.id},
            undo_payload={"template_id": row.id},
            actor_type=_actor(ctx),
            session_id=ctx.session_id,
        )
        db.refresh(row)
        return {
            "status": "success",
            "template": _template_payload(row),
            "history_id": history.id,
            "undoable": True,
        }


@register_action(
    "communications.templates.update",
    description="Update a reusable communication template without sending it.",
    input_model=TemplateUpdateInput,
    resource_resolver=_template_resource,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="update_message_template",
)
def update_template_action(data: TemplateUpdateInput, ctx: ActionContext) -> dict[str, Any]:
    from app.communications.models import MessageTemplate
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        row = db.get(MessageTemplate, data.template_id)
        if not row:
            raise ValueError("Message template not found.")
        previous = _template_payload(row)
        for field in data.model_fields_set - {"template_id", "variables"}:
            value = getattr(data, field)
            if isinstance(value, str):
                value = value.strip() or None
            setattr(row, field, value)
        if "variables" in data.model_fields_set:
            row.variables_json = json.dumps(data.variables or [])
        history = record_action(
            db,
            action_type="update_message_template",
            summary=f"Updated message template '{row.name}'",
            payload={"template_id": row.id},
            undo_payload={"template": previous},
            actor_type=_actor(ctx),
            session_id=ctx.session_id,
        )
        return {
            "status": "success",
            "template": _template_payload(row),
            "history_id": history.id,
            "undoable": True,
        }


@register_action(
    "communications.templates.active.set",
    description="Archive or restore a message template without deleting sequence history.",
    input_model=TemplateActiveInput,
    resource_resolver=_template_resource,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="set_message_template_active",
)
def set_template_active_action(data: TemplateActiveInput, ctx: ActionContext) -> dict[str, Any]:
    from app.communications.models import MessageTemplate
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        row = db.get(MessageTemplate, data.template_id)
        if not row:
            raise ValueError("Message template not found.")
        previous = row.is_active
        row.is_active = data.is_active
        history = record_action(
            db,
            action_type="set_message_template_active",
            summary=f"{'Restored' if data.is_active else 'Archived'} message template '{row.name}'",
            payload={"template_id": row.id, "is_active": data.is_active},
            undo_payload={"template_id": row.id, "is_active": previous},
            actor_type=_actor(ctx),
            session_id=ctx.session_id,
        )
        return {
            "status": "success",
            "template_id": row.id,
            "is_active": row.is_active,
            "history_id": history.id,
            "undoable": True,
        }


@register_action(
    "communications.sequences.list",
    description="Read outreach sequences, their draft steps, and enrollment state. This never processes due sends.",
    input_model=SequenceListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="list_outreach_sequences",
)
def list_sequences_action(data: SequenceListInput, ctx: ActionContext) -> dict[str, Any]:
    from app.communications.models import OutreachEnrollment, OutreachSequence
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        stmt = select(OutreachSequence).options(
            joinedload(OutreachSequence.steps),
            joinedload(OutreachSequence.enrollments).joinedload(OutreachEnrollment.candidate),
        )
        if not data.include_inactive:
            stmt = stmt.where(OutreachSequence.is_active.is_(True))
        rows = db.scalars(stmt.order_by(OutreachSequence.created_at.desc())).unique().all()
        return {"count": len(rows), "sequences": [_sequence_payload(row) for row in rows]}


@register_action(
    "communications.sequences.create",
    description="Create an outreach sequence and optional first draft step. This never sends or processes the sequence.",
    input_model=SequenceCreateInput,
    resource_resolver=_sequence_resource,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="create_outreach_sequence",
)
def create_sequence_action(data: SequenceCreateInput, ctx: ActionContext) -> dict[str, Any]:
    from app.communications.models import MessageTemplate, OutreachSequence, OutreachStep
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        if data.initial_template_id and not db.get(MessageTemplate, data.initial_template_id):
            raise ValueError("Initial message template not found.")
        row = OutreachSequence(
            name=data.name.strip(),
            description=(data.description or "").strip() or None,
            channel=data.channel,
            is_active=True,
        )
        db.add(row)
        db.flush()
        step_ids: list[int] = []
        if data.initial_template_id or (data.initial_body or "").strip():
            step = OutreachStep(
                sequence_id=row.id,
                step_number=1,
                delay_days=0,
                template_id=data.initial_template_id,
                channel=data.channel,
                subject=(data.initial_subject or "").strip() or None,
                body_override=(data.initial_body or "").strip() or None,
            )
            db.add(step)
            db.flush()
            step_ids.append(step.id)
        history = record_action(
            db,
            action_type="create_outreach_sequence",
            summary=f"Created outreach sequence '{row.name}'",
            payload={"sequence_id": row.id},
            undo_payload={"sequence_id": row.id, "created_step_ids": step_ids},
            actor_type=_actor(ctx),
            session_id=ctx.session_id,
        )
        details = db.scalar(
            select(OutreachSequence)
            .options(joinedload(OutreachSequence.steps), joinedload(OutreachSequence.enrollments))
            .where(OutreachSequence.id == row.id)
        )
        return {
            "status": "success",
            "sequence": _sequence_payload(details),
            "history_id": history.id,
            "undoable": True,
            "sent": False,
        }


@register_action(
    "communications.sequences.update",
    description="Update sequence metadata without changing enrollment progress or sending messages.",
    input_model=SequenceUpdateInput,
    resource_resolver=_sequence_resource,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="update_outreach_sequence",
)
def update_sequence_action(data: SequenceUpdateInput, ctx: ActionContext) -> dict[str, Any]:
    from app.communications.models import OutreachSequence
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        row = db.get(OutreachSequence, data.sequence_id)
        if not row:
            raise ValueError("Outreach sequence not found.")
        previous = {"name": row.name, "description": row.description, "channel": row.channel}
        for field in data.model_fields_set - {"sequence_id"}:
            value = getattr(data, field)
            if isinstance(value, str):
                value = value.strip() or None
            setattr(row, field, value)
        history = record_action(
            db,
            action_type="update_outreach_sequence",
            summary=f"Updated outreach sequence '{row.name}'",
            payload={"sequence_id": row.id},
            undo_payload={"sequence_id": row.id, **previous},
            actor_type=_actor(ctx),
            session_id=ctx.session_id,
        )
        return {
            "status": "success",
            "sequence_id": row.id,
            "history_id": history.id,
            "undoable": True,
            "sent": False,
        }


@register_action(
    "communications.sequences.active.set",
    description="Pause or restore an outreach sequence. This changes local state only and never sends messages.",
    input_model=SequenceActiveInput,
    resource_resolver=_sequence_resource,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="set_outreach_sequence_active",
)
def set_sequence_active_action(data: SequenceActiveInput, ctx: ActionContext) -> dict[str, Any]:
    from app.communications.models import OutreachSequence
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        row = db.get(OutreachSequence, data.sequence_id)
        if not row:
            raise ValueError("Outreach sequence not found.")
        previous = row.is_active
        row.is_active = data.is_active
        history = record_action(
            db,
            action_type="set_outreach_sequence_active",
            summary=f"{'Restored' if data.is_active else 'Paused'} outreach sequence '{row.name}'",
            payload={"sequence_id": row.id, "is_active": data.is_active},
            undo_payload={"sequence_id": row.id, "is_active": previous},
            actor_type=_actor(ctx),
            session_id=ctx.session_id,
        )
        return {
            "status": "success",
            "sequence_id": row.id,
            "is_active": row.is_active,
            "history_id": history.id,
            "undoable": True,
            "sent": False,
        }


@register_action(
    "communications.sequence_steps.add",
    description="Add a draft step to an outreach sequence. This action never sends or schedules a worker.",
    input_model=SequenceStepAddInput,
    resource_resolver=_sequence_resource,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="add_outreach_sequence_step",
)
def add_sequence_step_action(data: SequenceStepAddInput, ctx: ActionContext) -> dict[str, Any]:
    from app.communications.models import MessageTemplate, OutreachSequence, OutreachStep
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        sequence = db.get(OutreachSequence, data.sequence_id)
        if not sequence:
            raise ValueError("Outreach sequence not found.")
        if data.template_id and not db.get(MessageTemplate, data.template_id):
            raise ValueError("Message template not found.")
        duplicate = db.scalar(
            select(OutreachStep).where(
                OutreachStep.sequence_id == data.sequence_id,
                OutreachStep.step_number == data.step_number,
            )
        )
        if duplicate:
            raise ValueError(f"Sequence already has step {data.step_number}.")
        row = OutreachStep(
            sequence_id=data.sequence_id,
            step_number=data.step_number,
            delay_days=data.delay_days,
            template_id=data.template_id,
            channel=data.channel,
            subject=(data.subject or "").strip() or None,
            body_override=(data.body_override or "").strip() or None,
        )
        db.add(row)
        db.flush()
        history = record_action(
            db,
            action_type="add_outreach_step",
            summary=f"Added step {row.step_number} to outreach sequence '{sequence.name}'",
            payload={"sequence_id": sequence.id, "step_id": row.id},
            undo_payload={
                "sequence_id": sequence.id,
                "step_id": row.id,
                "step_number": row.step_number,
            },
            actor_type=_actor(ctx),
            session_id=ctx.session_id,
        )
        db.refresh(row)
        return {
            "status": "success",
            "step": _step_payload(row),
            "history_id": history.id,
            "undoable": True,
            "sent": False,
        }


@register_action(
    "communications.enrollments.create",
    description="Enroll a candidate in a sequence in local paused state. Enrollment never starts delivery by itself.",
    input_model=EnrollmentCreateInput,
    resource_resolver=_sequence_resource,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="enroll_candidate_in_outreach",
)
def create_enrollment_action(data: EnrollmentCreateInput, ctx: ActionContext) -> dict[str, Any]:
    from app.candidates.models import Candidate
    from app.communications.models import OutreachEnrollment, OutreachSequence
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = db.get(Candidate, data.candidate_id)
        sequence = db.get(OutreachSequence, data.sequence_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        if not sequence:
            raise ValueError("Outreach sequence not found.")
        existing = db.scalar(
            select(OutreachEnrollment).where(
                OutreachEnrollment.sequence_id == data.sequence_id,
                OutreachEnrollment.candidate_id == data.candidate_id,
                OutreachEnrollment.status.in_(["active", "paused"]),
            )
        )
        if existing:
            raise ValueError(
                "Candidate is already enrolled in this sequence; update that enrollment instead."
            )
        row = OutreachEnrollment(
            sequence_id=data.sequence_id,
            candidate_id=data.candidate_id,
            current_step_number=1,
            status="paused",
            enrolled_at=datetime.now(timezone.utc),
            next_step_due_at=None,
        )
        db.add(row)
        db.flush()
        history = record_action(
            db,
            action_type="enroll_outreach_candidate",
            summary=f"Enrolled {candidate.full_name} in '{sequence.name}' (paused)",
            payload={
                "sequence_id": sequence.id,
                "candidate_id": candidate.id,
                "enrollment_id": row.id,
            },
            undo_payload={"enrollment_id": row.id},
            actor_type=_actor(ctx),
            session_id=ctx.session_id,
        )
        db.refresh(row)
        return {
            "status": "success",
            "enrollment": _enrollment_payload(row),
            "history_id": history.id,
            "undoable": True,
            "sent": False,
        }


@register_action(
    "communications.enrollments.status.set",
    description="Pause, resume, or close a local outreach enrollment. Resuming does not send; delivery still requires approval.",
    input_model=EnrollmentStatusInput,
    resource_resolver=_enrollment_resource,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="set_outreach_enrollment_status",
)
def set_enrollment_status_action(data: EnrollmentStatusInput, ctx: ActionContext) -> dict[str, Any]:
    from app.communications.models import OutreachEnrollment
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        row = db.get(OutreachEnrollment, data.enrollment_id)
        if not row:
            raise ValueError("Outreach enrollment not found.")
        previous = {"status": row.status, "next_step_due_at": _iso(row.next_step_due_at)}
        row.status = data.status
        if data.status == "active":
            row.next_step_due_at = datetime.now(timezone.utc)
        elif data.status in {"completed", "replied", "bounced"}:
            row.next_step_due_at = None
        history = record_action(
            db,
            action_type="set_outreach_enrollment_status",
            summary=f"Set outreach enrollment #{row.id} to {data.status}",
            payload={
                "sequence_id": row.sequence_id,
                "candidate_id": row.candidate_id,
                "enrollment_id": row.id,
                "status": data.status,
            },
            undo_payload={"enrollment_id": row.id, **previous},
            actor_type=_actor(ctx),
            session_id=ctx.session_id,
        )
        return {
            "status": "success",
            "enrollment": _enrollment_payload(row),
            "history_id": history.id,
            "undoable": True,
            "sent": False,
        }


@register_action(
    "communications.deliveries.due.list",
    description="List exact rendered email messages that are due for approval. This never sends.",
    input_model=DeliveryDueListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="list_due_outreach_deliveries",
)
def list_due_deliveries_action(
    data: DeliveryDueListInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.communications.models import OutreachEnrollment
    from app.infrastructure.db import SessionFactory

    now = datetime.now(timezone.utc)
    with SessionFactory() as db:
        enrollment_ids = list(
            db.scalars(
                select(OutreachEnrollment.id)
                .where(
                    OutreachEnrollment.status == "active",
                    OutreachEnrollment.next_step_due_at.is_not(None),
                    OutreachEnrollment.next_step_due_at <= now,
                )
                .order_by(OutreachEnrollment.next_step_due_at, OutreachEnrollment.id)
                .limit(data.limit)
            ).all()
        )

    deliveries: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for enrollment_id in enrollment_ids:
        try:
            delivery = _resolve_delivery(DeliverySendInput(enrollment_id=enrollment_id))
            deliveries.append(
                {
                    "enrollment_id": delivery["enrollment_id"],
                    "candidate_id": delivery["candidate_id"],
                    "candidate_name": delivery["candidate_name"],
                    "sequence_name": delivery["sequence_name"],
                    "step_number": delivery["step_number"],
                    "sender": delivery["sender"],
                    "recipient": delivery["recipient"],
                    "subject": delivery["subject"],
                    "body": delivery["body"],
                    "retry": delivery["retry_of_communication_id"] is not None,
                }
            )
        except Exception as exc:
            blocked.append({"enrollment_id": enrollment_id, "reason": str(exc)})
    return {
        "status": "success",
        "count": len(deliveries),
        "deliveries": deliveries,
        "blocked": blocked,
        "sent": False,
    }


@register_action(
    "communications.delivery.send",
    description=(
        "Request one exact email send. Copilot can create the immutable R4 preview, but only "
        "the authenticated approval control can execute it."
    ),
    input_model=DeliverySendInput,
    preview_handler=_preview_delivery,
    resource_resolver=_delivery_resource,
    requires_approval=True,
    classification="mutation",
    risk_level="R4",
    required_scopes=("write",),
    version=1,
    copilot_enabled=True,
    copilot_tool_name="send_approved_email",
)
def send_approved_email_action(
    data: DeliverySendInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.communications.email_service import send_email
    from app.communications.models import Communication, OutreachEnrollment, OutreachStep
    from app.infrastructure.db import SessionFactory

    approved = _approved_delivery_preview(ctx)
    current = _resolve_delivery(data)
    immutable_fields = (
        "mode",
        "candidate_id",
        "enrollment_id",
        "step_number",
        "sender",
        "recipient",
        "cc",
        "subject",
        "body",
        "delivery_key",
    )
    if any(current.get(field) != approved.get(field) for field in immutable_fields):
        raise ValueError(
            "Recipient or rendered message changed after approval. Review a fresh preview."
        )

    approval_id = int(ctx.metadata["approval_id"])
    with SessionFactory() as db:
        communication = db.scalar(
            select(Communication).where(
                Communication.delivery_key == approved["delivery_key"]
            )
        )
        if communication and communication.status == "sent":
            raise ValueError("This exact email was already delivered.")
        if communication and communication.status == "pending":
            raise ValueError(
                "This email has an unresolved delivery attempt. Reconcile it before retrying."
            )
        metadata = {
            "approval_id": approval_id,
            "mode": approved["mode"],
            "enrollment_id": approved.get("enrollment_id"),
            "sequence_id": approved.get("sequence_id"),
            "step_number": approved.get("step_number"),
        }
        if communication:
            if not communication.retry_eligible:
                raise ValueError("The previous failed attempt is not eligible for retry.")
            communication.status = "pending"
            communication.failure_reason = None
            communication.retry_eligible = False
            communication.metadata_json = json.dumps(metadata)
            communication.sent_at = None
        else:
            communication = Communication(
                candidate_id=approved["candidate_id"],
                channel="email",
                direction="outbound",
                sender=approved["sender"],
                recipient=approved["recipient"],
                subject=approved["subject"],
                body=approved["body"],
                status="pending",
                sent_at=None,
                metadata_json=json.dumps(metadata),
                provider_name="smtp",
                retry_eligible=False,
                delivery_key=approved["delivery_key"],
            )
            db.add(communication)
        db.commit()
        db.refresh(communication)
        communication_id = communication.id

    provider_result = send_email(
        to_email=approved["recipient"],
        subject=approved["subject"],
        body=approved["body"],
        from_account=approved["sender"],
        cc=approved.get("cc"),
    )
    delivered = bool(provider_result.get("success") and provider_result.get("delivered"))
    completed_at = datetime.now(timezone.utc)

    with SessionFactory() as db:
        communication = db.get(Communication, communication_id)
        if not communication:
            raise RuntimeError("Delivery completed but its durable communication record is missing.")
        communication.provider_name = "smtp"
        communication.provider_message_id = provider_result.get("message_id")
        communication.sent_at = completed_at if delivered else None
        communication.status = "sent" if delivered else "failed"
        communication.failure_reason = None if delivered else (
            provider_result.get("error") or "SMTP provider did not confirm delivery."
        )
        communication.retry_eligible = not delivered

        if approved.get("enrollment_id"):
            enrollment = db.get(OutreachEnrollment, int(approved["enrollment_id"]))
            if not enrollment or enrollment.current_step_number != int(approved["step_number"]):
                raise RuntimeError(
                    "Delivery state changed before the sequence progression could be recorded."
                )
            if delivered:
                next_number = enrollment.current_step_number + 1
                next_step = db.scalar(
                    select(OutreachStep).where(
                        OutreachStep.sequence_id == enrollment.sequence_id,
                        OutreachStep.step_number == next_number,
                    )
                )
                enrollment.last_step_sent_at = completed_at
                if next_step:
                    enrollment.current_step_number = next_number
                    enrollment.next_step_due_at = completed_at + timedelta(
                        days=next_step.delay_days
                    )
                else:
                    enrollment.status = "completed"
                    enrollment.next_step_due_at = None
            else:
                enrollment.status = "paused"
                enrollment.next_step_due_at = None

        history = record_action(
            db,
            action_type="send_communication_email",
            summary=(
                f"Sent email to {approved['candidate_name']}"
                if delivered
                else f"Email delivery failed for {approved['candidate_name']}"
            ),
            payload={
                "communication_id": communication.id,
                "candidate_id": approved["candidate_id"],
                "enrollment_id": approved.get("enrollment_id"),
                "recipient": approved["recipient"],
                "provider_message_id": communication.provider_message_id,
                "delivery_key": communication.delivery_key,
                "delivered": delivered,
                "irreversible": delivered,
            },
            undo_payload=None,
            actor_type=_actor(ctx),
            session_id=ctx.session_id,
        )
        db.refresh(communication)
        payload = _communication_payload(communication)

    if not delivered:
        raise RuntimeError(payload["failure_reason"] or "Email delivery failed.")
    return {
        "status": "sent",
        "delivered": True,
        "sent": True,
        "undoable": False,
        "external_effect": True,
        "communication": payload,
        "history_id": history.id,
        "provider_receipt": {
            "provider": "smtp",
            "message_id": provider_result.get("message_id"),
            "timestamp": provider_result.get("timestamp"),
        },
    }
