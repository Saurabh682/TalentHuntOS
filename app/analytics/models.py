"""Durable metadata for locally generated report artifacts."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReportArtifact(Base):
    """Metadata for one report file stored under TalentHunt's private data directory."""

    __tablename__ = "report_artifacts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    report_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    format: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    hunt_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    hunt_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    provenance_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )
