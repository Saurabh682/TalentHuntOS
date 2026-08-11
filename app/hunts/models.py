"""SQLAlchemy 2.0 ORM models for Talent Hunt Campaigns and Pipeline."""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db import Base
from app.candidates.models import Candidate


class TalentHunt(Base):
    """Talent Hunt Campaign model."""
    __tablename__ = "talent_hunts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="Active", nullable=False)  # Active, Draft, Paused, Completed, Archived
    target_role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    salary_range: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    search_config: Mapped[Optional["HuntSearchConfig"]] = relationship(
        "HuntSearchConfig", back_populates="hunt", cascade="all, delete-orphan", uselist=False
    )
    stages: Mapped[List["HuntStage"]] = relationship(
        "HuntStage", back_populates="hunt", cascade="all, delete-orphan", order_by="HuntStage.position"
    )
    candidates: Mapped[List["HuntCandidate"]] = relationship(
        "HuntCandidate", back_populates="hunt", cascade="all, delete-orphan"
    )
    activities: Mapped[List["HuntActivity"]] = relationship(
        "HuntActivity", back_populates="hunt", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TalentHunt(id={self.id}, title='{self.title}', status='{self.status}')>"


class HuntSearchConfig(Base):
    """Search & Sourcing Configuration for a Talent Hunt."""
    __tablename__ = "hunt_search_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hunt_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("talent_hunts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    required_skills: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preferred_skills: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    experience_years_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    experience_years_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    locations: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    remote_policy: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_platforms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    hunt: Mapped["TalentHunt"] = relationship("TalentHunt", back_populates="search_config")

    def __repr__(self) -> str:
        return f"<HuntSearchConfig(id={self.id}, hunt_id={self.hunt_id})>"


class HuntStage(Base):
    """Stage definition in a Talent Hunt pipeline."""
    __tablename__ = "hunt_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hunt_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("talent_hunts.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    hunt: Mapped["TalentHunt"] = relationship("TalentHunt", back_populates="stages")
    candidates: Mapped[List["HuntCandidate"]] = relationship("HuntCandidate", back_populates="stage")

    def __repr__(self) -> str:
        return f"<HuntStage(id={self.id}, hunt_id={self.hunt_id}, name='{self.name}', pos={self.position})>"


class HuntCandidate(Base):
    """Candidate linked to a specific Talent Hunt pipeline."""
    __tablename__ = "hunt_candidates"
    __table_args__ = (UniqueConstraint("hunt_id", "candidate_id", name="uq_hunt_candidate"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hunt_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("talent_hunts.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True
    )
    candidate: Mapped[Optional["Candidate"]] = relationship("Candidate")
    stage_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("hunt_stages.id", ondelete="SET NULL"), nullable=True
    )
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    current_title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    current_company: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    github_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    portfolio_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="Active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    hunt: Mapped["TalentHunt"] = relationship("TalentHunt", back_populates="candidates")
    stage: Mapped[Optional["HuntStage"]] = relationship("HuntStage", back_populates="candidates")
    activities: Mapped[List["HuntActivity"]] = relationship(
        "HuntActivity", back_populates="candidate", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<HuntCandidate(id={self.id}, name='{self.full_name}', match_score={self.match_score})>"


class HuntActivity(Base):
    """Audit log / activity record for events in a Talent Hunt."""
    __tablename__ = "hunt_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hunt_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("talent_hunts.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("hunt_candidates.id", ondelete="CASCADE"), nullable=True
    )
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    hunt: Mapped["TalentHunt"] = relationship("TalentHunt", back_populates="activities")
    candidate: Mapped[Optional["HuntCandidate"]] = relationship("HuntCandidate", back_populates="activities")

    def __repr__(self) -> str:
        return f"<HuntActivity(id={self.id}, type='{self.activity_type}', hunt_id={self.hunt_id})>"


class PlaybookEntry(Base):
    """Global shared sourcing playbook: Keep/Pass triage and worked/didn't insights."""
    __tablename__ = "playbook_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)  # keep | pass | insight
    insight_outcome: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # worked | didnt_work
    role_context: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    query_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    candidate_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    candidate_title: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    candidate_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hunt_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hunt_title: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author_name: Mapped[str] = mapped_column(String(80), default="Recruiter", nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return f"<PlaybookEntry(id={self.id}, type='{self.entry_type}', role='{self.role_context}')>"
