"""Central Action Registry and Command Dispatcher for TalentHunt OS."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from app.actions.context import ActionContext

logger = logging.getLogger("talenthunt.actions")

ActionClassification = Literal["query", "mutation", "ai_task", "system"]
ActionRisk = Literal["R0", "R1", "R2", "R3", "R4", "R5"]


class ActionResult(BaseModel):
    """Standardized response container for action execution."""

    success: bool
    data: Any = None
    error: str | None = None
    action_name: str
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionError(Exception):
    """Base exception for action execution failures."""

    def __init__(self, message: str, action_name: str | None = None):
        super().__init__(message)
        self.action_name = action_name


class ActionNotFoundError(ActionError):
    """Raised when requesting an unregistered action."""

    pass





@dataclass
class ActionSpec:
    """Action registration metadata."""

    name: str
    description: str
    handler: Callable[..., Any]
    preview_handler: Callable[..., dict[str, Any]] | None = None
    resource_resolver: Callable[[Any, ActionContext], list[str]] | None = None
    input_model: type[BaseModel] | None = None
    output_model: type[BaseModel] | None = None
    requires_approval: bool = False
    classification: ActionClassification = "mutation"
    risk_level: ActionRisk = "R2"
    required_scopes: tuple[str, ...] = ("write",)
    version: int = 1
    lock_ttl_seconds: int = 15 * 60
    copilot_enabled: bool = False
    copilot_tool_name: str | None = None


# Global action registry storage
_REGISTRY: dict[str, ActionSpec] = {}


def register_action(
    name: str,
    description: str = "",
    preview_handler: Callable[..., dict[str, Any]] | None = None,
    resource_resolver: Callable[[Any, ActionContext], list[str]] | None = None,
    input_model: type[BaseModel] | None = None,
    output_model: type[BaseModel] | None = None,
    requires_approval: bool = False,
    classification: ActionClassification = "mutation",
    risk_level: ActionRisk = "R2",
    required_scopes: tuple[str, ...] = ("write",),
    version: int = 1,
    lock_ttl_seconds: int = 15 * 60,
    copilot_enabled: bool = False,
    copilot_tool_name: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a command/action handler."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        spec = ActionSpec(
            name=name,
            description=description or func.__doc__ or "",
            handler=func,
            preview_handler=preview_handler,
            resource_resolver=resource_resolver,
            input_model=input_model,
            output_model=output_model,
            requires_approval=requires_approval,
            classification=classification,
            risk_level=risk_level,
            required_scopes=tuple(required_scopes),
            version=max(1, int(version)),
            lock_ttl_seconds=max(5, min(int(lock_ttl_seconds), 60 * 60)),
            copilot_enabled=bool(copilot_enabled),
            copilot_tool_name=copilot_tool_name,
        )
        if name in _REGISTRY:
            logger.warning("Overwriting registered action '%s'", name)
        _REGISTRY[name] = spec
        return func

    return decorator


def get_action(name: str) -> ActionSpec:
    """Retrieve an action specification by name."""
    if name not in _REGISTRY:
        raise ActionNotFoundError(f"Action '{name}' is not registered.", action_name=name)
    return _REGISTRY[name]


def list_registered_specs() -> list[ActionSpec]:
    """Return a stable snapshot for trusted adapter generation."""
    return list(_REGISTRY.values())


def list_actions() -> list[dict[str, Any]]:
    """List details of all registered actions."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "requires_approval": spec.requires_approval,
            "has_preview": spec.preview_handler is not None,
            "uses_resource_locks": spec.resource_resolver is not None,
            "classification": spec.classification,
            "risk_level": spec.risk_level,
            "required_scopes": list(spec.required_scopes),
            "version": spec.version,
            "copilot_enabled": spec.copilot_enabled,
            "copilot_tool_name": spec.copilot_tool_name,
            "input_model": spec.input_model.__name__ if spec.input_model else None,
            "output_model": spec.output_model.__name__ if spec.output_model else None,
        }
        for spec in _REGISTRY.values()
    ]


