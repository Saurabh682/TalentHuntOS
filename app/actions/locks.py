"""Durable affected-resource leases for serialized action execution."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.actions.context import ActionContext
from app.actions.models import ActionResourceLock
from app.infrastructure.db import SessionFactory


DEFAULT_LOCK_TTL_SECONDS = 15 * 60


@dataclass(frozen=True)
class ResourceLockConflict:
    resource_key: str
    action_name: str
    session_id: str | None
    expires_at: datetime


class ResourceLockedError(RuntimeError):
    def __init__(self, conflicts: list[ResourceLockConflict]):
        self.conflicts = conflicts
        resources = ", ".join(item.resource_key for item in conflicts)
        super().__init__(f"Resource busy: {resources}. Wait for the current action to finish or retry.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def normalize_resource_keys(resource_keys: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(key).strip().lower() for key in resource_keys if str(key).strip()}))


def acquire_resource_locks(
    resource_keys: Iterable[str],
    *,
    action_name: str,
    ctx: ActionContext,
    ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
) -> str | None:
    """Acquire all keys atomically from the caller's perspective or raise a conflict."""
    keys = normalize_resource_keys(resource_keys)
    if not keys:
        return None
    now = _now()
    expires_at = now + timedelta(seconds=max(5, min(int(ttl_seconds), 60 * 60)))
    lease_id = uuid.uuid4().hex

    with SessionFactory() as db:
        db.execute(
            update(ActionResourceLock)
            .where(
                ActionResourceLock.status == "active",
                ActionResourceLock.expires_at <= now,
            )
            .values(status="expired", released_at=now)
        )
        db.commit()

        existing = list(db.scalars(
            select(ActionResourceLock).where(
                ActionResourceLock.status == "active",
                ActionResourceLock.resource_key.in_(keys),
            )
        ).all())
        if existing:
            raise ResourceLockedError([
                ResourceLockConflict(
                    resource_key=row.resource_key,
                    action_name=row.action_name,
                    session_id=row.session_id,
                    expires_at=_aware(row.expires_at),
                )
                for row in existing
            ])

        db.add_all([
            ActionResourceLock(
                lease_id=lease_id,
                resource_key=key,
                action_name=action_name,
                request_id=ctx.request_id,
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                status="active",
                acquired_at=now,
                expires_at=expires_at,
            )
            for key in keys
        ])
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            conflicts = list(db.scalars(
                select(ActionResourceLock).where(
                    ActionResourceLock.status == "active",
                    ActionResourceLock.resource_key.in_(keys),
                )
            ).all())
            raise ResourceLockedError([
                ResourceLockConflict(
                    resource_key=row.resource_key,
                    action_name=row.action_name,
                    session_id=row.session_id,
                    expires_at=_aware(row.expires_at),
                )
                for row in conflicts
            ]) from None
    return lease_id


def release_resource_locks(lease_id: str | None, *, status: str = "released") -> None:
    if not lease_id:
        return
    now = _now()
    with SessionFactory() as db:
        db.execute(
            update(ActionResourceLock)
            .where(
                ActionResourceLock.lease_id == lease_id,
                ActionResourceLock.status == "active",
            )
            .values(status=status, released_at=now)
        )
        db.commit()


def list_active_resource_locks() -> list[dict[str, object]]:
    now = _now()
    with SessionFactory() as db:
        rows = list(db.scalars(
            select(ActionResourceLock)
            .where(
                ActionResourceLock.status == "active",
                ActionResourceLock.expires_at > now,
            )
            .order_by(ActionResourceLock.resource_key)
        ).all())
        return [
            {
                "lease_id": row.lease_id,
                "resource_key": row.resource_key,
                "action_name": row.action_name,
                "session_id": row.session_id,
                "expires_at": row.expires_at.isoformat(),
            }
            for row in rows
        ]
