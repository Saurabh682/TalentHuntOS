"""Database models for restart-safe background work."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BackgroundJob(Base):
    """Durable lifecycle record for asynchronous OS work."""

    __tablename__ = "background_jobs"
    __table_args__ = (
        Index(
            "uq_background_jobs_active_sourcing",
            "kind",
            unique=True,
            sqlite_where=text("kind = 'sourcing' AND status = 'running'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="running", index=True, nullable=False
    )
    hunt_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    hunt_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="Starting...", nullable=False)
    scanned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    progress_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parent_job_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

