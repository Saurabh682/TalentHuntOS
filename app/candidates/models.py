"""SQLAlchemy 2.0 ORM models for Candidate Database, Profile, Tags, Experience, Education, and Notes."""

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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db import Base


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
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
