"""Central Action Registry and Command Dispatcher for TalentHunt OS."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from app.actions.context import ActionContext

logger = logging.getLogger("talenthunt.actions")

ActionClassification = Literal["query", "mutation", "ai_task", "system"]


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
    input_model: type[BaseModel] | None = None
    output_model: type[BaseModel] | None = None
    requires_approval: bool = False
    classification: ActionClassification = "mutation"


# Global action registry storage
_REGISTRY: dict[str, ActionSpec] = {}


def register_action(
    name: str,
    description: str = "",
    input_model: type[BaseModel] | None = None,
    output_model: type[BaseModel] | None = None,
    requires_approval: bool = False,
    classification: ActionClassification = "mutation",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a command/action handler."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        spec = ActionSpec(
            name=name,
            description=description or func.__doc__ or "",
            handler=func,
            input_model=input_model,
            output_model=output_model,
            requires_approval=requires_approval,
            classification=classification,
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


def list_actions() -> list[dict[str, Any]]:
    """List details of all registered actions."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "requires_approval": spec.requires_approval,
            "classification": spec.classification,
            "input_model": spec.input_model.__name__ if spec.input_model else None,
            "output_model": spec.output_model.__name__ if spec.output_model else None,
        }
        for spec in _REGISTRY.values()
    ]


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

    # Approval check
    if spec.requires_approval and not ctx.approval_token:
        duration = (time.perf_counter() - start_time) * 1000
        return ActionResult(
            success=False,
            error=f"Action '{name}' requires human approval token.",
            action_name=name,
            duration_ms=round(duration, 2),
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

        duration = (time.perf_counter() - start_time) * 1000
        return ActionResult(
            success=True,
            data=result.model_dump() if isinstance(result, BaseModel) else result,
            action_name=name,
            duration_ms=round(duration, 2),
        )
    except Exception as exc:
        logger.exception("Error executing action '%s': %s", name, exc)
        duration = (time.perf_counter() - start_time) * 1000
        return ActionResult(
            success=False,
            error=str(exc),
            action_name=name,
            duration_ms=round(duration, 2),
        )
