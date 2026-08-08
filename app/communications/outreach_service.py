"""Outreach Sequence & Automated Drip Campaign Execution Engine."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.communications.models import (
    OutreachSequence,
    OutreachStep,
    OutreachEnrollment,
    MessageTemplate,
)
from app.candidates.models import Candidate
from app.communications.service import log_communication
from app.communications.email_service import send_email
from app.communications.template_engine import generate_candidate_outreach, render_template


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


def process_due_outreach_steps(db: Session) -> List[Dict[str, Any]]:
    """Process all active candidate enrollments whose next step is due.
    
    Renders message templates, logs communication records, sends mock email,
    and updates enrollment progress to the next step.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(OutreachEnrollment)
        .where(
            OutreachEnrollment.status == "active",
            OutreachEnrollment.next_step_due_at <= now,
        )
    )
    due_enrollments = list(db.scalars(stmt).all())
    processed_results = []

    for enr in due_enrollments:
        candidate = db.get(Candidate, enr.candidate_id)
        if not candidate:
            enr.status = "error"
            db.commit()
            continue

        # Find current step
        step_stmt = select(OutreachStep).where(
            OutreachStep.sequence_id == enr.sequence_id,
            OutreachStep.step_number == enr.current_step_number,
        )
        step = db.scalar(step_stmt)

        if not step:
            # Sequence finished
            enr.status = "completed"
            db.commit()
            processed_results.append({
                "enrollment_id": enr.id,
                "candidate_id": candidate.id,
                "candidate_name": getattr(candidate, "full_name", "Unknown"),
                "status": "completed",
                "message": "All steps executed successfully.",
            })
            continue

        # Resolve subject and body
        subject = step.subject or f"Outreach Step {step.step_number}"
        body_template = step.body_override

        if not body_template and step.template_id:
            tmpl = db.get(MessageTemplate, step.template_id)
            if tmpl:
                body_template = tmpl.body_template
                if tmpl.subject and not step.subject:
                    subject = tmpl.subject

        if not body_template:
            body_template = "Hi {{candidate_name}}, following up regarding opportunities at {{company}}."

        # Personalize text
        cand_name = getattr(candidate, "full_name", "Candidate") or "Candidate"
        skills_str = ""
        if candidate and hasattr(candidate, "profile") and candidate.profile and candidate.profile.skills_json:
            try:
                sk_arr = json.loads(candidate.profile.skills_json)
                skills_str = ", ".join(str(s) for s in sk_arr if s)
            except Exception:
                skills_str = ""

        subj_context = {
            "candidate_name": cand_name,
            "first_name": cand_name.split()[0] if cand_name else "there",
            "company": "Innovate Tech",
            "job_title": getattr(candidate, "current_title", "Senior Role") or "Senior Role",
            "skills": skills_str or "your technical domain",
            "recruiter_name": "Talent Hunt Recruiter",
        }

        rendered_body = generate_candidate_outreach(
            template_body=body_template,
            candidate=candidate,
            recruiter_name="Talent Hunt Recruiter",
        )
        rendered_subject = render_template(subject, subj_context)

        # Send / Log communication
        recipient_addr = candidate.email or f"candidate_{candidate.id}@talenthunt-demo.com"
        
        send_res = send_email(
            to_email=recipient_addr,
            subject=rendered_subject,
            body=rendered_body,
        )

        comm_record = None
        try:
            comm_record = log_communication(
                db,
                candidate_id=candidate.id,
                channel=step.channel,
                direction="outbound",
                sender="recruiter@talenthunt.os",
                recipient=recipient_addr,
                subject=rendered_subject,
                body=rendered_body,
                status="sent" if send_res["success"] else "failed",
            )
        except Exception as log_err:
            logger.warning(f"Failed to log communication record: {log_err}")

        # Calculate next step
        enr.last_step_sent_at = datetime.now(timezone.utc)
        if send_res["success"]:
            next_step_num = enr.current_step_number + 1
            next_step_stmt = select(OutreachStep).where(
                OutreachStep.sequence_id == enr.sequence_id,
                OutreachStep.step_number == next_step_num,
            )
            next_step = db.scalar(next_step_stmt)

            if next_step:
                enr.current_step_number = next_step_num
                enr.next_step_due_at = datetime.now(timezone.utc) + timedelta(days=next_step.delay_days)
            else:
                enr.status = "completed"
                enr.next_step_due_at = None
        else:
            enr.status = "paused"

        db.commit()

        processed_results.append({
            "enrollment_id": enr.id,
            "candidate_id": candidate.id,
            "candidate_name": getattr(candidate, "full_name", "Unknown"),
            "step_number": step.step_number,
            "channel": step.channel,
            "communication_id": comm_record.id if comm_record else None,
            "subject": rendered_subject,
            "status": "sent",
        })

    return processed_results


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
