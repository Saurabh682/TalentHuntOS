"""Durable, action-bound human approvals for sensitive operations."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update

from app.actions.context import ActionContext
from app.actions.models import PendingActionApproval
from app.infrastructure.db import SessionFactory


APPROVAL_TTL_MINUTES = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def approval_fingerprint(
    action_name: str,
    action_version: int,
    input_payload: Any,
    ctx: ActionContext,
) -> str:
    """Bind approval to action, parameters, authenticated user, session, and request."""
    payload = {
        "action": action_name,
        "version": int(action_version),
        "input": input_payload,
        "user_id": ctx.user_id,
        "session_id": ctx.session_id,
        "request_id": ctx.request_id,
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def create_pending_approval(
    *,
    action_name: str,
    action_version: int,
    input_payload: Any,
    preview: dict[str, Any],
    ctx: ActionContext,
    ttl_minutes: int = APPROVAL_TTL_MINUTES,
) -> dict[str, Any]:
    """Persist an immutable preview. No executable token is returned here."""
    if not ctx.identity_verified or ctx.user_id is None:
        raise PermissionError("Authenticated user identity is required for approval.")
    if not ctx.session_id:
        raise PermissionError("A bound session is required for approval.")

    fingerprint = approval_fingerprint(action_name, action_version, input_payload, ctx)
    now = _now()
    expires = now + timedelta(minutes=max(1, min(int(ttl_minutes), 30)))
    with SessionFactory() as db:
        existing = db.scalar(
            select(PendingActionApproval).where(
                PendingActionApproval.fingerprint == fingerprint,
                PendingActionApproval.user_id == ctx.user_id,
                PendingActionApproval.session_id == ctx.session_id,
                PendingActionApproval.status == "pending",
            ).order_by(PendingActionApproval.id.desc())
        )
        if existing and _aware(existing.expires_at) > now:
            return serialize_pending_approval(existing)

        row = PendingActionApproval(
            action_name=action_name,
            action_version=action_version,
            fingerprint=fingerprint,
            user_id=ctx.user_id,
            actor_type=ctx.actor_type,
            session_id=ctx.session_id,
            request_id=ctx.request_id,
            status="pending",
            input_json=_canonical(input_payload),
            preview_json=_canonical(preview),
            created_at=now,
            expires_at=expires,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return serialize_pending_approval(row)


def approve_pending_approval(
    approval_id: int,
    *,
    user_id: int,
    session_id: str,
) -> dict[str, Any]:
    """Approve one preview and return its raw one-time token only to trusted UI code."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now = _now()
    with SessionFactory() as db:
        row = db.get(PendingActionApproval, int(approval_id))
        if not row:
            raise ValueError("Approval request was not found.")
        if row.user_id != int(user_id) or row.session_id != session_id:
            raise PermissionError("Approval request belongs to a different user or session.")
        if row.status != "pending":
            raise ValueError(f"Approval request is already {row.status}.")
        if _aware(row.expires_at) <= now:
            row.status = "expired"
            db.commit()
            raise ValueError("Approval request has expired. Preview the action again.")

        changed = db.execute(
            update(PendingActionApproval)
            .where(
                PendingActionApproval.id == row.id,
                PendingActionApproval.status == "pending",
            )
            .values(status="approved", token_hash=token_hash, approved_at=now)
        )
        if changed.rowcount != 1:
            db.rollback()
            raise ValueError("Approval request changed before it could be approved.")
        db.commit()
        return {
            "approval_id": row.id,
            "action_name": row.action_name,
            "action_version": row.action_version,
            "input": json.loads(row.input_json),
            "preview": json.loads(row.preview_json),
            "request_id": row.request_id,
            "token": raw_token,
        }


