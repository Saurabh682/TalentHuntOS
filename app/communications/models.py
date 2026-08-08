"""SQLAlchemy 2.0 ORM models for Communications Hub, Email Accounts, Templates, Outreach Sequences, and Embedded Browser Sessions."""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db import Base
from app.candidates.models import Candidate


class CommunicationThread(Base):
    """Communication thread organizing multi-turn messages with candidates across channels."""
    __tablename__ = "communication_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True
    )
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    channel: Mapped[str] = mapped_column(String(50), default="email", nullable=False)  # email, linkedin, naukri, whatsapp, phone
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)  # active, closed, archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    candidate: Mapped[Optional["Candidate"]] = relationship("Candidate", foreign_keys=[candidate_id])
    communications: Mapped[List["Communication"]] = relationship(
        "Communication", back_populates="thread", cascade="all, delete-orphan", order_by="Communication.created_at.asc()"
    )

    def __repr__(self) -> str:
        return f"<CommunicationThread(id={self.id}, channel='{self.channel}', subject='{self.subject}')>"


class Communication(Base):
    """Individual communication message log entry (Email, LinkedIn message, InMail, WhatsApp, Voice call log)."""
    __tablename__ = "communications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("communication_threads.id", ondelete="CASCADE"), nullable=True
    )
    candidate_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(50), default="email", nullable=False)  # email, linkedin, naukri, whatsapp, phone, voice_ai
    direction: Mapped[str] = mapped_column(String(20), default="outbound", nullable=False)  # outbound, inbound
    sender: Mapped[str] = mapped_column(String(120), nullable=False)
    recipient: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="sent", nullable=False)  # draft, sent, received, failed, pending
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    thread: Mapped[Optional["CommunicationThread"]] = relationship("CommunicationThread", back_populates="communications")
    candidate: Mapped[Optional["Candidate"]] = relationship("Candidate", foreign_keys=[candidate_id])

    def __repr__(self) -> str:
        return f"<Communication(id={self.id}, channel='{self.channel}', direction='{self.direction}', recipient='{self.recipient}')>"


class MessageTemplate(Base):
    """Reusable message template for email/LinkedIn outreach with merge tags."""
    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), default="email", nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(50), default="Outreach", nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    variables_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of variable names
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    outreach_steps: Mapped[List["OutreachStep"]] = relationship("OutreachStep", back_populates="template")

    def __repr__(self) -> str:
        return f"<MessageTemplate(id={self.id}, name='{self.name}', channel='{self.channel}')>"


class OutreachSequence(Base):
    """Sequenced multi-step drip campaign for candidate outreach."""
    __tablename__ = "outreach_sequences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(50), default="email", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    steps: Mapped[List["OutreachStep"]] = relationship(
        "OutreachStep", back_populates="sequence", cascade="all, delete-orphan", order_by="OutreachStep.step_number"
    )
    enrollments: Mapped[List["OutreachEnrollment"]] = relationship(
        "OutreachEnrollment", back_populates="sequence", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<OutreachSequence(id={self.id}, name='{self.name}', channel='{self.channel}')>"


class OutreachStep(Base):
    """Step in an outreach sequence campaign (e.g. Day 1 initial email, Day 3 LinkedIn follow-up)."""
    __tablename__ = "outreach_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sequence_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("outreach_sequences.id", ondelete="CASCADE"), nullable=False
    )
    step_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    delay_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("message_templates.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(50), default="email", nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body_override: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    sequence: Mapped["OutreachSequence"] = relationship("OutreachSequence", back_populates="steps")
    template: Mapped[Optional["MessageTemplate"]] = relationship("MessageTemplate", back_populates="outreach_steps")

    def __repr__(self) -> str:
        return f"<OutreachStep(id={self.id}, sequence_id={self.sequence_id}, step={self.step_number}, delay={self.delay_days}d)>"


class OutreachEnrollment(Base):
    """Candidate enrollment in an outreach sequence tracking progression."""
    __tablename__ = "outreach_enrollments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sequence_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("outreach_sequences.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    current_step_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)  # active, paused, completed, replied, bounced
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_step_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_step_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    sequence: Mapped["OutreachSequence"] = relationship("OutreachSequence", back_populates="enrollments")
    candidate: Mapped["Candidate"] = relationship("Candidate", foreign_keys=[candidate_id])

    def __repr__(self) -> str:
        return f"<OutreachEnrollment(id={self.id}, sequence_id={self.sequence_id}, candidate_id={self.candidate_id}, step={self.current_step_number})>"


class EmailAccount(Base):
    """SMTP/IMAP account settings for recruiter outbound sending and inbox syncing."""
    __tablename__ = "email_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_address: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    smtp_host: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    smtp_username: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    smtp_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    imap_host: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    imap_port: Mapped[int] = mapped_column(Integer, default=993, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return f"<EmailAccount(id={self.id}, email='{self.email_address}', default={self.is_default})>"


class BrowserSession(Base):
    """Saved embedded browser sessions, active cookies/tokens, and target platforms."""
    __tablename__ = "browser_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # linkedin, naukri, github, indeed
    session_name: Mapped[str] = mapped_column(String(100), nullable=False)
    target_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cookies_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    headers_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<BrowserSession(id={self.id}, platform='{self.platform}', name='{self.session_name}')>"
