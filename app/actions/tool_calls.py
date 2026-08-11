"""Structured, redacted audit records for Copilot tool invocations."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.actions.models import ActionToolCall
from app.infrastructure.db import SessionFactory


MAX_TOOL_OUTPUT_CHARS = 20_000
_SECRET_PARTS = ("password", "secret", "token", "api_key", "apikey", "cookie", "authorization")


def _redact(value: Any, key: str = "") -> Any:
    if any(part in key.lower() for part in _SECRET_PARTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _json(value: Any, *, limit: int | None = None) -> str:
    text = json.dumps(_redact(value), ensure_ascii=False, default=str)
    if limit and len(text) > limit:
        return text[:limit] + "...[truncated]"
    return text


def begin_tool_call(
    *,
    tool_name: str,
    action_name: str | None,
    session_id: str | None,
    input_payload: dict[str, Any],
) -> tuple[int, float]:
    started = time.perf_counter()
    with SessionFactory() as db:
        row = ActionToolCall(
            tool_call_id=uuid.uuid4().hex,
            tool_name=tool_name,
            action_name=action_name,
            actor_type="agent",
            session_id=session_id,
            status="running",
            input_json=_json(input_payload),
            started_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id, started


def interpret_tool_output(output: Any) -> tuple[str, int | None, str | None]:
    parsed = output
    if isinstance(output, str):
        try:
            parsed = json.loads(output)
        except (TypeError, ValueError):
            parsed = None
    if not isinstance(parsed, dict):
        return "completed", None, None
    execution = parsed.get("execution") or {}
    execution_id = execution.get("execution_id") if isinstance(execution, dict) else None
    status_value = str(parsed.get("status") or "").lower()
    error = parsed.get("error")
    if not error and status_value in {"error", "failed"}:
        error = parsed.get("message")
    status = "failed" if error or status_value in {"error", "failed"} else "completed"
    return status, int(execution_id) if execution_id else None, str(error) if error else None


def finish_tool_call(
    row_id: int,
    started: float,
    *,
    output: Any = None,
    error: str | None = None,
) -> None:
    status, execution_id, output_error = interpret_tool_output(output)
    if error:
        status, output_error = "failed", error
    with SessionFactory() as db:
        row = db.get(ActionToolCall, int(row_id))
        if not row:
            return
        row.status = status
        row.action_execution_id = execution_id
        row.output_json = _json(output, limit=MAX_TOOL_OUTPUT_CHARS) if output is not None else None
        row.error = output_error
        row.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        row.completed_at = datetime.now(timezone.utc)
        db.commit()
