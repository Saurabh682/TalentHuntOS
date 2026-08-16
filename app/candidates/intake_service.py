"""Candidate JD intake form: create magic links, accept submissions, apply to profile."""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.candidates.models import (
    Candidate,
    CandidateIntakeRequest,
    CandidateIntakeSubmission,
)
from app.candidates.service import (
    add_candidate_note,
    get_candidate,
    replace_or_merge_profile_sections,
    serialize_candidate_profile_state,
)

logger = logging.getLogger("talenthunt.candidates.intake")

DEFAULT_EXPIRY_DAYS = 14


def _public_base_url() -> str:
    from app.config.settings import settings

    return f"http://127.0.0.1:{settings.port}"


def intake_url_for_token(token: str) -> str:
    return f"{_public_base_url()}/intake/{token}"


def create_intake_request(
    db: Session,
    candidate_id: int,
    hunt_id: Optional[int] = None,
    *,
    expires_in_days: int = DEFAULT_EXPIRY_DAYS,
    mark_sent: bool = True,
    commit: bool = True,
) -> Optional[CandidateIntakeRequest]:
    """Create a tokenized intake request for a candidate (optionally tied to a hunt JD)."""
    candidate = get_candidate(db, candidate_id)
    if not candidate:
        return None

    token = secrets.token_urlsafe(24)
    expires_at = datetime.now(timezone.utc) + timedelta(days=max(1, expires_in_days))
    req = CandidateIntakeRequest(
        token=token,
        candidate_id=candidate_id,
        hunt_id=hunt_id,
        status="sent" if mark_sent else "draft",
        expires_at=expires_at,
    )
    db.add(req)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(req)
    return req


def draft_outreach_message(
    candidate: Candidate,
    *,
    url: str,
    hunt_title: Optional[str] = None,
    role: Optional[str] = None,
) -> str:
    name = (candidate.full_name or "there").split()[0]
    role_bit = role or hunt_title or "an open role"
    hunt_bit = f" for {hunt_title}" if hunt_title and role and hunt_title != role else ""
    return (
        f"Hi {name},\n\n"
        f"We're hiring for {role_bit}{hunt_bit} and would love a few details "
        f"to better match you to the role.\n\n"
        f"Please fill this short form (takes ~5 minutes):\n{url}\n\n"
        f"Thanks!\nTalentHunt OS"
    )


def get_intake_by_token(db: Session, token: str) -> Optional[CandidateIntakeRequest]:
    stmt = (
        select(CandidateIntakeRequest)
        .options(selectinload(CandidateIntakeRequest.submissions))
        .where(CandidateIntakeRequest.token == token)
    )
    return db.scalars(stmt).first()


def is_intake_open(req: CandidateIntakeRequest) -> Tuple[bool, str]:
    if req.status in {"accepted", "rejected", "expired"}:
        return False, f"This form is {req.status}."
    if req.status == "submitted":
        return False, "You already submitted this form. Thank you!"
    if req.expires_at:
        exp = req.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp:
            return False, "This form link has expired."
    return True, ""


def get_hunt_jd_context(db: Session, hunt_id: Optional[int]) -> Dict[str, Any]:
    if not hunt_id:
        return {}
    try:
        from app.hunts.service import get_hunt

        hunt = get_hunt(db, hunt_id)
        if not hunt:
            return {}
        cfg = hunt.search_config
        return {
            "hunt_id": hunt.id,
            "title": hunt.title,
            "role": hunt.target_role,
            "location": hunt.location or (cfg.locations if cfg else None),
            "salary_range": hunt.salary_range,
            "description": hunt.description,
            "required_skills": cfg.required_skills if cfg else None,
            "experience_min": cfg.experience_years_min if cfg else None,
            "experience_max": cfg.experience_years_max if cfg else None,
            "industry": cfg.industry if cfg else None,
        }
    except Exception as e:
        logger.warning("Failed to load hunt JD context for hunt_id=%s: %s", hunt_id, e)
        return {}


