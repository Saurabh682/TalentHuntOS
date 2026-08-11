"""SQLAlchemy 2.0 ORM models for Candidate Database, Profile, Tags, Experience, Education, and Notes."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional
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

if TYPE_CHECKING:
    from app.hunts.models import TalentHunt


class Candidate(Base):
    """Global Candidate database record."""
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(120), unique=True, index=True, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    current_title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    current_company: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pronouns: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    connection_degree: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    connections_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    profile_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    experience_years: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    github_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    portfolio_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="Active", nullable=False)  # Active, Passive, Placed, Archived, Blacklisted
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    profile: Mapped[Optional["CandidateProfile"]] = relationship(
        "CandidateProfile", back_populates="candidate", cascade="all, delete-orphan", uselist=False
    )
    tags: Mapped[List["CandidateTag"]] = relationship(
        "CandidateTag", back_populates="candidate", cascade="all, delete-orphan"
    )
    experiences: Mapped[List["CandidateExperience"]] = relationship(
        "CandidateExperience", back_populates="candidate", cascade="all, delete-orphan", order_by="CandidateExperience.start_date.desc()"
    )
    educations: Mapped[List["CandidateEducation"]] = relationship(
        "CandidateEducation", back_populates="candidate", cascade="all, delete-orphan", order_by="CandidateEducation.end_year.desc()"
    )
    notes: Mapped[List["CandidateNote"]] = relationship(
        "CandidateNote", back_populates="candidate", cascade="all, delete-orphan", order_by="CandidateNote.created_at.desc()"
    )
    snapshots: Mapped[List["CandidateProfileSnapshot"]] = relationship(
        "CandidateProfileSnapshot",
        cascade="all, delete-orphan",
        order_by="CandidateProfileSnapshot.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<Candidate(id={self.id}, name='{self.full_name}', title='{self.current_title}')>"


class CandidateProfile(Base):
    """Detailed extended profile and resume text for Candidate."""
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidates.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    headline: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resume_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    skills_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string array e.g. ["Python", "PyTorch"]
    languages_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    highlights_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_evaluation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chroma_doc_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationship
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="profile")

    def __repr__(self) -> str:
        return f"<CandidateProfile(id={self.id}, candidate_id={self.candidate_id})>"


class DiscoveredProfile(Base):
    """Permanent common-pool identity found during lightweight sourcing."""
    __tablename__ = "discovered_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    normalized_url: Mapped[str] = mapped_column(String(500), unique=True, index=True, nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(120), index=True, nullable=True)
    headline: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    current_company: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    experience_years: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="raw", index=True, nullable=False)
    candidate_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True, nullable=False
    )
    seen_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    deep_scanned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    candidate: Mapped[Optional["Candidate"]] = relationship("Candidate")
    hunt_matches: Mapped[List["DiscoveryHuntMatch"]] = relationship(
        "DiscoveryHuntMatch", back_populates="profile", cascade="all, delete-orphan"
    )


class DiscoveryHuntMatch(Base):
    """Independent qualification and approval state for one discovery in one hunt."""
    __tablename__ = "discovery_hunt_matches"
    __table_args__ = (
        UniqueConstraint("discovered_profile_id", "hunt_id", name="uq_discovery_hunt_match"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discovered_profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("discovered_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hunt_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("talent_hunts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="raw", index=True, nullable=False)
    source_platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    scan_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True, nullable=False
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped["DiscoveredProfile"] = relationship("DiscoveredProfile", back_populates="hunt_matches")
    hunt: Mapped["TalentHunt"] = relationship("TalentHunt")


class CandidateTag(Base):
    """Tags assigned to candidates."""
    __tablename__ = "candidate_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    tag_name: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(30), default="#00d4aa", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationship
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="tags")

    def __repr__(self) -> str:
        return f"<CandidateTag(id={self.id}, tag='{self.tag_name}', candidate_id={self.candidate_id})>"


class CandidateExperience(Base):
    """Candidate work experience entry."""
    __tablename__ = "candidate_experiences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    company: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    start_date: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    employment_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    skills_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationship
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="experiences")

    def __repr__(self) -> str:
        return f"<CandidateExperience(id={self.id}, company='{self.company}', title='{self.title}')>"


class CandidateEducation(Base):
    """Candidate education record."""
    __tablename__ = "candidate_educations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    institution: Mapped[str] = mapped_column(String(120), nullable=False)
    degree: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    field_of_study: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    start_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    grade: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    activities: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationship
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="educations")

    def __repr__(self) -> str:
        return f"<CandidateEducation(id={self.id}, institution='{self.institution}', degree='{self.degree}')>"


class CandidateNote(Base):
    """Recruiter note or interaction entry."""
    __tablename__ = "candidate_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    author: Mapped[str] = mapped_column(String(100), default="Recruiter", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationship
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="notes")

    def __repr__(self) -> str:
        return f"<CandidateNote(id={self.id}, candidate_id={self.candidate_id}, author='{self.author}')>"


class CandidateProfileSnapshot(Base):
    """Saved Playwright profile page snapshot (local PNG + text + HTML)."""
    __tablename__ = "candidate_profile_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    snapshot_dir: Mapped[str] = mapped_column(String(500), nullable=False)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    text_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    html_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CandidateProfileSnapshot(id={self.id}, candidate_id={self.candidate_id})>"


class CandidateIntakeRequest(Base):
    """Tokenized candidate-facing intake form request (JD questionnaire)."""
    __tablename__ = "candidate_intake_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    candidate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hunt_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(30), default="draft", nullable=False
    )  # draft, sent, submitted, accepted, rejected, expired
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    submissions: Mapped[List["CandidateIntakeSubmission"]] = relationship(
        "CandidateIntakeSubmission",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="CandidateIntakeSubmission.submitted_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<CandidateIntakeRequest(id={self.id}, token='{self.token[:8]}…', status='{self.status}')>"


class CandidateIntakeSubmission(Base):
    """Submitted payload from a candidate intake form (pending recruiter review)."""
    __tablename__ = "candidate_intake_submissions"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_candidate_intake_submission_request"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidate_intake_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )  # pending, accepted, rejected

    request: Mapped["CandidateIntakeRequest"] = relationship(
        "CandidateIntakeRequest", back_populates="submissions"
    )

    def __repr__(self) -> str:
        return f"<CandidateIntakeSubmission(id={self.id}, request_id={self.request_id}, review='{self.review_status}')>"
