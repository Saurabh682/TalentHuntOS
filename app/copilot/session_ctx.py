"""Per-request Copilot session context (active hunt binding for tools)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_active_hunt_id: ContextVar[Optional[int]] = ContextVar("copilot_active_hunt_id", default=None)
_active_session_id: ContextVar[Optional[str]] = ContextVar("copilot_active_session_id", default=None)


def set_active_hunt_id(hunt_id: Optional[int]) -> None:
    _active_hunt_id.set(hunt_id)


def get_active_hunt_id() -> Optional[int]:
    return _active_hunt_id.get()


def set_active_session_id(session_id: Optional[str]) -> None:
    _active_session_id.set(session_id)


def get_active_session_id() -> Optional[str]:
    return _active_session_id.get()


def resolve_hunt_id_from_session(session_id: Optional[str] = None) -> Optional[int]:
    sid = session_id or get_active_session_id() or ""
    if sid.startswith("hunt_"):
        part = sid.split("_", 1)[1]
        if part.isdigit():
            return int(part)
    return get_active_hunt_id()
