"""Candidate identity review and reversible canonical-record merging."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.candidates.models import (
    Candidate,
    CandidateEducation,
    CandidateExperience,
    CandidateIntakeRequest,
    CandidateNote,
    CandidateProfile,
    CandidateTag,
    DiscoveredProfile,
)


def _text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else digits


def _url(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    path = re.sub(r"/+", "/", parsed.path).rstrip("/").casefold()
    return urlunsplit(("https", host, path, "", "")) if host else _text(value)


def duplicate_reasons(left: Candidate, right: Candidate) -> list[str]:
    """Return conservative identity signals shared by two records."""
    reasons: list[str] = []
    checks = (
        ("email", _text(left.email), _text(right.email)),
        ("phone", _phone(left.phone), _phone(right.phone)),
        ("LinkedIn URL", _url(left.linkedin_url), _url(right.linkedin_url)),
        ("GitHub URL", _url(left.github_url), _url(right.github_url)),
        ("portfolio URL", _url(left.portfolio_url), _url(right.portfolio_url)),
    )
    for label, a, b in checks:
        if a and a == b:
            reasons.append(f"Same {label}")

    same_name = _text(left.full_name) and _text(left.full_name) == _text(right.full_name)
    same_company = _text(left.current_company) and _text(left.current_company) == _text(right.current_company)
    same_location = _text(left.location) and _text(left.location) == _text(right.location)
    if same_name and same_company:
        reasons.append("Same name and company")
    if same_name and same_location:
        reasons.append("Same name and location")
    return reasons


def _identity_strength(reasons: list[str]) -> int:
    strong = {"Same email", "Same phone", "Same LinkedIn URL", "Same GitHub URL", "Same portfolio URL"}
    return 100 if any(reason in strong for reason in reasons) else 70


def find_candidate_duplicates(
    db: Session,
    *,
    candidate_id: int | None = None,
    include_archived: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Find likely duplicate pairs without modifying canonical records."""
    stmt = select(Candidate).options(
        selectinload(Candidate.profile),
        selectinload(Candidate.tags),
        selectinload(Candidate.experiences),
        selectinload(Candidate.educations),
    )
    if not include_archived:
        stmt = stmt.where(Candidate.status != "Archived")
    rows = list(db.scalars(stmt.order_by(Candidate.id)).all())
    if candidate_id is not None and not any(row.id == candidate_id for row in rows):
        candidate = db.get(Candidate, candidate_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        rows.append(candidate)

    pairs: list[dict[str, Any]] = []
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            if candidate_id is not None and candidate_id not in {left.id, right.id}:
                continue
            reasons = duplicate_reasons(left, right)
            if not reasons:
                continue
            pairs.append({
                "left": _candidate_identity(left),
                "right": _candidate_identity(right),
                "reasons": reasons,
                "confidence": _identity_strength(reasons),
            })
    pairs.sort(key=lambda item: (-item["confidence"], item["left"]["id"], item["right"]["id"]))
    return pairs[: max(1, min(int(limit), 100))]


def find_candidate_identity_conflict(
    db: Session,
    *,
    full_name: str,
    email: str | None = None,
    phone: str | None = None,
    location: str | None = None,
    current_company: str | None = None,
    linkedin_url: str | None = None,
    github_url: str | None = None,
    portfolio_url: str | None = None,
) -> tuple[Candidate, list[str]] | None:
    """Return an existing canonical identity that makes automatic creation unsafe."""
    incoming = Candidate(
        full_name=full_name,
        email=email,
        phone=phone,
        location=location,
        current_company=current_company,
        linkedin_url=linkedin_url,
        github_url=github_url,
        portfolio_url=portfolio_url,
        status="Active",
    )
    rows = list(db.scalars(select(Candidate).where(Candidate.status != "Archived")).all())
    for row in rows:
        reasons = duplicate_reasons(incoming, row)
        same_unqualified_name = (
            _text(full_name) == _text(row.full_name)
            and not current_company
            and not row.current_company
            and not linkedin_url
            and not row.linkedin_url
        )
        if reasons or same_unqualified_name:
            return row, reasons or ["Same name with no distinguishing identity fields"]
    return None


def _candidate_identity(candidate: Candidate) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "full_name": candidate.full_name,
        "status": candidate.status,
        "current_title": candidate.current_title,
        "current_company": candidate.current_company,
        "location": candidate.location,
        "email": candidate.email,
        "linkedin_url": candidate.linkedin_url,
        "evidence": {
            "experiences": len(candidate.experiences or []),
            "educations": len(candidate.educations or []),
            "tags": len(candidate.tags or []),
        },
    }


