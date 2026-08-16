"""Trusted adapters for dispatching registered OS actions."""

from __future__ import annotations

from typing import Any

from app.actions.context import ActionContext, ActorType
from app.actions.registry import ActionResult, execute_action, preview_action


def ensure_core_actions_registered() -> None:
    # Register both sides of cross-domain ORM relationships before an action opens a
    # session. Copilot adapters can be invoked from a cold worker without app.main.
    import app.hunts.models  # noqa: F401
    from app.actions import (
        ai_runtime,  # noqa: F401
        communications,  # noqa: F401
        recruiting,  # noqa: F401
        reports,  # noqa: F401
        sites,  # noqa: F401
    )


def dispatch_action(
    name: str,
    input_data: dict[str, Any] | None = None,
    *,
    actor_type: ActorType = "ui",
    session_id: str | None = None,
    idempotency_key: str | None = None,
    scopes: list[str] | None = None,
    user_id: int | None = None,
    approval_token: str | None = None,
    request_id: str | None = None,
) -> ActionResult:
    """Dispatch one action through validation, policy, ledger, and handler layers."""
    ensure_core_actions_registered()
    if user_id is None and actor_type in {"ui", "agent"}:
        from app.infrastructure.auth import get_active_admin_id

        user_id = get_active_admin_id()
    ctx = ActionContext.create(
        actor_type=actor_type,
        user_id=user_id,
        session_id=session_id,
        scopes=scopes,
        approval_token=approval_token,
        idempotency_key=idempotency_key,
        metadata={"trusted_adapter": True},
    )
    if request_id:
        ctx.request_id = request_id
    return execute_action(name, input_data or {}, ctx)


def dispatch_preview(
    name: str,
    input_data: dict[str, Any] | None = None,
    *,
    actor_type: ActorType = "ui",
    session_id: str,
    scopes: list[str] | None = None,
    user_id: int | None = None,
) -> ActionResult:
    """Create a durable preview for an approval-gated action."""
    ensure_core_actions_registered()
    if user_id is None:
        from app.infrastructure.auth import get_active_admin_id

        user_id = get_active_admin_id()
    ctx = ActionContext.create(
        actor_type=actor_type,
        user_id=user_id,
        session_id=session_id,
        scopes=scopes,
        metadata={"trusted_adapter": True, "approval_preview": True},
    )
    return preview_action(name, input_data or {}, ctx)


def approve_and_dispatch(
    approval_id: int,
    *,
    user_id: int | None = None,
    session_id: str,
    actor_type: ActorType = "ui",
) -> ActionResult:
    """Approve in trusted UI code, then execute the exact persisted input once."""
    if user_id is None:
        from app.infrastructure.auth import get_active_admin_id

        user_id = get_active_admin_id()
    if user_id is None:
        return ActionResult(
            success=False,
            error="Authenticated administrator identity is required.",
            action_name="actions.approve",
        )
    from app.actions.approvals import approve_pending_approval

    try:
        approved = approve_pending_approval(
            approval_id,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception as exc:
        return ActionResult(
            success=False,
            error=str(exc),
            action_name="actions.approve",
        )
    result = dispatch_action(
        approved["action_name"],
        approved["input"],
        actor_type=actor_type,
        user_id=user_id,
        session_id=session_id,
        approval_token=approved["token"],
        request_id=approved["request_id"],
        idempotency_key=f"approval:{approval_id}",
    )
    if not result.success and result.metadata.get("lock_conflicts"):
        from app.actions.approvals import reopen_approval_after_lock_conflict

        try:
            reopen_approval_after_lock_conflict(
                approval_id,
                user_id=user_id,
                session_id=session_id,
            )
            result.metadata["approval_reopened"] = True
            result.metadata["approval_id"] = approval_id
        except Exception as exc:
            result.metadata["approval_reopen_error"] = str(exc)
    return result


def cancel_approval(
    approval_id: int,
    *,
    user_id: int | None = None,
    session_id: str,
) -> ActionResult:
    if user_id is None:
        from app.infrastructure.auth import get_active_admin_id

        user_id = get_active_admin_id()
    if user_id is None:
        return ActionResult(
            success=False, error="Authentication required.", action_name="actions.cancel"
        )
    from app.actions.approvals import cancel_pending_approval

    try:
        cancel_pending_approval(approval_id, user_id=user_id, session_id=session_id)
        return ActionResult(
            success=True,
            data={"status": "cancelled", "approval_id": approval_id},
            action_name="actions.cancel",
        )
    except Exception as exc:
        return ActionResult(success=False, error=str(exc), action_name="actions.cancel")