def preview_action(
    name: str,
    input_data: Any = None,
    ctx: ActionContext | None = None,
) -> ActionResult:
    """Create a durable human-approval request without exposing an execution token."""
    start_time = time.perf_counter()
    ctx = ctx or ActionContext.create()
    try:
        spec = get_action(name)
    except ActionNotFoundError as exc:
        return ActionResult(success=False, error=str(exc), action_name=name)
    if not spec.requires_approval or not spec.preview_handler:
        return ActionResult(
            success=False,
            error=f"Action '{name}' does not provide an approval preview.",
            action_name=name,
        )
    missing_scopes = sorted(set(spec.required_scopes) - set(ctx.scopes))
    if missing_scopes:
        return ActionResult(
            success=False,
            error=f"Action '{name}' requires scopes: {', '.join(missing_scopes)}.",
            action_name=name,
        )
    try:
        parsed_input = (
            spec.input_model.model_validate(input_data or {})
            if spec.input_model and not isinstance(input_data, spec.input_model)
            else input_data
        )
        input_payload = (
            parsed_input.model_dump(mode="json", exclude_unset=True)
            if isinstance(parsed_input, BaseModel)
            else parsed_input
        )
        preview = spec.preview_handler(parsed_input, ctx)
        from app.actions.approvals import create_pending_approval

        pending = create_pending_approval(
            action_name=name,
            action_version=spec.version,
            input_payload=input_payload,
            preview=preview,
            ctx=ctx,
        )
        return ActionResult(
            success=True,
            data={"status": "approval_required", **pending},
            action_name=name,
            duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
            metadata={"risk_level": spec.risk_level, "version": spec.version},
        )
    except Exception as exc:
        return ActionResult(
            success=False,
            error=str(exc),
            action_name=name,
            duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
        )


