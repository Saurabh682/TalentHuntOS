"""Generate and audit LangChain tools from the authoritative action registry."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import StructuredTool

from app.copilot.session_ctx import get_active_session_id

logger = logging.getLogger("talenthunt.copilot.action_adapters")


def _action_response(result) -> str:
    return json.dumps(
        {
            "status": "success" if result.success else "error",
            "action": result.action_name,
            "data": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
            "execution": result.metadata,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _build_action_tool(spec) -> StructuredTool:
    tool_name = spec.copilot_tool_name or spec.name.replace(".", "_")

    def invoke_action(**payload: Any) -> str:
        from app.actions.api import dispatch_action, dispatch_preview

        session_id = get_active_session_id() or "default"
        if spec.requires_approval:
            result = dispatch_preview(
                spec.name,
                payload,
                actor_type="agent",
                session_id=session_id,
            )
        else:
            result = dispatch_action(
                spec.name,
                payload,
                actor_type="agent",
                session_id=session_id,
            )
        return _action_response(result)

    description = spec.description
    if spec.requires_approval:
        description += " Creates a trusted UI approval preview; it never executes directly."
    return StructuredTool.from_function(
        func=invoke_action,
        name=tool_name,
        description=description,
        args_schema=spec.input_model,
        infer_schema=spec.input_model is None,
        metadata={"generated_action": True, "action_name": spec.name},
    )


def get_generated_action_tools() -> list[StructuredTool]:
    """Build the current Copilot action surface directly from registered specs."""
    from app.actions.api import ensure_core_actions_registered
    from app.actions.registry import list_registered_specs

    ensure_core_actions_registered()
    specs = [spec for spec in list_registered_specs() if spec.copilot_enabled]
    return [_build_action_tool(spec) for spec in sorted(specs, key=lambda item: item.name)]


def wrap_tool_for_audit(base_tool) -> StructuredTool:
    """Wrap any LangChain tool with a durable structured tool-call record."""
    metadata = dict(getattr(base_tool, "metadata", None) or {})
    action_name = metadata.get("action_name")

    def invoke_recorded(**payload: Any):
        from app.actions.tool_calls import begin_tool_call, finish_tool_call

        session_id = get_active_session_id() or "default"
        row_id, started = begin_tool_call(
            tool_name=base_tool.name,
            action_name=action_name,
            session_id=session_id,
            input_payload=payload,
        )
        try:
            output = base_tool.invoke(payload)
        except Exception as exc:
            try:
                finish_tool_call(row_id, started, error=str(exc))
            except Exception:
                logger.exception("Could not finalize failed tool call %s", row_id)
            raise
        try:
            finish_tool_call(row_id, started, output=output)
        except Exception:
            logger.exception("Could not finalize tool call %s", row_id)
        return output

    return StructuredTool.from_function(
        func=invoke_recorded,
        name=base_tool.name,
        description=base_tool.description,
        args_schema=getattr(base_tool, "args_schema", None),
        infer_schema=getattr(base_tool, "args_schema", None) is None,
        return_direct=bool(getattr(base_tool, "return_direct", False)),
        metadata={**metadata, "audited_tool": True},
    )
