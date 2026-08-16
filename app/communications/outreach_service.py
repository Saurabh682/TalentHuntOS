"""Outreach Sequence & Automated Drip Campaign Execution Engine."""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.communications.models import (
    OutreachEnrollment,
    OutreachSequence,
    OutreachStep,
)


def create_sequence(
    db: Session,
    name: str,
    description: Optional[str] = None,
    channel: str = "email",
) -> OutreachSequence:
    """Create a new drip outreach sequence campaign."""
    seq = OutreachSequence(
        name=name,
        description=description,
        channel=channel,
        is_active=True,
    )
    db.add(seq)
    db.commit()
    db.refresh(seq)
    return seq


def add_step_to_sequence(
    db: Session,
    sequence_id: int,
    step_number: int,
    delay_days: int,
    template_id: Optional[int] = None,
    subject: Optional[str] = None,
    body_override: Optional[str] = None,
    channel: str = "email",
) -> OutreachStep:
    """Add a step to an outreach sequence."""
    step = OutreachStep(
        sequence_id=sequence_id,
        step_number=step_number,
        delay_days=delay_days,
        template_id=template_id,
        subject=subject,
        body_override=body_override,
        channel=channel,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


def enroll_candidate(db: Session, sequence_id: int, candidate_id: int) -> OutreachEnrollment:
    """Enroll a candidate into an outreach drip campaign sequence."""
    # Check if already enrolled in this sequence
    existing = db.scalar(
        select(OutreachEnrollment).where(
            OutreachEnrollment.sequence_id == sequence_id,
            OutreachEnrollment.candidate_id == candidate_id,
            OutreachEnrollment.status == "active",
        )
    )
    if existing:
        return existing

    enrollment = OutreachEnrollment(
        sequence_id=sequence_id,
        candidate_id=candidate_id,
        current_step_number=1,
        status="active",
        enrolled_at=datetime.now(timezone.utc),
        next_step_due_at=datetime.now(timezone.utc),  # Immediate start for step 1
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment


def list_sequences(db: Session) -> List[OutreachSequence]:
    """List all outreach sequence campaigns."""
    stmt = (
        select(OutreachSequence)
        .options(joinedload(OutreachSequence.steps), joinedload(OutreachSequence.enrollments))
        .order_by(OutreachSequence.created_at.desc())
    )
    return list(db.scalars(stmt).unique().all())


def get_sequence_details(db: Session, sequence_id: int) -> Optional[OutreachSequence]:
    """Get sequence by ID with loaded steps and active enrollments."""
    stmt = (
        select(OutreachSequence)
        .options(joinedload(OutreachSequence.steps), joinedload(OutreachSequence.enrollments))
        .where(OutreachSequence.id == sequence_id)
    )
    return db.scalars(stmt).unique().first()


def pause_enrollment(db: Session, enrollment_id: int) -> Optional[OutreachEnrollment]:
    """Pause an active candidate drip enrollment."""
    enr = db.get(OutreachEnrollment, enrollment_id)
    if enr:
        enr.status = "paused"
        db.commit()
        db.refresh(enr)
    return enr


def resume_enrollment(db: Session, enrollment_id: int) -> Optional[OutreachEnrollment]:
    """Resume a paused candidate drip enrollment."""
    enr = db.get(OutreachEnrollment, enrollment_id)
    if enr:
        enr.status = "active"
        enr.next_step_due_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(enr)
    return enr


def process_due_outreach_steps(db: Session) -> list[dict[str, object]]:
    """Reject the legacy unapproved send path.

    Call ``communications.deliveries.due.list`` and then request an individual
    ``communications.delivery.send`` approval instead.
    """
    raise PermissionError(
        "Direct drip processing is disabled. Use the R4 approved delivery action."
    )


def seed_default_sequence_if_empty(db: Session) -> None:
    """Seed a sample 3-step recruiting sequence if none exists."""
    existing = db.scalar(select(OutreachSequence.id).limit(1))
    if existing:
        return

    seq = create_sequence(
        db,
        name="Senior Software Engineer 3-Step Campaign",
        description="Standard 3-step automated outreach for passive engineering candidates.",
        channel="email",
    )

    add_step_to_sequence(
        db,
        sequence_id=seq.id,
        step_number=1,
        delay_days=0,
        subject="Opportunity: {{job_title}} at {{company}}",
        body_override="Hi {{candidate_name}},\n\nI was impressed by your expertise in {{skills}}. We have a Lead {{job_title}} position at {{company}} that matches your profile.\n\nWould you be open to a 10-min chat?\n\nBest,\n{{recruiter_name}}",
        channel="email",
    )

    add_step_to_sequence(
        db,
        sequence_id=seq.id,
        step_number=2,
        delay_days=3,
        subject="Re: Opportunity: {{job_title}} at {{company}}",
        body_override="Hi {{candidate_name}},\n\nFollowing up on my previous note. Wanted to see if you had a moment to review the {{job_title}} details.\n\nBest,\n{{recruiter_name}}",
        channel="email",
    )

    add_step_to_sequence(
        db,
        sequence_id=seq.id,
        step_number=3,
        delay_days=5,
        subject="Final check - {{job_title}} role",
        body_override="Hi {{candidate_name}},\n\nClosing the loop on this for now. If timing isn't right, no worries at all! Feel free to connect whenever you're open to new roles.\n\nBest,\n{{recruiter_name}}",
        channel="email",
    )