def _reference_counts(db: Session, candidate_id: int) -> dict[str, int]:
    from app.communications.models import Communication, CommunicationThread, OutreachEnrollment
    from app.hunts.models import HuntCandidate, PlaybookEntry

    models = {
        "discoveries": DiscoveredProfile,
        "hunt_enrollments": HuntCandidate,
        "communication_threads": CommunicationThread,
        "communications": Communication,
        "outreach_enrollments": OutreachEnrollment,
        "intake_requests": CandidateIntakeRequest,
        "playbook_entries": PlaybookEntry,
    }
    return {
        label: len(list(db.scalars(select(model.id).where(model.candidate_id == candidate_id)).all()))
        for label, model in models.items()
    }


def preview_candidate_merge(db: Session, survivor_id: int, source_id: int) -> dict[str, Any]:
    if survivor_id == source_id:
        raise ValueError("Survivor and source must be different candidates.")
    survivor = db.get(Candidate, survivor_id)
    source = db.get(Candidate, source_id)
    if not survivor or not source:
        raise ValueError("Both Candidate records must exist.")
    if source.status == "Archived":
        raise ValueError("The source Candidate is already archived.")

    reasons = duplicate_reasons(survivor, source)
    fill_fields = [
        field for field in (
            "email", "phone", "location", "current_title", "current_company", "pronouns",
            "connection_degree", "connections_count", "profile_image_url", "experience_years",
            "linkedin_url", "github_url", "portfolio_url",
        )
        if not getattr(survivor, field, None) and getattr(source, field, None)
    ]
    from app.hunts.models import HuntCandidate
    survivor_hunts = {
        row.hunt_id
        for row in db.scalars(
            select(HuntCandidate).where(HuntCandidate.candidate_id == survivor_id)
        ).all()
    }
    source_hunts = list(db.scalars(select(HuntCandidate).where(HuntCandidate.candidate_id == source_id)).all())
    return {
        "title": "Merge duplicate Candidates",
        "summary": f"Keep {survivor.full_name} (#{survivor.id}) and archive {source.full_name} (#{source.id}).",
        "survivor": _candidate_identity(survivor),
        "source": _candidate_identity(source),
        "duplicate_reasons": reasons,
        "identity_warning": not bool(reasons),
        "fields_filled": fill_fields,
        "source_references": _reference_counts(db, source_id),
        "overlapping_hunts": sum(1 for row in source_hunts if row.hunt_id in survivor_hunts),
        "source_retained": True,
        "reversible": True,
        "undo_window_days": 7,
        "affected_resources": [f"candidate:{survivor_id}", f"candidate:{source_id}"],
    }