def execute_action(
    name: str,
    input_data: Any = None,
    ctx: ActionContext | None = None,
) -> ActionResult:
    """Execute a registered action with validation, timing, and error handling."""
    start_time = time.perf_counter()
    ctx = ctx or ActionContext.create()

    if name not in _REGISTRY:
        duration = (time.perf_counter() - start_time) * 1000
        return ActionResult(
            success=False,
            error=f"Action '{name}' non-existent.",
            action_name=name,
            duration_ms=round(duration, 2),
        )

    spec = _REGISTRY[name]

    missing_scopes = sorted(set(spec.required_scopes) - set(ctx.scopes))
    if missing_scopes:
        duration = (time.perf_counter() - start_time) * 1000
        return ActionResult(
            success=False,
            error=f"Action '{name}' requires scopes: {', '.join(missing_scopes)}.",
            action_name=name,
            duration_ms=round(duration, 2),
            metadata={"risk_level": spec.risk_level, "version": spec.version},
        )

    # Input validation
    parsed_input = input_data
    if spec.input_model and not isinstance(input_data, spec.input_model):
        try:
            if isinstance(input_data, dict):
                parsed_input = spec.input_model(**input_data)
            elif input_data is None:
                parsed_input = spec.input_model()
            else:
                parsed_input = spec.input_model.model_validate(input_data)
        except Exception as err:
            duration = (time.perf_counter() - start_time) * 1000
            return ActionResult(
                success=False,
                error=f"Invalid input payload for '{name}': {err}",
                action_name=name,
                duration_ms=round(duration, 2),
            )

    input_payload = (
        parsed_input.model_dump(mode="json", exclude_unset=True)
        if isinstance(parsed_input, BaseModel)
        else parsed_input
    )
    resource_keys: list[str] = []
    lease_id: str | None = None

    def release_lease() -> None:
        if not lease_id:
            return
        try:
            from app.actions.locks import release_resource_locks

            release_resource_locks(lease_id)
        except Exception:
            logger.exception("Could not release action resource lease %s", lease_id)

    if spec.resource_resolver:
        try:
            resource_keys = list(spec.resource_resolver(parsed_input, ctx))
            from app.actions.locks import acquire_resource_locks

            lease_id = acquire_resource_locks(
                resource_keys,
                action_name=name,
                ctx=ctx,
                ttl_seconds=spec.lock_ttl_seconds,
            )
        except Exception as exc:
            from app.actions.locks import ResourceLockedError

            metadata = {
                "risk_level": spec.risk_level,
                "version": spec.version,
                "resource_keys": resource_keys,
            }
            if isinstance(exc, ResourceLockedError):
                metadata["lock_conflicts"] = [
                    {
                        "resource_key": item.resource_key,
                        "action_name": item.action_name,
                        "session_id": item.session_id,
                        "expires_at": item.expires_at.isoformat(),
                    }
                    for item in exc.conflicts
                ]
            return ActionResult(
                success=False,
                error=str(exc),
                action_name=name,
                duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
                metadata=metadata,
            )
    approval_id: int | None = None
    if spec.requires_approval:
        if not ctx.approval_token:
            release_lease()
            return ActionResult(
                success=False,
                error=f"Action '{name}' requires a trusted approval preview and token.",
                action_name=name,
                duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
                metadata={"risk_level": spec.risk_level, "version": spec.version},
            )
        try:
            from app.actions.approvals import consume_approval_token

            approval_id = consume_approval_token(
                ctx.approval_token,
                action_name=name,
                action_version=spec.version,
                input_payload=input_payload,
                ctx=ctx,
            )
        except Exception as exc:
            release_lease()
            return ActionResult(
                success=False,
                error=str(exc),
                action_name=name,
                duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
                metadata={"risk_level": spec.risk_level, "version": spec.version},
            )
    execution_id: int | None = None
    try:
        from sqlalchemy import select
        from app.actions.models import ActionExecution
        from app.infrastructure.db import SessionFactory

        with SessionFactory() as ledger_db:
            if ctx.idempotency_key:
                previous = ledger_db.scalar(
                    select(ActionExecution).where(
                        ActionExecution.idempotency_key == ctx.idempotency_key
                    )
                )
                if previous:
                    if previous.action_name != name:
                        release_lease()
                        return ActionResult(
                            success=False,
                            error="Idempotency key was already used for a different action.",
                            action_name=name,
                            duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
                            metadata={"execution_id": previous.id, "idempotent_replay": True},
                        )
                    output = json.loads(previous.output_json) if previous.output_json else None
                    release_lease()
                    return ActionResult(
                        success=previous.status == "completed",
                        data=output,
                        error=previous.error,
                        action_name=name,
                        duration_ms=float(previous.duration_ms or 0),
                        metadata={
                            "execution_id": previous.id,
                            "idempotent_replay": True,
                            "risk_level": previous.risk_level,
                            "version": previous.action_version,
                        },
                    )
            execution = ActionExecution(
                action_name=name,
                action_version=spec.version,
                classification=spec.classification,
                risk_level=spec.risk_level,
                actor_type=ctx.actor_type,
                session_id=ctx.session_id,
                request_id=ctx.request_id,
                idempotency_key=ctx.idempotency_key,
                status="running",
                input_json=json.dumps(input_payload, ensure_ascii=False, default=str),
            )
            ledger_db.add(execution)
            ledger_db.commit()
            ledger_db.refresh(execution)
            execution_id = execution.id
    except Exception as exc:
        logger.exception("Could not create action execution ledger row: %s", exc)
        release_lease()
        return ActionResult(
            success=False,
            error="The action could not be safely recorded, so it was not executed.",
            action_name=name,
            duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
        )

    # Handler execution
    try:
        import inspect
        import asyncio
        import concurrent.futures

        if inspect.iscoroutinefunction(spec.handler):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(1) as pool:
                    result = pool.submit(lambda: asyncio.run(spec.handler(parsed_input, ctx))).result()
            else:
                result = asyncio.run(spec.handler(parsed_input, ctx))
        else:
            result = spec.handler(parsed_input, ctx)
        
        # Optional output validation
        if spec.output_model and isinstance(result, dict):
            result = spec.output_model(**result)

        normalized_result = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
        duration = (time.perf_counter() - start_time) * 1000
        with SessionFactory() as ledger_db:
            execution = ledger_db.get(ActionExecution, execution_id)
            if execution:
                execution.status = "completed"
                execution.output_json = json.dumps(normalized_result, ensure_ascii=False, default=str)
                execution.duration_ms = round(duration, 2)
                execution.completed_at = datetime.now(timezone.utc)
                ledger_db.commit()
        release_lease()
        return ActionResult(
            success=True,
            data=normalized_result,
            action_name=name,
            duration_ms=round(duration, 2),
            metadata={
                "execution_id": execution_id,
                "risk_level": spec.risk_level,
                "version": spec.version,
                "approval_id": approval_id,
                "resource_keys": resource_keys,
            },
        )
    except Exception as exc:
        logger.exception("Error executing action '%s': %s", name, exc)
        duration = (time.perf_counter() - start_time) * 1000
        try:
            with SessionFactory() as ledger_db:
                execution = ledger_db.get(ActionExecution, execution_id)
                if execution:
                    execution.status = "failed"
                    execution.error = str(exc)
                    execution.duration_ms = round(duration, 2)
                    execution.completed_at = datetime.now(timezone.utc)
                    ledger_db.commit()
        except Exception:
            logger.exception("Could not finalize failed action execution %s", execution_id)
        release_lease()
        return ActionResult(
            success=False,
            error=str(exc),
            action_name=name,
            duration_ms=round(duration, 2),
            metadata={
                "execution_id": execution_id,
                "risk_level": spec.risk_level,
                "version": spec.version,
                "approval_id": approval_id,
                "resource_keys": resource_keys,
            },
        )