def submit_intake(
    db: Session,
    token: str,
    payload: Dict[str, Any],
) -> Tuple[Optional[CandidateIntakeSubmission], str]:
    """Store a candidate submission as pending review. Locks the token after submit."""
    req = get_intake_by_token(db, token)
    if not req:
        return None, "Invalid form link."
    open_ok, reason = is_intake_open(req)
    if not open_ok:
        return None, reason

    claimed = db.execute(
        update(CandidateIntakeRequest)
        .where(
            CandidateIntakeRequest.id == req.id,
            CandidateIntakeRequest.status.in_(("draft", "sent")),
        )
        .values(status="submitted")
    )
    if claimed.rowcount != 1:
        db.rollback()
        return None, "You already submitted this form. Thank you!"

    sub = CandidateIntakeSubmission(
        request_id=req.id,
        payload_json=json.dumps(payload),
        review_status="pending",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub, "ok"


def list_pending_submissions(
    db: Session,
    *,
    candidate_id: Optional[int] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    stmt = (
        select(CandidateIntakeSubmission)
        .options(selectinload(CandidateIntakeSubmission.request))
        .where(CandidateIntakeSubmission.review_status == "pending")
        .order_by(CandidateIntakeSubmission.submitted_at.desc())
        .limit(limit)
    )
    rows = list(db.scalars(stmt).all())
    out: List[Dict[str, Any]] = []
    for s in rows:
        req = s.request
        if candidate_id and req and req.candidate_id != candidate_id:
            continue
        try:
            payload = json.loads(s.payload_json)
        except json.JSONDecodeError:
            payload = {}
        out.append({
            "submission_id": s.id,
            "request_id": s.request_id,
            "candidate_id": req.candidate_id if req else None,
            "hunt_id": req.hunt_id if req else None,
            "token": req.token if req else None,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            "payload": payload,
        })
    return out


def get_latest_intake_status(db: Session, candidate_id: int) -> Dict[str, Any]:
    """Summary chip data for the profile header."""
    stmt = (
        select(CandidateIntakeRequest)
        .options(selectinload(CandidateIntakeRequest.submissions))
        .where(CandidateIntakeRequest.candidate_id == candidate_id)
        .order_by(CandidateIntakeRequest.created_at.desc())
        .limit(1)
    )
    req = db.scalars(stmt).first()
    if not req:
        return {"label": "Form not sent", "status": "none", "request_id": None, "submission_id": None}

    pending = next(
        (s for s in (req.submissions or []) if s.review_status == "pending"),
        None,
    )
    label_map = {
        "draft": "Form draft",
        "sent": "Link active",
        "submitted": "Submitted — review",
        "accepted": "Form applied",
        "rejected": "Form rejected",
        "expired": "Form expired",
    }
    return {
        "label": label_map.get(req.status, req.status),
        "status": req.status,
        "request_id": req.id,
        "submission_id": pending.id if pending else None,
        "token": req.token,
        "url": intake_url_for_token(req.token),
    }


def apply_intake_submission(
    db: Session,
    submission_id: int,
    *,
    mode: str = "merge",
    accept: bool = True,
    profile_payload: Optional[Dict[str, Any]] = None,
    actor_type: str = "ui",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Accept (merge into profile) or reject a pending intake submission."""
    sub = db.get(CandidateIntakeSubmission, submission_id)
    if not sub:
        return {"status": "error", "message": "Submission not found."}
    if sub.review_status != "pending":
        return {"status": "error", "message": f"Already {sub.review_status}."}

    req = db.get(CandidateIntakeRequest, sub.request_id)
    if not req:
        return {"status": "error", "message": "Intake request missing."}

    previous_request_status = req.status
    previous_review_status = sub.review_status
    previous_reviewed_at = sub.reviewed_at.isoformat() if sub.reviewed_at else None

    if not accept:
        sub.review_status = "rejected"
        sub.reviewed_at = datetime.now(timezone.utc)
        req.status = "rejected"
        from app.actions.history import record_action

        history = record_action(
            db,
            action_type="review_intake_submission",
            summary=f"Rejected candidate intake submission #{submission_id}",
            actor_type=actor_type,
            session_id=session_id,
            payload={
                "submission_id": submission_id,
                "request_id": req.id,
                "candidate_id": req.candidate_id,
                "decision": "reject",
            },
            undo_payload={
                "request_id": req.id,
                "submission_id": sub.id,
                "request_status": previous_request_status,
                "review_status": previous_review_status,
                "reviewed_at": previous_reviewed_at,
            },
        )
        return {
            "status": "success", "action": "rejected", "submission_id": submission_id,
            "candidate_id": req.candidate_id, "action_id": history.id,
            "undoable": True, "undo_window_days": 7,
        }

    try:
        payload = json.loads(sub.payload_json)
    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid submission payload."}

    reviewed = dict(payload)
    if profile_payload is not None:
        for key in ("experiences", "educations", "skills", "summary", "experience_years"):
            if key in profile_payload:
                reviewed[key] = profile_payload[key]

    experiences = reviewed.get("experiences") or []
    educations = reviewed.get("educations") or []
    skills = reviewed.get("skills") or []
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",") if s.strip()]

    contact = payload.get("contact") or {}
    candidate_before = get_candidate(db, req.candidate_id)
    if not candidate_before:
        return {"status": "error", "message": "Candidate not found."}
    before_state = serialize_candidate_profile_state(candidate_before)
    update_kwargs: Dict[str, Any] = {}
    if contact.get("email"):
        update_kwargs["email"] = str(contact["email"]).strip()
    if contact.get("phone"):
        update_kwargs["phone"] = str(contact["phone"]).strip()
    if contact.get("location"):
        update_kwargs["location"] = str(contact["location"]).strip()

    from app.candidates.service import update_candidate

    if update_kwargs:
        update_candidate(db, req.candidate_id, **update_kwargs)

    cand = replace_or_merge_profile_sections(
        db,
        req.candidate_id,
        experiences=experiences,
        educations=educations,
        skills=skills,
        summary=reviewed.get("summary"),
        experience_years=reviewed.get("experience_years"),
        mode=mode,
        record_history=False,
    )
    if not cand:
        return {"status": "error", "message": "Failed to apply profile sections."}

    # JD fit answers → recruiter note
    fit = payload.get("jd_fit") or {}
    fit_lines = []
    for key, label in (
        ("availability", "Availability"),
        ("notice_period", "Notice period"),
        ("salary_expectation", "Salary expectation"),
        ("why_fit", "Why fit"),
    ):
        val = (fit.get(key) or "").strip() if isinstance(fit.get(key), str) else fit.get(key)
        if val:
            fit_lines.append(f"{label}: {val}")
    created_note_ids: List[int] = []
    if fit_lines:
        note = add_candidate_note(
            db,
            req.candidate_id,
            "Candidate intake form — JD fit:\n" + "\n".join(fit_lines),
            author="Intake Form",
        )
        if note:
            created_note_ids.append(note.id)

    sub.review_status = "accepted"
    sub.reviewed_at = datetime.now(timezone.utc)
    req.status = "accepted"
    from app.actions.history import record_action

    history = record_action(
        db,
        action_type="apply_intake_submission",
        summary=f"Applied candidate intake submission for {cand.full_name}",
        actor_type=actor_type,
        session_id=session_id,
        payload={
            "submission_id": submission_id,
            "candidate_id": req.candidate_id,
            "mode": mode,
        },
        undo_payload={
            "candidate_state": before_state,
            "request_id": req.id,
            "submission_id": sub.id,
            "request_status": previous_request_status,
            "review_status": previous_review_status,
            "reviewed_at": previous_reviewed_at,
            "created_note_ids": created_note_ids,
        },
    )

    return {
        "status": "success",
        "action": "accepted",
        "submission_id": submission_id,
        "candidate_id": req.candidate_id,
        "mode": mode,
        "action_id": history.id,
        "undoable": True,
        "undo_window_days": 7,
    }