def consume_approval_token(
    token: str,
    *,
    action_name: str,
    action_version: int,
    input_payload: Any,
    ctx: ActionContext,
) -> int:
    """Validate and atomically consume a one-time token before action execution."""
    if not token or not ctx.identity_verified or ctx.user_id is None or not ctx.session_id:
        raise PermissionError("A trusted, authenticated approval token is required.")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expected = approval_fingerprint(action_name, action_version, input_payload, ctx)
    now = _now()
    with SessionFactory() as db:
        row = db.scalar(
            select(PendingActionApproval).where(
                PendingActionApproval.token_hash == token_hash
            )
        )
        if not row or not hmac.compare_digest(row.token_hash or "", token_hash):
            raise PermissionError("Approval token is invalid.")
        if row.status != "approved":
            raise PermissionError(f"Approval token is already {row.status}.")
        if _aware(row.expires_at) <= now:
            row.status = "expired"
            db.commit()
            raise PermissionError("Approval token has expired.")
        if row.user_id != ctx.user_id or row.session_id != ctx.session_id:
            raise PermissionError("Approval token belongs to a different user or session.")
        if row.action_name != action_name or row.action_version != action_version:
            raise PermissionError("Approval token is bound to a different action.")
        if not hmac.compare_digest(row.fingerprint, expected):
            raise PermissionError("Action parameters changed after approval.")

        changed = db.execute(
            update(PendingActionApproval)
            .where(
                PendingActionApproval.id == row.id,
                PendingActionApproval.status == "approved",
                PendingActionApproval.token_hash == token_hash,
            )
            .values(status="consumed", consumed_at=now)
        )
        if changed.rowcount != 1:
            db.rollback()
            raise PermissionError("Approval token was already consumed.")
        db.commit()
        return row.id


def cancel_pending_approval(
    approval_id: int,
    *,
    user_id: int,
    session_id: str,
) -> None:
    with SessionFactory() as db:
        row = db.get(PendingActionApproval, int(approval_id))
        if not row:
            raise ValueError("Approval request was not found.")
        if row.user_id != int(user_id) or row.session_id != session_id:
            raise PermissionError("Approval request belongs to a different user or session.")
        if row.status not in {"pending", "approved"}:
            raise ValueError(f"Approval request is already {row.status}.")
        row.status = "cancelled"
        row.cancelled_at = _now()
        db.commit()


def reopen_approval_after_lock_conflict(
    approval_id: int,
    *,
    user_id: int,
    session_id: str,
) -> None:
    """Return an unconsumed approval to the visible queue after a lock conflict."""
    with SessionFactory() as db:
        changed = db.execute(
            update(PendingActionApproval)
            .where(
                PendingActionApproval.id == int(approval_id),
                PendingActionApproval.user_id == int(user_id),
                PendingActionApproval.session_id == session_id,
                PendingActionApproval.status == "approved",
                PendingActionApproval.consumed_at.is_(None),
            )
            .values(status="pending", token_hash=None, approved_at=None)
        )
        if changed.rowcount != 1:
            db.rollback()
            raise ValueError("Approval could not be reopened after the resource conflict.")
        db.commit()


def list_pending_approvals(*, user_id: int, session_id: str | None = None) -> list[dict[str, Any]]:
    now = _now()
    with SessionFactory() as db:
        stmt = select(PendingActionApproval).where(
            PendingActionApproval.user_id == int(user_id),
            PendingActionApproval.status == "pending",
        )
        if session_id:
            stmt = stmt.where(PendingActionApproval.session_id == session_id)
        rows = list(db.scalars(stmt.order_by(PendingActionApproval.id.desc())).all())
        result = []
        changed = False
        for row in rows:
            if _aware(row.expires_at) <= now:
                row.status = "expired"
                changed = True
                continue
            result.append(serialize_pending_approval(row))
        if changed:
            db.commit()
        return result


def serialize_pending_approval(row: PendingActionApproval) -> dict[str, Any]:
    return {
        "approval_id": row.id,
        "action_name": row.action_name,
        "action_version": row.action_version,
        "status": row.status,
        "input": json.loads(row.input_json),
        "preview": json.loads(row.preview_json),
        "session_id": row.session_id,
        "created_at": row.created_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
    }
