"""Action context containing security, identity, and execution metadata."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

ActorType = Literal["ui", "agent", "cli", "mcp", "scheduler", "system"]


@dataclass
class ActionContext:
    """Trusted context created by calling adapters to enforce identity and permissions."""

    user_id: int | None = None
    actor_type: ActorType = "ui"
    session_id: str | None = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    idempotency_key: str | None = None
    scopes: list[str] = field(default_factory=lambda: ["read", "write", "compute", "draft"])
    approval_token: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)
    identity_verified: bool = False
    undo_action: str | None = None
    undo_input: dict[str, Any] = field(default_factory=dict, repr=False)

    def set_undo(self, action_name: str, input_data: dict[str, Any]) -> None:
        """Attach a safe inverse action for rollback or audit purposes."""
        self.undo_action = action_name
        self.undo_input = dict(input_data)

    @classmethod
    def create(
        cls,
        actor_type: ActorType = "ui",
        user_id: int | None = None,
        session_id: str | None = None,
        scopes: list[str] | None = None,
        approval_token: str | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ActionContext:
        """Construct a standard ActionContext instance."""
        return cls(
            user_id=user_id,
            actor_type=actor_type,
            session_id=session_id or (f"{actor_type}:{user_id}" if user_id else None),
            scopes=scopes if scopes is not None else ["read", "write", "compute", "draft"],
            approval_token=approval_token,
            idempotency_key=idempotency_key,
            metadata=metadata or {},
            identity_verified=user_id is not None or actor_type in {"system", "scheduler"},
        )