def _json_values(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
        return [str(item).strip() for item in parsed if str(item).strip()] if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _merge_json(left: str | None, right: str | None) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for item in [*_json_values(left), *_json_values(right)]:
        key = _text(item)
        if key and key not in seen:
            seen.add(key)
            values.append(item)
    return json.dumps(values)


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _hunt_snapshot(row) -> dict[str, Any]:
    fields = (
        "id", "hunt_id", "candidate_id", "stage_id", "full_name", "email", "phone",
        "current_title", "current_company", "location", "linkedin_url", "github_url",
        "portfolio_url", "match_score", "ai_summary", "notes", "source_platform",
        "source_query", "status", "created_at", "updated_at",
    )
    return {field: _iso(getattr(row, field)) for field in fields}


def merge_candidate_records(
    db: Session,
    *,
    survivor_id: int,
    source_id: int,
    actor_type: str,
    session_id: str | None,
):
    """Merge source evidence/references into survivor and retain source as archived."""
    from app.actions.history import record_action
    from app.candidates.service import serialize_candidate_profile_state
    from app.communications.models import Communication, CommunicationThread, OutreachEnrollment
    from app.hunts.models import HuntActivity, HuntCandidate, PlaybookEntry

    preview = preview_candidate_merge(db, survivor_id, source_id)
    survivor = db.get(Candidate, survivor_id)
    source = db.get(Candidate, source_id)
    before_survivor = serialize_candidate_profile_state(survivor)
    before_source = serialize_candidate_profile_state(source)
    undo: dict[str, Any] = {
        "survivor_state": before_survivor,
        "source_state": before_source,
        "created_tag_ids": [],
        "created_note_ids": [],
        "reassigned": {},
        "hunt_rows_moved": [],
        "hunt_rows_collapsed": [],
    }

    try:
        source_values = {
            field: getattr(source, field)
            for field in (
                "email", "phone", "location", "current_title", "current_company", "pronouns",
                "connection_degree", "connections_count", "profile_image_url", "experience_years",
                "linkedin_url", "github_url", "portfolio_url",
            )
        }
        if not survivor.email and source_values["email"]:
            source.email = None
            db.flush()

        scalar_fields = (
            "email", "phone", "location", "current_title", "current_company", "pronouns",
            "connection_degree", "connections_count", "profile_image_url", "experience_years",
            "linkedin_url", "github_url", "portfolio_url",
        )
        for field in scalar_fields:
            if not getattr(survivor, field, None) and source_values[field]:
                setattr(survivor, field, source_values[field])

        if source.profile and not survivor.profile:
            survivor.profile = CandidateProfile(candidate_id=survivor.id)
            db.add(survivor.profile)
            db.flush()
        if source.profile and survivor.profile:
            for field in ("headline", "summary", "resume_text", "ai_evaluation"):
                incoming = getattr(source.profile, field)
                current = getattr(survivor.profile, field)
                if incoming and (not current or field in {"summary", "resume_text"} and len(incoming) > len(current)):
                    setattr(survivor.profile, field, incoming)
            for field in ("skills_json", "languages_json", "highlights_json"):
                setattr(survivor.profile, field, _merge_json(getattr(survivor.profile, field), getattr(source.profile, field)))

        exp_keys = {
            (_text(row.company), _text(row.title), _text(row.start_date), _text(row.end_date))
            for row in survivor.experiences or []
        }
        for row in source.experiences or []:
            key = (_text(row.company), _text(row.title), _text(row.start_date), _text(row.end_date))
            if key in exp_keys:
                continue
            db.add(CandidateExperience(
                candidate_id=survivor.id, company=row.company, title=row.title, location=row.location,
                start_date=row.start_date, end_date=row.end_date, is_current=row.is_current,
                employment_type=row.employment_type, description=row.description, skills_json=row.skills_json,
            ))
            exp_keys.add(key)

        edu_keys = {
            (_text(row.institution), _text(row.degree), _text(row.field_of_study), row.start_year, row.end_year)
            for row in survivor.educations or []
        }
        for row in source.educations or []:
            key = (_text(row.institution), _text(row.degree), _text(row.field_of_study), row.start_year, row.end_year)
            if key in edu_keys:
                continue
            db.add(CandidateEducation(
                candidate_id=survivor.id, institution=row.institution, degree=row.degree,
                field_of_study=row.field_of_study, start_year=row.start_year, end_year=row.end_year,
                grade=row.grade, activities=row.activities, description=row.description,
            ))
            edu_keys.add(key)

        existing_tags = {_text(row.tag_name) for row in survivor.tags or []}
        for row in source.tags or []:
            if _text(row.tag_name) in existing_tags:
                continue
            created = CandidateTag(candidate_id=survivor.id, tag_name=row.tag_name, color=row.color)
            db.add(created)
            db.flush()
            undo["created_tag_ids"].append(created.id)
            existing_tags.add(_text(row.tag_name))

        existing_notes = {(_text(row.author), _text(row.content)) for row in survivor.notes or []}
        for row in source.notes or []:
            key = (_text(row.author), _text(row.content))
            if key in existing_notes:
                continue
            created = CandidateNote(
                candidate_id=survivor.id, author=row.author, content=row.content, created_at=row.created_at
            )
            db.add(created)
            db.flush()
            undo["created_note_ids"].append(created.id)
            existing_notes.add(key)

        simple_models = {
            "discoveries": DiscoveredProfile,
            "communication_threads": CommunicationThread,
            "communications": Communication,
            "outreach_enrollments": OutreachEnrollment,
            "intake_requests": CandidateIntakeRequest,
            "playbook_entries": PlaybookEntry,
        }
        for label, model in simple_models.items():
            rows = list(db.scalars(select(model).where(model.candidate_id == source.id)).all())
            undo["reassigned"][label] = [row.id for row in rows]
            for row in rows:
                row.candidate_id = survivor.id

        survivor_hunts = {
            row.hunt_id: row
            for row in db.scalars(select(HuntCandidate).where(HuntCandidate.candidate_id == survivor.id)).all()
        }
        source_hunts = list(db.scalars(select(HuntCandidate).where(HuntCandidate.candidate_id == source.id)).all())
        for row in source_hunts:
            existing = survivor_hunts.get(row.hunt_id)
            if existing is None:
                row.candidate_id = survivor.id
                undo["hunt_rows_moved"].append(row.id)
                survivor_hunts[row.hunt_id] = row
                continue
            activity_ids = [activity.id for activity in row.activities or []]
            for activity in list(row.activities or []):
                activity.candidate = existing
            undo["hunt_rows_collapsed"].append({
                "row": _hunt_snapshot(row),
                "activity_ids": activity_ids,
            })
            db.flush()
            db.delete(row)

        source.status = "Archived"
        db.flush()
        history = record_action(
            db,
            action_type="merge_candidates",
            summary=f"Merged candidate {source.full_name} into {survivor.full_name}",
            actor_type=actor_type,
            session_id=session_id,
            payload={"candidate_id": survivor.id, "candidate_ids": [survivor.id, source.id], "source_id": source.id},
            undo_payload=undo,
        )
    except Exception:
        db.rollback()
        raise
    return history, preview


def undo_candidate_merge(db: Session, payload: dict[str, Any]) -> tuple[Candidate, Candidate]:
    """Restore both canonical records and every reference moved by a merge."""
    from app.candidates.service import restore_candidate_profile_state
    from app.communications.models import Communication, CommunicationThread, OutreachEnrollment
    from app.hunts.models import HuntActivity, HuntCandidate, PlaybookEntry

    survivor_state = payload.get("survivor_state") or {}
    source_state = payload.get("source_state") or {}
    survivor_id = int(survivor_state.get("candidate_id"))
    source_id = int(source_state.get("candidate_id"))
    survivor = db.get(Candidate, survivor_id)
    source = db.get(Candidate, source_id)
    if not survivor or not source:
        raise ValueError("Both merged Candidate records are required for undo.")

    # Release the unique email before restoring each exact profile state.
    survivor.email = None
    source.email = None
    db.flush()

    for tag_id in payload.get("created_tag_ids", []):
        row = db.get(CandidateTag, int(tag_id))
        if row:
            db.delete(row)
    for note_id in payload.get("created_note_ids", []):
        row = db.get(CandidateNote, int(note_id))
        if row:
            db.delete(row)
    db.flush()

    survivor = restore_candidate_profile_state(db, survivor_state)
    source = restore_candidate_profile_state(db, source_state)
    if not survivor or not source:
        raise ValueError("Candidate profile state could not be restored.")

    simple_models = {
        "discoveries": DiscoveredProfile,
        "communication_threads": CommunicationThread,
        "communications": Communication,
        "outreach_enrollments": OutreachEnrollment,
        "intake_requests": CandidateIntakeRequest,
        "playbook_entries": PlaybookEntry,
    }
    for label, ids in (payload.get("reassigned") or {}).items():
        model = simple_models.get(label)
        if model is None:
            continue
        for row_id in ids:
            row = db.get(model, int(row_id))
            if row:
                row.candidate_id = source_id

    for row_id in payload.get("hunt_rows_moved", []):
        row = db.get(HuntCandidate, int(row_id))
        if row:
            row.candidate_id = source_id

    for collapsed in payload.get("hunt_rows_collapsed", []):
        values = dict(collapsed.get("row") or {})
        for field in ("created_at", "updated_at"):
            if values.get(field):
                values[field] = datetime.fromisoformat(values[field])
        restored = HuntCandidate(**values)
        db.add(restored)
        db.flush()
        for activity_id in collapsed.get("activity_ids", []):
            activity = db.get(HuntActivity, int(activity_id))
            if activity:
                activity.candidate_id = restored.id

    db.flush()
    return survivor, source
