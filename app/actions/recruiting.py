"""Registered recruiting actions shared by Copilot and NiceGUI pages."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.actions.context import ActionContext
from app.actions.registry import register_action


def _history_actor(ctx: ActionContext) -> str:
    return "copilot" if ctx.actor_type == "agent" else ctx.actor_type


def _json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _candidate_payload(candidate) -> dict[str, Any]:
    profile = candidate.profile
    skills = _json_list(profile.skills_json) if profile else []
    highlights = _json_list(profile.highlights_json) if profile else []
    return {
        "id": candidate.id,
        "full_name": candidate.full_name,
        "email": candidate.email,
        "phone": candidate.phone,
        "location": candidate.location,
        "current_title": candidate.current_title,
        "current_company": candidate.current_company,
        "pronouns": candidate.pronouns,
        "connection_degree": candidate.connection_degree,
        "connections_count": candidate.connections_count,
        "profile_image_url": candidate.profile_image_url,
        "experience_years": candidate.experience_years,
        "linkedin_url": candidate.linkedin_url,
        "github_url": candidate.github_url,
        "portfolio_url": candidate.portfolio_url,
        "status": candidate.status,
        "headline": profile.headline if profile else None,
        "summary": profile.summary if profile else None,
        "resume_text": profile.resume_text if profile else None,
        "skills": skills,
        "highlights": highlights,
        "tags": [tag.tag_name for tag in candidate.tags or []],
        "tag_records": [
            {"id": tag.id, "name": tag.tag_name, "color": tag.color} for tag in candidate.tags or []
        ],
        "notes": [
            {
                "id": note.id,
                "author": note.author,
                "content": note.content,
                "created_at": note.created_at.isoformat(),
            }
            for note in candidate.notes or []
        ],
        "experiences": [
            {
                "id": row.id,
                "company": row.company,
                "title": row.title,
                "location": row.location,
                "start_date": row.start_date,
                "end_date": row.end_date,
                "is_current": row.is_current,
                "employment_type": row.employment_type,
                "description": row.description,
                "skills": _json_list(row.skills_json),
            }
            for row in candidate.experiences or []
        ],
        "educations": [
            {
                "id": row.id,
                "institution": row.institution,
                "degree": row.degree,
                "field_of_study": row.field_of_study,
                "start_year": row.start_year,
                "end_year": row.end_year,
                "grade": row.grade,
                "activities": row.activities,
                "description": row.description,
            }
            for row in candidate.educations or []
        ],
    }


def _candidate_summary(candidate) -> dict[str, Any]:
    profile = candidate.profile
    return {
        "id": candidate.id,
        "full_name": candidate.full_name,
        "current_title": candidate.current_title,
        "current_company": candidate.current_company,
        "location": candidate.location,
        "experience_years": candidate.experience_years,
        "status": candidate.status,
        "linkedin_url": candidate.linkedin_url,
        "skills": _json_list(profile.skills_json) if profile else [],
        "tags": [
            {"id": tag.id, "name": tag.tag_name, "color": tag.color} for tag in candidate.tags or []
        ],
    }


def _discovery_payload(match) -> dict[str, Any]:
    profile = match.profile
    return {
        "match_id": match.id,
        "hunt_id": match.hunt_id,
        "hunt_title": match.hunt.title if match.hunt else None,
        "status": match.status,
        "match_score": match.match_score,
        "source_platform": match.source_platform,
        "source_query": match.source_query,
        "rejection_reason": match.rejection_reason,
        "scan_error": match.scan_error,
        "last_seen_at": match.last_seen_at.isoformat(),
        "profile": {
            "id": profile.id,
            "candidate_id": profile.candidate_id,
            "full_name": profile.full_name,
            "headline": profile.headline,
            "current_company": profile.current_company,
            "location": profile.location,
            "experience_years": profile.experience_years,
            "platform": profile.platform,
            "source_url": profile.source_url,
            "snippet": profile.snippet,
            "seen_count": profile.seen_count,
            "deep_scanned": profile.deep_scanned_at is not None,
        },
    }


def _common_pool_payload(profile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "candidate_id": profile.candidate_id,
        "full_name": profile.full_name,
        "headline": profile.headline,
        "current_company": profile.current_company,
        "location": profile.location,
        "experience_years": profile.experience_years,
        "platform": profile.platform,
        "source_url": profile.source_url,
        "snippet": profile.snippet,
        "status": profile.status,
        "seen_count": profile.seen_count,
        "first_seen_at": profile.first_seen_at.isoformat(),
        "last_seen_at": profile.last_seen_at.isoformat(),
        "deep_scanned": profile.deep_scanned_at is not None,
        "hunt_matches": [
            {
                "match_id": match.id,
                "hunt_id": match.hunt_id,
                "hunt_title": match.hunt.title if match.hunt else None,
                "status": match.status,
                "match_score": match.match_score,
            }
            for match in profile.hunt_matches or []
        ],
    }


class CandidateGetInput(BaseModel):
    candidate_id: int = Field(gt=0)


class CandidateCreateInput(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=100)
    current_title: str | None = Field(default=None, max_length=100)
    current_company: str | None = Field(default=None, max_length=100)
    experience_years: float | None = Field(default=None, ge=0, le=60)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    headline: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=50000)
    resume_text: str | None = Field(default=None, max_length=200000)
    skills: list[str] = Field(default_factory=list, max_length=300)
    tags: list[str] = Field(default_factory=list, max_length=100)
    status: str | None = Field(default=None, max_length=30)
    hunt_id: int | None = Field(default=None, gt=0)

    @field_validator("full_name")
    @classmethod
    def clean_create_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("status")
    @classmethod
    def valid_create_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().title()
        if normalized not in {"Active", "Passive", "Sourced"}:
            raise ValueError("status must be Active, Passive, or Sourced")
        return normalized


class CandidateListInput(BaseModel):
    search: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=30)
    offset: int = Field(default=0, ge=0, le=100000)
    limit: int = Field(default=50, ge=1, le=100)


class CandidateArchiveInput(BaseModel):
    candidate_id: int = Field(gt=0)


class CandidateDuplicateListInput(BaseModel):
    candidate_id: int | None = Field(default=None, gt=0)
    include_archived: bool = False
    limit: int = Field(default=50, ge=1, le=100)


class CandidateMergeInput(BaseModel):
    survivor_id: int = Field(gt=0)
    source_id: int = Field(gt=0)

    @field_validator("source_id")
    @classmethod
    def different_candidates(cls, value: int, info) -> int:
        if info.data.get("survivor_id") == value:
            raise ValueError("source_id must differ from survivor_id")
        return value


class CandidateTagAddInput(BaseModel):
    candidate_id: int = Field(gt=0)
    tag_name: str = Field(min_length=1, max_length=50)
    color: str = Field(default="#00d4aa", min_length=4, max_length=30)

    @field_validator("tag_name")
    @classmethod
    def clean_tag_name(cls, value: str) -> str:
        return value.strip()


class CandidateTagRemoveInput(BaseModel):
    candidate_id: int = Field(gt=0)
    tag_id: int = Field(gt=0)


class CandidateNoteAddInput(BaseModel):
    candidate_id: int = Field(gt=0)
    content: str = Field(min_length=1, max_length=10000)
    author: str = Field(default="Recruiter", min_length=1, max_length=100)

    @field_validator("content", "author")
    @classmethod
    def clean_note_text(cls, value: str) -> str:
        return value.strip()


class CandidateExperienceSaveInput(BaseModel):
    candidate_id: int = Field(gt=0)
    experience_id: int | None = Field(default=None, gt=0)
    company: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=100)
    location: str | None = Field(default=None, max_length=100)
    start_date: str | None = Field(default=None, max_length=30)
    end_date: str | None = Field(default=None, max_length=30)
    is_current: bool = False
    employment_type: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=10000)
    skills: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("company", "title")
    @classmethod
    def clean_required_experience_text(cls, value: str) -> str:
        return value.strip()


class CandidateExperienceRemoveInput(BaseModel):
    candidate_id: int = Field(gt=0)
    experience_id: int = Field(gt=0)


class CandidateEducationSaveInput(BaseModel):
    candidate_id: int = Field(gt=0)
    education_id: int | None = Field(default=None, gt=0)
    institution: str = Field(min_length=1, max_length=120)
    degree: str | None = Field(default=None, max_length=100)
    field_of_study: str | None = Field(default=None, max_length=100)
    start_year: int | None = Field(default=None, ge=1900, le=2200)
    end_year: int | None = Field(default=None, ge=1900, le=2200)
    grade: str | None = Field(default=None, max_length=100)
    activities: str | None = Field(default=None, max_length=5000)
    description: str | None = Field(default=None, max_length=10000)

    @field_validator("institution")
    @classmethod
    def clean_institution(cls, value: str) -> str:
        return value.strip()


class CandidateEducationRemoveInput(BaseModel):
    candidate_id: int = Field(gt=0)
    education_id: int = Field(gt=0)


class CandidateProfileApplyInput(BaseModel):
    candidate_id: int = Field(gt=0)
    mode: str = "merge"
    experiences: list[dict[str, Any]] | None = Field(default=None, max_length=100)
    educations: list[dict[str, Any]] | None = Field(default=None, max_length=100)
    skills: list[str] | None = Field(default=None, max_length=300)
    highlights: list[str] | None = Field(default=None, max_length=100)
    full_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=150)
    current_title: str | None = Field(default=None, max_length=150)
    current_company: str | None = Field(default=None, max_length=150)
    pronouns: str | None = Field(default=None, max_length=50)
    connection_degree: str | None = Field(default=None, max_length=30)
    connections_count: int | None = Field(default=None, ge=0, le=100000000)
    profile_image_url: str | None = Field(default=None, max_length=1000)
    headline: str | None = Field(default=None, max_length=500)
    summary: str | None = Field(default=None, max_length=50000)
    experience_years: float | None = Field(default=None, ge=0, le=60)
    resume_text: str | None = Field(default=None, max_length=200000)

    @field_validator("mode")
    @classmethod
    def valid_profile_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"merge", "replace"}:
            raise ValueError("mode must be 'merge' or 'replace'")
        return normalized


class CandidateRogueSetInput(BaseModel):
    candidate_id: int = Field(gt=0)
    enabled: bool
    note: str | None = Field(default=None, max_length=2000)
    author: str = Field(default="Recruiter", min_length=1, max_length=80)


class DiscoveryListInput(BaseModel):
    hunt_id: int | None = Field(default=None, gt=0)
    statuses: list[str] | None = Field(default=None, max_length=20)
    limit: int = Field(default=100, ge=1, le=500)


class DiscoveryGetInput(BaseModel):
    match_id: int = Field(gt=0)


class CommonPoolListInput(BaseModel):
    hunt_id: int | None = Field(default=None, gt=0)
    search: str | None = Field(default=None, max_length=200)
    offset: int = Field(default=0, ge=0, le=100000)
    limit: int = Field(default=50, ge=1, le=100)


class CommonPoolArchiveInput(BaseModel):
    hunt_id: int | None = Field(default=None, gt=0)
    search: str | None = Field(default=None, max_length=200)

    @field_validator("search")
    @classmethod
    def clean_pool_search(cls, value: str | None) -> str | None:
        cleaned = (value or "").strip()
        return cleaned or None


class CandidateUpdateInput(BaseModel):
    candidate_id: int = Field(gt=0)
    full_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=150)
    current_title: str | None = Field(default=None, max_length=150)
    current_company: str | None = Field(default=None, max_length=150)
    experience_years: float | None = None
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, max_length=30)
    headline: str | None = Field(default=None, max_length=255)
    summary: str | None = None
    resume_text: str | None = None
    skills: list[str] | str | None = None

    @field_validator("experience_years")
    @classmethod
    def valid_experience(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= float(value) <= 60:
            raise ValueError("experience_years must be between 0 and 60")
        return value

    @field_validator("full_name")
    @classmethod
    def valid_name(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            raise ValueError("full_name cannot be empty when supplied")
        return value.strip()

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().title()
        allowed = {"Active", "Passive", "Placed", "Archived", "Blacklisted", "Sourced"}
        if normalized not in allowed:
            raise ValueError(f"status must be one of: {', '.join(sorted(allowed))}")
        return normalized


class DiscoveryDecisionInput(BaseModel):
    match_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=500)


class PipelineMoveInput(BaseModel):
    hunt_candidate_id: int = Field(gt=0)
    stage_id: int = Field(gt=0)


class PipelineGetInput(BaseModel):
    hunt_id: int = Field(gt=0)


class PipelineRemoveInput(BaseModel):
    hunt_candidate_id: int = Field(gt=0)


class PipelineEnrollInput(BaseModel):
    candidate_id: int = Field(gt=0)
    hunt_id: int = Field(gt=0)
    move_from_other_hunts: bool = False
    note: str | None = Field(default=None, max_length=2000)


class PipelineTriageInput(BaseModel):
    hunt_candidate_id: int = Field(gt=0)
    decision: str
    note: str | None = Field(default=None, max_length=2000)
    author: str = Field(default="Recruiter", min_length=1, max_length=80)

    @field_validator("decision")
    @classmethod
    def valid_decision(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"keep", "pass"}:
            raise ValueError("decision must be keep or pass")
        return normalized


class PipelineStageAddInput(BaseModel):
    hunt_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=50)
    color: str = Field(default="#19d3c5", min_length=4, max_length=30)

    @field_validator("name")
    @classmethod
    def clean_stage_name(cls, value: str) -> str:
        return value.strip()


class HuntListInput(BaseModel):
    status: str | None = Field(default=None, max_length=30)
    search: str | None = Field(default=None, max_length=200)
    offset: int = Field(default=0, ge=0, le=100000)
    limit: int = Field(default=50, ge=1, le=100)


class HuntGetInput(BaseModel):
    hunt_id: int = Field(gt=0)


class HuntCreateInput(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    target_role: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default="India", max_length=100)
    salary_range: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=50000)
    required_skills: str | None = Field(default=None, max_length=5000)
    preferred_skills: str | None = Field(default=None, max_length=5000)
    experience: str | None = Field(default=None, max_length=100)
    industry: str | None = Field(default=None, max_length=100)
    remote_policy: str | None = Field(default=None, max_length=50)
    target_platforms: list[str] = Field(
        default_factory=lambda: ["linkedin", "naukri"], max_length=20
    )
    status: str = "Active"

    @field_validator("title")
    @classmethod
    def clean_hunt_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("status")
    @classmethod
    def valid_create_hunt_status(cls, value: str) -> str:
        normalized = value.strip().title()
        if normalized not in {"Active", "Draft", "Paused"}:
            raise ValueError("status must be Active, Draft, or Paused")
        return normalized


class HuntUpdateInput(BaseModel):
    hunt_id: int = Field(gt=0)
    title: str | None = Field(default=None, max_length=150)
    target_role: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=100)
    salary_range: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=50000)
    required_skills: str | None = Field(default=None, max_length=5000)
    preferred_skills: str | None = Field(default=None, max_length=5000)
    experience: str | None = Field(default=None, max_length=100)
    industry: str | None = Field(default=None, max_length=100)
    remote_policy: str | None = Field(default=None, max_length=50)
    target_platforms: list[str] | None = Field(default=None, max_length=20)

    @field_validator("title")
    @classmethod
    def valid_update_hunt_title(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("title cannot be empty")
        return value.strip() if value is not None else None


class HuntStatusInput(BaseModel):
    hunt_id: int = Field(gt=0)
    status: str

    @field_validator("status")
    @classmethod
    def valid_hunt_status(cls, value: str) -> str:
        aliases = {"Pause": "Paused", "Resume": "Active"}
        normalized = aliases.get(value.strip().title(), value.strip().title())
        if normalized not in {"Active", "Paused", "Draft", "Completed"}:
            raise ValueError(
                "status must be Active, Paused, Draft, or Completed; use archive for Archived"
            )
        return normalized


class HuntArchiveInput(BaseModel):
    hunt_id: int = Field(gt=0)


class PlaybookListInput(BaseModel):
    entry_type: str | None = Field(default=None, max_length=20)
    role: str | None = Field(default=None, max_length=150)
    platform: str | None = Field(default=None, max_length=50)
    search: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=50, ge=1, le=150)


class PlaybookInsightAddInput(BaseModel):
    worked: bool
    note: str = Field(min_length=1, max_length=5000)
    role_context: str | None = Field(default=None, max_length=150)
    platform: str | None = Field(default=None, max_length=50)
    query_text: str | None = Field(default=None, max_length=5000)
    hunt_id: int | None = Field(default=None, gt=0)
    author_name: str = Field(default="Recruiter", min_length=1, max_length=80)

    @field_validator("note", "author_name")
    @classmethod
    def clean_required_playbook_text(cls, value: str) -> str:
        return value.strip()


class IntakeRequestCreateInput(BaseModel):
    candidate_id: int = Field(gt=0)
    hunt_id: int | None = Field(default=None, gt=0)
    expires_in_days: int = Field(default=14, ge=1, le=90)


class IntakeSubmissionListInput(BaseModel):
    candidate_id: int | None = Field(default=None, gt=0)
    limit: int = Field(default=50, ge=1, le=100)


class IntakeSubmissionReviewInput(BaseModel):
    submission_id: int = Field(gt=0)
    accept: bool = True
    mode: str = "merge"
    profile_payload: dict[str, Any] | None = None

    @field_validator("mode")
    @classmethod
    def valid_intake_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"merge", "replace"}:
            raise ValueError("mode must be merge or replace")
        return normalized


class ActionUndoInput(BaseModel):
    action_id: int | str = "latest"

    @field_validator("action_id")
    @classmethod
    def valid_action_id(cls, value: int | str) -> int | str:
        if isinstance(value, int):
            if value <= 0:
                raise ValueError("action_id must be positive")
            return value
        normalized = str(value).strip().lower()
        if normalized == "latest":
            return normalized
        if normalized.isdigit() and int(normalized) > 0:
            return int(normalized)
        raise ValueError("action_id must be a positive ID or 'latest'")


class AnalyticsScopeInput(BaseModel):
    hunt_id: int | None = Field(default=None, gt=0)


class AnalyticsTrendInput(AnalyticsScopeInput):
    days: int = Field(default=30, ge=1, le=365)


class JobIdInput(BaseModel):
    job_id: str = Field(min_length=6, max_length=32)

    @field_validator("job_id")
    @classmethod
    def valid_job_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized.isalnum():
            raise ValueError("job_id must contain only letters and numbers")
        return normalized


class JobRetryInput(JobIdInput):
    pass


class JobCancelInput(JobIdInput):
    pass


class JobListInput(BaseModel):
    status: str = "all"
    kind: str | None = Field(default=None, max_length=60)
    hunt_id: int | None = Field(default=None, gt=0)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("status")
    @classmethod
    def valid_job_status(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {
            "all",
            "active",
            "retryable",
            "running",
            "done",
            "cancelled",
            "error",
            "interrupted",
        }
        if normalized not in allowed:
            raise ValueError(f"status must be one of: {', '.join(sorted(allowed))}")
        return normalized

    @field_validator("kind")
    @classmethod
    def valid_job_kind(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized or any(
            ch not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for ch in normalized
        ):
            raise ValueError("kind may contain only letters, numbers, underscores, and hyphens")
        return normalized


def _analytics_scope(db, hunt_id: int | None) -> dict[str, Any]:
    if hunt_id is None:
        return {"type": "all_hunts", "hunt_id": None, "hunt_title": None}
    from app.hunts.models import TalentHunt

    hunt = db.get(TalentHunt, hunt_id)
    if not hunt:
        raise ValueError("Talent Hunt not found.")
    return {"type": "hunt", "hunt_id": hunt.id, "hunt_title": hunt.title}


def _analytics_result(
    *,
    metric: str,
    service: str,
    scope: dict[str, Any],
    data: dict[str, Any],
    tables: list[str],
    filters: dict[str, Any] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(data, dict) or not data:
        raise RuntimeError(f"{metric.replace('_', ' ').title()} analytics could not be calculated.")
    return {
        "status": "success",
        "metric": metric,
        "scope": scope,
        "data": data,
        "provenance": {
            "source_of_truth": "canonical TalentHunt database records",
            "service": service,
            "tables": tables,
            "filters": filters or {"hunt_id": scope["hunt_id"]},
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "limitations": limitations or [],
        },
    }


def _undo_resources(data: ActionUndoInput, ctx: ActionContext) -> list[str]:
    from app.actions.history import action_resource_keys, get_undoable_action
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        return action_resource_keys(db, get_undoable_action(db, data.action_id))


def _candidate_resources(
    data: CandidateUpdateInput
    | CandidateArchiveInput
    | CandidateTagAddInput
    | CandidateTagRemoveInput
    | CandidateNoteAddInput
    | CandidateExperienceSaveInput
    | CandidateExperienceRemoveInput
    | CandidateEducationSaveInput
    | CandidateEducationRemoveInput
    | CandidateProfileApplyInput
    | CandidateRogueSetInput,
    ctx: ActionContext,
) -> list[str]:
    return [f"candidate:{data.candidate_id}"]


def _candidate_merge_resources(data: CandidateMergeInput, ctx: ActionContext) -> list[str]:
    return sorted([f"candidate:{data.survivor_id}", f"candidate:{data.source_id}"])


def _candidate_create_resources(data: CandidateCreateInput, ctx: ActionContext) -> list[str]:
    resources = ["candidates:create"]
    if data.hunt_id:
        resources.append(f"hunt:{data.hunt_id}")
    return resources


def _preview_candidate_merge(data: CandidateMergeInput, ctx: ActionContext) -> dict[str, Any]:
    from app.candidates.duplicates import preview_candidate_merge
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        return preview_candidate_merge(db, data.survivor_id, data.source_id)


def _record_candidate_profile_change(
    db,
    *,
    candidate,
    before: dict[str, Any],
    summary: str,
    payload: dict[str, Any],
    ctx: ActionContext,
):
    from app.actions.history import record_action
    from app.candidates.service import _reindex_candidate, restore_candidate_profile_state

    try:
        return record_action(
            db,
            action_type="update_candidate_profile",
            summary=summary,
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={"candidate_id": candidate.id, **payload},
            undo_payload={"candidate_state": before},
        )
    except Exception:
        restored = restore_candidate_profile_state(db, before)
        db.commit()
        if restored:
            _reindex_candidate(db, restored)
        raise


def _refresh_candidate_timeline(db, candidate) -> None:
    from app.hunts.experience import estimate_years_from_experience_rows

    db.flush()
    db.expire(candidate, ["experiences"])
    rows = list(candidate.experiences or [])
    candidate.experience_years = estimate_years_from_experience_rows(rows)
    current = next((row for row in rows if row.is_current), rows[0] if rows else None)
    if current:
        candidate.current_title = current.title
        candidate.current_company = current.company


def _discovery_resources(data: DiscoveryDecisionInput, ctx: ActionContext) -> list[str]:
    from app.candidates.models import DiscoveryHuntMatch
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        match = db.get(DiscoveryHuntMatch, data.match_id)
        resources = [f"discovery-match:{data.match_id}"]
        if match:
            resources.append(f"hunt:{match.hunt_id}")
        return resources


def _common_pool_archive_resources(
    data: CommonPoolArchiveInput,
    ctx: ActionContext,
) -> list[str]:
    resources = ["discoveries:common-pool"]
    if data.hunt_id:
        resources.append(f"hunt:{data.hunt_id}")
    return resources


def _preview_common_pool_archive(
    data: CommonPoolArchiveInput,
    ctx: ActionContext,
) -> dict[str, Any]:
    from app.candidates.discovery import (
        common_pool_count,
        common_pool_linked_candidate_count,
        list_common_pool_profiles,
    )
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        total = common_pool_count(db, hunt_id=data.hunt_id, search=data.search)
        if not total:
            raise ValueError("No visible Common Pool profiles match this selection.")
        linked = common_pool_linked_candidate_count(
            db,
            hunt_id=data.hunt_id,
            search=data.search,
        )
        sample = list_common_pool_profiles(
            db,
            hunt_id=data.hunt_id,
            search=data.search,
            limit=10,
        )
        return {
            "title": "Archive Discoveries Common Pool",
            "summary": (
                f"Archive {total} matching Common Pool profile(s). "
                f"{linked} linked canonical Candidate record(s) will be preserved."
            ),
            "profile_count": total,
            "linked_candidates_preserved": linked,
            "hunt_id": data.hunt_id,
            "search": data.search,
            "sample_names": [profile.full_name or "Unknown candidate" for profile in sample],
            "reversible": True,
            "undo_window_days": 7,
            "affected_resources": _common_pool_archive_resources(data, ctx),
        }


def _pipeline_resources(
    data: PipelineMoveInput | PipelineRemoveInput | PipelineTriageInput,
    ctx: ActionContext,
) -> list[str]:
    from app.hunts.models import HuntCandidate
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        row = db.get(HuntCandidate, data.hunt_candidate_id)
        resources = [f"hunt-candidate:{data.hunt_candidate_id}"]
        if row:
            resources.append(f"hunt:{row.hunt_id}")
            if row.candidate_id:
                resources.append(f"candidate:{row.candidate_id}")
        return resources


def _pipeline_hunt_resources(data: PipelineStageAddInput, ctx: ActionContext) -> list[str]:
    return [f"hunt:{data.hunt_id}"]


def _pipeline_enroll_resources(data: PipelineEnrollInput, ctx: ActionContext) -> list[str]:
    from app.hunts.models import HuntCandidate
    from app.infrastructure.db import SessionFactory

    resources = {f"candidate:{data.candidate_id}", f"hunt:{data.hunt_id}"}
    if data.move_from_other_hunts:
        with SessionFactory() as db:
            for hunt_id in db.scalars(
                select(HuntCandidate.hunt_id).where(HuntCandidate.candidate_id == data.candidate_id)
            ).all():
                resources.add(f"hunt:{hunt_id}")
    return sorted(resources)


def _pipeline_row_snapshot(row) -> dict[str, Any]:
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "hunt_id",
            "candidate_id",
            "stage_id",
            "full_name",
            "email",
            "phone",
            "current_title",
            "current_company",
            "location",
            "linkedin_url",
            "github_url",
            "portfolio_url",
            "match_score",
            "ai_summary",
            "notes",
            "source_platform",
            "source_query",
            "status",
        )
    } | {
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "activities": [
            {
                "id": activity.id,
                "activity_type": activity.activity_type,
                "description": activity.description,
                "metadata_json": activity.metadata_json,
                "created_at": activity.created_at.isoformat() if activity.created_at else None,
            }
            for activity in row.activities or []
        ],
    }


def _hunt_resources(data: HuntArchiveInput, ctx: ActionContext) -> list[str]:
    return [f"hunt:{data.hunt_id}"]


def _hunt_create_resources(data: HuntCreateInput, ctx: ActionContext) -> list[str]:
    return ["hunts:create"]


def _playbook_insight_resources(data: PlaybookInsightAddInput, ctx: ActionContext) -> list[str]:
    return [f"hunt:{data.hunt_id}"] if data.hunt_id else ["playbook:global"]


def _intake_request_resources(data: IntakeRequestCreateInput, ctx: ActionContext) -> list[str]:
    resources = [f"candidate:{data.candidate_id}"]
    if data.hunt_id:
        resources.append(f"hunt:{data.hunt_id}")
    return resources


def _intake_submission_resources(
    data: IntakeSubmissionReviewInput, ctx: ActionContext
) -> list[str]:
    from app.candidates.models import CandidateIntakeRequest, CandidateIntakeSubmission
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        submission = db.get(CandidateIntakeSubmission, data.submission_id)
        if not submission:
            return [f"intake-submission:{data.submission_id}"]
        request = db.get(CandidateIntakeRequest, submission.request_id)
        resources = [
            f"intake-submission:{submission.id}",
            f"intake-request:{submission.request_id}",
        ]
        if request:
            resources.append(f"candidate:{request.candidate_id}")
            if request.hunt_id:
                resources.append(f"hunt:{request.hunt_id}")
        return resources


def _hunt_payload(hunt) -> dict[str, Any]:
    config = hunt.search_config
    return {
        "id": hunt.id,
        "title": hunt.title,
        "description": hunt.description,
        "status": hunt.status,
        "target_role": hunt.target_role,
        "location": hunt.location,
        "salary_range": hunt.salary_range,
        "created_at": hunt.created_at.isoformat() if hunt.created_at else None,
        "updated_at": hunt.updated_at.isoformat() if hunt.updated_at else None,
        "search_config": None
        if not config
        else {
            "id": config.id,
            "keywords": config.keywords,
            "required_skills": config.required_skills,
            "preferred_skills": config.preferred_skills,
            "experience_years_min": config.experience_years_min,
            "experience_years_max": config.experience_years_max,
            "locations": config.locations,
            "industry": config.industry,
            "remote_policy": config.remote_policy,
            "target_platforms": config.target_platforms,
        },
        "stages": [
            {
                "id": stage.id,
                "name": stage.name,
                "position": stage.position,
                "color": stage.color,
                "is_terminal": stage.is_terminal,
            }
            for stage in hunt.stages or []
        ],
        "pipeline_candidates": len(hunt.candidates or []),
    }


def _job_retry_resources(data: JobRetryInput, ctx: ActionContext) -> list[str]:
    from app.jobs import service as jobs

    original = jobs.get_retryable_job(data.job_id)
    resources = [f"job:{data.job_id}"]
    if original["kind"] == "sourcing":
        resources.append("job:sourcing")
    if original["kind"] in {"embedded_ai_install", "embedded_ai_start"}:
        resources.append("ai-runtime:embedded")
    platform = original.get("payload", {}).get("platform")
    if platform:
        resources.append(f"site:{platform}")
        if original["kind"] == "site_connect":
            resources.append("browser:interactive-login")
    if original.get("hunt_id"):
        resources.append(f"hunt:{original['hunt_id']}")
    match_id = original.get("payload", {}).get("match_id")
    if match_id:
        resources.append(f"discovery-match:{int(match_id)}")
    return resources


def _job_control_resources(data: JobCancelInput, ctx: ActionContext) -> list[str]:
    from app.jobs import service as jobs

    row = jobs.get_job_row(data.job_id)
    if not row:
        raise ValueError("Background job not found.")
    resources = [f"job:{data.job_id}"]
    if row.kind == "sourcing":
        resources.append("job:sourcing")
    if row.kind in {"embedded_ai_install", "embedded_ai_start"}:
        resources.append("ai-runtime:embedded")
    if row.hunt_id:
        resources.append(f"hunt:{row.hunt_id}")
    match_id = jobs.serialize_job(row).get("payload", {}).get("match_id")
    if match_id:
        resources.append(f"discovery-match:{int(match_id)}")
    platform = jobs.serialize_job(row).get("payload", {}).get("platform")
    if platform:
        resources.append(f"site:{platform}")
    return resources


def _job_payload(row) -> dict[str, Any]:
    from app.jobs.service import serialize_job

    item = serialize_job(row)
    phase = str(item.get("phase") or "").strip().lower() or None
    cancellable = (
        item["status"] == "running"
        and item["kind"] in {"sourcing", "profile_enrichment", "site_connect", "site_verify"}
        and not (item["kind"] == "profile_enrichment" and phase == "applying")
    )
    return {
        "id": item["id"],
        "kind": item["kind"],
        "status": item["status"],
        "hunt_id": item.get("hunt_id"),
        "hunt_title": item.get("hunt_title"),
        "label": item["label"],
        "message": item["message"],
        "phase": phase,
        "platform": item.get("platform") or item.get("payload", {}).get("platform"),
        "window_open": bool(item.get("window_open")),
        "ready_for_save": bool(item.get("ready_for_save")),
        "browser_channel": item.get("browser_channel"),
        "scanned": item["scanned"],
        "added": item["added"],
        "skipped": item["skipped"],
        "attempt": item["attempt"],
        "parent_job_id": item.get("parent_job_id"),
        "retryable": bool(
            item["retryable"] and item["status"] in {"cancelled", "error", "interrupted"}
        ),
        "cancellable": cancellable,
        "started_at": item.get("started_at"),
        "heartbeat_at": item.get("heartbeat_at"),
        "finished_at": item.get("finished_at"),
        "elapsed_sec": item["elapsed_sec"],
        "error": item.get("error"),
    }


def _preview_hunt_archive(data: HuntArchiveInput, ctx: ActionContext) -> dict[str, Any]:
    from sqlalchemy import func

    from app.hunts.models import HuntCandidate, TalentHunt
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        hunt = db.get(TalentHunt, data.hunt_id)
        if not hunt:
            raise ValueError("Hunt not found.")
        if hunt.status == "Archived":
            raise ValueError("Hunt is already archived.")
        count = int(
            db.scalar(
                select(func.count())
                .select_from(HuntCandidate)
                .where(HuntCandidate.hunt_id == hunt.id)
            )
            or 0
        )
        return {
            "title": "Archive Talent Hunt",
            "summary": f"Archive '{hunt.title}' and hide it from active views.",
            "hunt_id": hunt.id,
            "hunt_title": hunt.title,
            "current_status": hunt.status,
            "pipeline_candidates": count,
            "reversible": True,
            "undo_window_days": 7,
            "affected_resources": [f"hunt:{hunt.id}"],
        }


@register_action(
    "actions.undo",
    description="Undo one reversible action from the seven-day history.",
    input_model=ActionUndoInput,
    resource_resolver=_undo_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="undo_recent_action",
)
def undo_history_action(data: ActionUndoInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import serialize_action, undo_action
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        item = undo_action(db, data.action_id)
        return {
            "status": "success",
            "message": f"Undid action #{item.id}: {item.summary}",
            "action": serialize_action(item, db),
        }


@register_action(
    "candidates.list",
    description="List and search canonical Candidate records using the same source as the Candidates page.",
    input_model=CandidateListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="list_candidate_records",
)
def list_candidates_action(data: CandidateListInput, ctx: ActionContext) -> dict[str, Any]:
    from app.candidates.service import list_candidates
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidates = list_candidates(
            db,
            search=data.search,
            status=data.status,
            skip=data.offset,
            limit=data.limit,
        )
        return {
            "status": "success",
            "count": len(candidates),
            "offset": data.offset,
            "limit": data.limit,
            "candidates": [_candidate_summary(candidate) for candidate in candidates],
        }


@register_action(
    "candidates.create",
    description="Create one canonical Candidate, optionally enroll them in a Hunt, with conflict detection and safe Undo.",
    input_model=CandidateCreateInput,
    resource_resolver=_candidate_create_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="add_candidate_to_database",
)
def create_candidate_action(data: CandidateCreateInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.candidates.duplicates import find_candidate_identity_conflict
    from app.candidates.service import (
        create_candidate,
        delete_candidate,
        get_candidate,
        serialize_candidate_profile_state,
    )
    from app.hunts.models import TalentHunt
    from app.hunts.pipeline import add_candidate_to_hunt
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        if data.hunt_id and not db.get(TalentHunt, data.hunt_id):
            raise ValueError("Hunt not found.")
        conflict = find_candidate_identity_conflict(
            db,
            full_name=data.full_name,
            email=data.email,
            phone=data.phone,
            location=data.location,
            current_company=data.current_company,
            linkedin_url=data.linkedin_url,
            github_url=data.github_url,
            portfolio_url=data.portfolio_url,
        )
        if conflict:
            existing, reasons = conflict
            return {
                "status": "conflict",
                "changed": False,
                "candidate_id": existing.id,
                "candidate_name": existing.full_name,
                "reasons": reasons,
                "message": "A likely matching Candidate already exists. Review or merge instead of creating another record.",
            }

        candidate = create_candidate(
            db,
            full_name=data.full_name,
            email=data.email,
            phone=data.phone,
            location=data.location,
            current_title=data.current_title,
            current_company=data.current_company,
            experience_years=data.experience_years,
            linkedin_url=data.linkedin_url,
            github_url=data.github_url,
            portfolio_url=data.portfolio_url,
            status=data.status or ("Sourced" if data.hunt_id else "Active"),
            headline=data.headline,
            summary=data.summary,
            resume_text=data.resume_text,
            skills=data.skills or None,
            tags=data.tags or None,
        )
        if not candidate:
            raise RuntimeError("Candidate creation failed.")

        hunt_candidate = None
        try:
            if data.hunt_id:
                hunt_candidate = add_candidate_to_hunt(
                    db,
                    hunt_id=data.hunt_id,
                    candidate_id=candidate.id,
                    full_name=candidate.full_name,
                    email=candidate.email,
                    phone=candidate.phone,
                    current_title=candidate.current_title,
                    current_company=candidate.current_company,
                    location=candidate.location,
                    linkedin_url=candidate.linkedin_url,
                    github_url=candidate.github_url,
                    source_platform="manual",
                )
            candidate = get_candidate(db, candidate.id)
            initial_state = serialize_candidate_profile_state(candidate)
            history = record_action(
                db,
                action_type="create_candidate",
                summary=f"Created candidate {candidate.full_name}",
                actor_type=_history_actor(ctx),
                session_id=ctx.session_id,
                payload={
                    "candidate_id": candidate.id,
                    "candidate_ids": [candidate.id],
                    "hunt_id": data.hunt_id,
                    "hunt_candidate_id": hunt_candidate.id if hunt_candidate else None,
                },
                undo_payload={
                    "candidate_id": candidate.id,
                    "initial_state": initial_state,
                    "initial_tag_ids": [tag.id for tag in candidate.tags or []],
                    "hunt_candidate_id": hunt_candidate.id if hunt_candidate else None,
                    "hunt_activity_ids": [row.id for row in (hunt_candidate.activities or [])]
                    if hunt_candidate
                    else [],
                },
            )
        except Exception:
            delete_candidate(db, candidate.id)
            raise
        return {
            "status": "success",
            "changed": True,
            "candidate_id": candidate.id,
            "candidate_name": candidate.full_name,
            "hunt_id": data.hunt_id,
            "hunt_candidate_id": hunt_candidate.id if hunt_candidate else None,
            "action_id": history.id,
            "undoable": True,
            "undo_window_days": 7,
        }


@register_action(
    "candidates.get",
    description="Read one canonical Candidate record with profile evidence.",
    input_model=CandidateGetInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_candidate_record",
)
def get_candidate_action(data: CandidateGetInput, ctx: ActionContext) -> dict[str, Any]:
    from app.candidates.service import get_candidate
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = get_candidate(db, data.candidate_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        return {"status": "success", "candidate": _candidate_payload(candidate)}


@register_action(
    "candidates.duplicates.list",
    description="Find likely duplicate canonical Candidate records using conservative identity signals.",
    input_model=CandidateDuplicateListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="find_candidate_duplicates",
)
def list_candidate_duplicates_action(
    data: CandidateDuplicateListInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.candidates.duplicates import find_candidate_duplicates
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        duplicates = find_candidate_duplicates(
            db,
            candidate_id=data.candidate_id,
            include_archived=data.include_archived,
            limit=data.limit,
        )
        return {"status": "success", "count": len(duplicates), "duplicates": duplicates}


@register_action(
    "candidates.merge",
    description="Merge a duplicate Candidate into a chosen survivor after a trusted immutable preview.",
    preview_handler=_preview_candidate_merge,
    input_model=CandidateMergeInput,
    resource_resolver=_candidate_merge_resources,
    requires_approval=True,
    classification="mutation",
    risk_level="R3",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="merge_candidate_records",
)
def merge_candidates_action(data: CandidateMergeInput, ctx: ActionContext) -> dict[str, Any]:
    from app.candidates.duplicates import merge_candidate_records
    from app.candidates.service import _reindex_candidate, get_candidate
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        history, preview = merge_candidate_records(
            db,
            survivor_id=data.survivor_id,
            source_id=data.source_id,
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
        )
        survivor = get_candidate(db, data.survivor_id)
        source = get_candidate(db, data.source_id)
        if survivor:
            _reindex_candidate(db, survivor)
        if source:
            _reindex_candidate(db, source)
        return {
            "status": "success",
            "survivor_id": data.survivor_id,
            "source_id": data.source_id,
            "source_status": "Archived",
            "action_id": history.id,
            "undoable": True,
            "undo_window_days": 7,
            "preview": preview,
        }


@register_action(
    "candidates.archive",
    description="Archive one canonical Candidate without deleting its profile, with seven-day undo.",
    input_model=CandidateArchiveInput,
    resource_resolver=_candidate_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="archive_candidate_record",
)
def archive_candidate_action(data: CandidateArchiveInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.candidates.service import get_candidate
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = get_candidate(db, data.candidate_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        if candidate.status == "Archived":
            return {"status": "success", "changed": False, "candidate_id": candidate.id}
        previous_status = candidate.status
        candidate.status = "Archived"
        history = record_action(
            db,
            action_type="archive_candidates",
            summary=f"Archived candidate {candidate.full_name}",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={"candidate_id": candidate.id, "candidate_ids": [candidate.id]},
            undo_payload={"previous_statuses": {str(candidate.id): previous_status}},
        )
        return {
            "status": "success",
            "changed": True,
            "candidate_id": candidate.id,
            "candidate_name": candidate.full_name,
            "action_id": history.id,
            "undoable": True,
            "undo_window_days": 7,
        }


@register_action(
    "candidates.tags.add",
    description="Add one tag to a canonical Candidate with seven-day undo.",
    input_model=CandidateTagAddInput,
    resource_resolver=_candidate_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="add_candidate_tag",
)
def add_candidate_tag_action(data: CandidateTagAddInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.candidates.models import CandidateTag
    from app.candidates.service import add_candidate_tag, get_candidate
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = get_candidate(db, data.candidate_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        existing = db.scalar(
            select(CandidateTag).where(
                CandidateTag.candidate_id == data.candidate_id,
                CandidateTag.tag_name.ilike(data.tag_name),
            )
        )
        if existing:
            return {"status": "success", "changed": False, "tag_id": existing.id}
        tag = add_candidate_tag(db, data.candidate_id, data.tag_name, data.color)
        if not tag:
            raise RuntimeError("Candidate tag could not be added.")
        history = record_action(
            db,
            action_type="add_candidate_tag",
            summary=f"Added tag '{tag.tag_name}' to {candidate.full_name}",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={"candidate_id": candidate.id, "tag_id": tag.id, "tag_name": tag.tag_name},
            undo_payload={"candidate_id": candidate.id, "tag_id": tag.id},
        )
        return {
            "status": "success",
            "changed": True,
            "tag_id": tag.id,
            "action_id": history.id,
            "undoable": True,
        }


@register_action(
    "candidates.tags.remove",
    description="Remove one Candidate tag with seven-day undo.",
    input_model=CandidateTagRemoveInput,
    resource_resolver=_candidate_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="remove_candidate_tag",
)
def remove_candidate_tag_action(
    data: CandidateTagRemoveInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.candidates.models import CandidateTag
    from app.candidates.service import get_candidate, remove_candidate_tag
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = get_candidate(db, data.candidate_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        tag = db.scalar(
            select(CandidateTag).where(
                CandidateTag.id == data.tag_id,
                CandidateTag.candidate_id == data.candidate_id,
            )
        )
        if not tag:
            raise ValueError("Candidate tag not found.")
        previous = {"candidate_id": candidate.id, "tag_name": tag.tag_name, "color": tag.color}
        if not remove_candidate_tag(db, data.candidate_id, data.tag_id):
            raise RuntimeError("Candidate tag could not be removed.")
        history = record_action(
            db,
            action_type="remove_candidate_tag",
            summary=f"Removed tag '{tag.tag_name}' from {candidate.full_name}",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={"candidate_id": candidate.id, "tag_id": data.tag_id, "tag_name": tag.tag_name},
            undo_payload=previous,
        )
        return {"status": "success", "changed": True, "action_id": history.id, "undoable": True}


@register_action(
    "candidates.notes.add",
    description="Add a recruiter note to one canonical Candidate with seven-day undo.",
    input_model=CandidateNoteAddInput,
    resource_resolver=_candidate_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="add_candidate_note",
)
def add_candidate_note_action(data: CandidateNoteAddInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.candidates.service import add_candidate_note, get_candidate
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = get_candidate(db, data.candidate_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        note = add_candidate_note(db, candidate.id, data.content, data.author)
        if not note:
            raise RuntimeError("Candidate note could not be added.")
        history = record_action(
            db,
            action_type="add_candidate_note",
            summary=f"Added a note to {candidate.full_name}",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={"candidate_id": candidate.id, "note_id": note.id},
            undo_payload={"candidate_id": candidate.id, "note_id": note.id},
        )
        return {
            "status": "success",
            "changed": True,
            "note_id": note.id,
            "action_id": history.id,
            "undoable": True,
        }


@register_action(
    "candidates.experiences.save",
    description="Add or edit one Candidate work-experience row with seven-day undo.",
    input_model=CandidateExperienceSaveInput,
    resource_resolver=_candidate_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="save_candidate_experience",
)
def save_candidate_experience_action(
    data: CandidateExperienceSaveInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.candidates.models import CandidateExperience
    from app.candidates.service import (
        _reindex_candidate,
        get_candidate,
        serialize_candidate_profile_state,
    )
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = get_candidate(db, data.candidate_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        before = serialize_candidate_profile_state(candidate)
        row = db.get(CandidateExperience, data.experience_id) if data.experience_id else None
        if data.experience_id and (not row or row.candidate_id != candidate.id):
            raise ValueError("Candidate experience not found.")
        created = row is None
        if row is None:
            row = CandidateExperience(
                candidate_id=candidate.id, company=data.company, title=data.title
            )
            db.add(row)
        values = data.model_dump(exclude={"candidate_id", "experience_id", "skills"})
        for field, value in values.items():
            setattr(row, field, value)
        row.skills_json = json.dumps([skill.strip() for skill in data.skills if skill.strip()])
        _refresh_candidate_timeline(db, candidate)
        history = _record_candidate_profile_change(
            db,
            candidate=candidate,
            before=before,
            summary=f"{'Added' if created else 'Updated'} experience for {candidate.full_name}",
            payload={"experience_id": row.id, "operation": "add" if created else "update"},
            ctx=ctx,
        )
        _reindex_candidate(db, get_candidate(db, candidate.id))
        return {
            "status": "success",
            "changed": True,
            "experience_id": row.id,
            "action_id": history.id,
            "undoable": True,
        }


@register_action(
    "candidates.experiences.remove",
    description="Remove one Candidate work-experience row with seven-day undo.",
    input_model=CandidateExperienceRemoveInput,
    resource_resolver=_candidate_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="remove_candidate_experience",
)
def remove_candidate_experience_action(
    data: CandidateExperienceRemoveInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.candidates.models import CandidateExperience
    from app.candidates.service import (
        _reindex_candidate,
        get_candidate,
        serialize_candidate_profile_state,
    )
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = get_candidate(db, data.candidate_id)
        row = db.get(CandidateExperience, data.experience_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        if not row or row.candidate_id != candidate.id:
            raise ValueError("Candidate experience not found.")
        before = serialize_candidate_profile_state(candidate)
        label = f"{row.title} at {row.company}"
        db.delete(row)
        _refresh_candidate_timeline(db, candidate)
        history = _record_candidate_profile_change(
            db,
            candidate=candidate,
            before=before,
            summary=f"Removed experience '{label}' from {candidate.full_name}",
            payload={"experience_id": data.experience_id, "operation": "remove"},
            ctx=ctx,
        )
        _reindex_candidate(db, get_candidate(db, candidate.id))
        return {"status": "success", "changed": True, "action_id": history.id, "undoable": True}


@register_action(
    "candidates.educations.save",
    description="Add or edit one Candidate education row with seven-day undo.",
    input_model=CandidateEducationSaveInput,
    resource_resolver=_candidate_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="save_candidate_education",
)
def save_candidate_education_action(
    data: CandidateEducationSaveInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.candidates.models import CandidateEducation
    from app.candidates.service import get_candidate, serialize_candidate_profile_state
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = get_candidate(db, data.candidate_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        before = serialize_candidate_profile_state(candidate)
        row = db.get(CandidateEducation, data.education_id) if data.education_id else None
        if data.education_id and (not row or row.candidate_id != candidate.id):
            raise ValueError("Candidate education record not found.")
        created = row is None
        if row is None:
            row = CandidateEducation(candidate_id=candidate.id, institution=data.institution)
            db.add(row)
        for field, value in data.model_dump(exclude={"candidate_id", "education_id"}).items():
            setattr(row, field, value)
        db.flush()
        history = _record_candidate_profile_change(
            db,
            candidate=candidate,
            before=before,
            summary=f"{'Added' if created else 'Updated'} education for {candidate.full_name}",
            payload={"education_id": row.id, "operation": "add" if created else "update"},
            ctx=ctx,
        )
        return {
            "status": "success",
            "changed": True,
            "education_id": row.id,
            "action_id": history.id,
            "undoable": True,
        }


@register_action(
    "candidates.educations.remove",
    description="Remove one Candidate education row with seven-day undo.",
    input_model=CandidateEducationRemoveInput,
    resource_resolver=_candidate_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="remove_candidate_education",
)
def remove_candidate_education_action(
    data: CandidateEducationRemoveInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.candidates.models import CandidateEducation
    from app.candidates.service import get_candidate, serialize_candidate_profile_state
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = get_candidate(db, data.candidate_id)
        row = db.get(CandidateEducation, data.education_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        if not row or row.candidate_id != candidate.id:
            raise ValueError("Candidate education record not found.")
        before = serialize_candidate_profile_state(candidate)
        institution = row.institution
        db.delete(row)
        history = _record_candidate_profile_change(
            db,
            candidate=candidate,
            before=before,
            summary=f"Removed education '{institution}' from {candidate.full_name}",
            payload={"education_id": data.education_id, "operation": "remove"},
            ctx=ctx,
        )
        return {"status": "success", "changed": True, "action_id": history.id, "undoable": True}


@register_action(
    "candidates.profile.apply",
    description="Merge or replace reviewed structured profile sections with exact seven-day undo.",
    input_model=CandidateProfileApplyInput,
    resource_resolver=_candidate_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="apply_candidate_profile_sections",
)
def apply_candidate_profile_action(
    data: CandidateProfileApplyInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.candidates.service import (
        get_candidate,
        replace_or_merge_profile_sections,
        serialize_candidate_profile_state,
    )
    from app.infrastructure.db import SessionFactory

    changes = data.model_dump(exclude={"candidate_id"}, exclude_unset=True)
    if set(changes) <= {"mode"}:
        raise ValueError("No profile sections were provided to apply.")
    with SessionFactory() as db:
        candidate = get_candidate(db, data.candidate_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        before = serialize_candidate_profile_state(candidate)
        updated = replace_or_merge_profile_sections(
            db,
            data.candidate_id,
            record_history=False,
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            **changes,
        )
        if not updated:
            raise RuntimeError("Candidate profile sections could not be applied.")
        after = serialize_candidate_profile_state(get_candidate(db, data.candidate_id))
        if before == after:
            return {"status": "success", "changed": False, "candidate": _candidate_payload(updated)}
        history = _record_candidate_profile_change(
            db,
            candidate=updated,
            before=before,
            summary=f"Applied {data.mode} profile sections for {updated.full_name}",
            payload={"mode": data.mode, "sections": sorted(changes)},
            ctx=ctx,
        )
        return {
            "status": "success",
            "changed": True,
            "candidate": _candidate_payload(get_candidate(db, data.candidate_id)),
            "action_id": history.id,
            "undoable": True,
        }


@register_action(
    "candidates.rogue.set",
    description="Mark or clear a Candidate as Rogue, with Playbook-aware seven-day undo.",
    input_model=CandidateRogueSetInput,
    resource_resolver=_candidate_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="set_candidate_rogue_status",
)
def set_candidate_rogue_action(data: CandidateRogueSetInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.candidates.models import CandidateTag
    from app.candidates.service import get_candidate
    from app.hunts.playbook import ROGUE_TAG, clear_candidate_rogue, mark_candidate_rogue
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = get_candidate(db, data.candidate_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        tags = list(
            db.scalars(
                select(CandidateTag).where(
                    CandidateTag.candidate_id == candidate.id,
                    CandidateTag.tag_name == ROGUE_TAG,
                )
            ).all()
        )
        if bool(tags) == data.enabled:
            return {
                "status": "success",
                "changed": False,
                "candidate_id": candidate.id,
                "rogue": data.enabled,
            }
        previous_tags = [{"tag_name": tag.tag_name, "color": tag.color} for tag in tags]
        playbook_entry_id = None
        if data.enabled:
            result = mark_candidate_rogue(
                db, candidate.id, note=data.note, author_name=data.author.strip() or "Recruiter"
            )
            if result.get("status") != "success":
                raise RuntimeError(result.get("error") or "Candidate could not be marked Rogue.")
            playbook_entry_id = result.get("playbook_entry_id")
        else:
            clear_candidate_rogue(db, candidate.id)
        try:
            history = record_action(
                db,
                action_type="set_candidate_rogue",
                summary=f"{'Marked' if data.enabled else 'Cleared'} Rogue status for {candidate.full_name}",
                actor_type=_history_actor(ctx),
                session_id=ctx.session_id,
                payload={"candidate_id": candidate.id, "enabled": data.enabled},
                undo_payload={
                    "candidate_id": candidate.id,
                    "previous_tags": previous_tags,
                    "playbook_entry_id": playbook_entry_id,
                },
            )
        except Exception:
            from app.hunts.models import PlaybookEntry

            for tag in list(
                db.scalars(
                    select(CandidateTag).where(
                        CandidateTag.candidate_id == candidate.id,
                        CandidateTag.tag_name == ROGUE_TAG,
                    )
                ).all()
            ):
                db.delete(tag)
            for tag in previous_tags:
                db.add(
                    CandidateTag(
                        candidate_id=candidate.id,
                        tag_name=tag["tag_name"],
                        color=tag.get("color"),
                    )
                )
            if playbook_entry_id:
                entry = db.get(PlaybookEntry, int(playbook_entry_id))
                if entry:
                    db.delete(entry)
            db.commit()
            raise
        return {
            "status": "success",
            "changed": True,
            "candidate_id": candidate.id,
            "rogue": data.enabled,
            "action_id": history.id,
            "undoable": True,
        }


@register_action(
    "candidates.update",
    description="Update recruiter-editable Candidate fields with seven-day undo.",
    input_model=CandidateUpdateInput,
    resource_resolver=_candidate_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="update_candidate_record",
)
def update_candidate_action(data: CandidateUpdateInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.candidates.service import (
        _reindex_candidate,
        get_candidate,
        restore_candidate_profile_state,
        serialize_candidate_profile_state,
        update_candidate,
    )
    from app.infrastructure.db import SessionFactory

    changes = data.model_dump(exclude_unset=True)
    changes.pop("candidate_id", None)
    if not changes:
        raise ValueError("No Candidate fields were provided to update.")

    with SessionFactory() as db:
        candidate = get_candidate(db, data.candidate_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        before = serialize_candidate_profile_state(candidate)
        updated = update_candidate(db, data.candidate_id, **changes)
        if not updated:
            raise RuntimeError("Candidate update failed.")
        after = serialize_candidate_profile_state(get_candidate(db, data.candidate_id))
        if before == after:
            return {
                "status": "success",
                "changed": False,
                "candidate": _candidate_payload(updated),
            }
        try:
            history = record_action(
                db,
                action_type="update_candidate_profile",
                summary=f"Updated candidate {updated.full_name}",
                actor_type=_history_actor(ctx),
                session_id=ctx.session_id,
                payload={"candidate_id": updated.id, "fields": sorted(changes)},
                undo_payload={"candidate_state": before},
            )
        except Exception:
            restored = restore_candidate_profile_state(db, before)
            db.commit()
            if restored:
                _reindex_candidate(db, restored)
            raise
        return {
            "status": "success",
            "changed": True,
            "action_id": history.id,
            "undoable": True,
            "candidate": _candidate_payload(get_candidate(db, data.candidate_id)),
        }


@register_action(
    "discoveries.list",
    description="List Hunt-specific discovery matches and their lightweight evidence.",
    input_model=DiscoveryListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="list_discovery_records",
)
def list_discoveries_action(data: DiscoveryListInput, ctx: ActionContext) -> dict[str, Any]:
    from app.candidates.discovery import list_discoveries
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        matches = list_discoveries(
            db,
            hunt_id=data.hunt_id,
            statuses=data.statuses,
            limit=data.limit,
        )
        return {
            "status": "success",
            "count": len(matches),
            "discoveries": [_discovery_payload(match) for match in matches],
        }


@register_action(
    "discoveries.get",
    description="Read one Hunt discovery with its stored source evidence and review state.",
    input_model=DiscoveryGetInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_discovery_record",
)
def get_discovery_action(data: DiscoveryGetInput, ctx: ActionContext) -> dict[str, Any]:
    from app.candidates.models import DiscoveryHuntMatch
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        match = db.scalar(
            select(DiscoveryHuntMatch)
            .options(
                selectinload(DiscoveryHuntMatch.profile),
                selectinload(DiscoveryHuntMatch.hunt),
            )
            .where(DiscoveryHuntMatch.id == data.match_id)
        )
        if not match:
            raise ValueError("Discovery match not found.")
        return {"status": "success", "discovery": _discovery_payload(match)}


@register_action(
    "discoveries.common_pool.list",
    description="Search the retained Common Pool, including filtered and rejected identities.",
    input_model=CommonPoolListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="list_common_pool",
)
def list_common_pool_action(data: CommonPoolListInput, ctx: ActionContext) -> dict[str, Any]:
    from app.candidates.discovery import common_pool_count, list_common_pool_profiles
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        profiles = list_common_pool_profiles(
            db,
            hunt_id=data.hunt_id,
            search=data.search,
            offset=data.offset,
            limit=data.limit,
        )
        return {
            "status": "success",
            "count": len(profiles),
            "total": common_pool_count(db, hunt_id=data.hunt_id, search=data.search),
            "offset": data.offset,
            "limit": data.limit,
            "profiles": [_common_pool_payload(profile) for profile in profiles],
        }


@register_action(
    "discoveries.common_pool.archive",
    description=(
        "Archive, clear, or delete matching profiles from the Discoveries Common Pool only. "
        "Canonical Candidate records are preserved. This creates a trusted confirmation preview "
        "and can be undone for seven days. Omit Hunt and search to archive the whole visible pool."
    ),
    preview_handler=_preview_common_pool_archive,
    input_model=CommonPoolArchiveInput,
    resource_resolver=_common_pool_archive_resources,
    requires_approval=True,
    classification="mutation",
    risk_level="R3",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="archive_discoveries_common_pool",
)
def archive_common_pool_action(
    data: CommonPoolArchiveInput,
    ctx: ActionContext,
) -> dict[str, Any]:
    from app.candidates.discovery import archive_common_pool_profiles
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        return archive_common_pool_profiles(
            db,
            hunt_id=data.hunt_id,
            search=data.search,
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
        )


@register_action(
    "discoveries.approve",
    description="Approve one discovery and start its deep profile scan.",
    input_model=DiscoveryDecisionInput,
    resource_resolver=_discovery_resources,
    classification="ai_task",
    risk_level="R2",
    required_scopes=("write", "compute"),
    copilot_enabled=True,
    copilot_tool_name="approve_discovery",
)
def approve_discovery_action(data: DiscoveryDecisionInput, ctx: ActionContext) -> dict[str, Any]:
    from app.candidates.discovery import utcnow
    from app.candidates.models import DiscoveryHuntMatch
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        match = db.scalar(
            select(DiscoveryHuntMatch)
            .options(selectinload(DiscoveryHuntMatch.profile))
            .where(DiscoveryHuntMatch.id == data.match_id)
        )
        if not match:
            raise ValueError("Discovery match not found.")
        if match.status == "imported":
            return {
                "status": "success",
                "started": False,
                "message": "Discovery is already imported.",
                "candidate_id": match.profile.candidate_id,
            }
        if match.status in {"approved", "enriching"}:
            return {
                "status": "success",
                "started": False,
                "message": "The deep scan is already running.",
            }
        name = match.profile.full_name or "candidate"
        match.status = "approved"
        match.approved_at = utcnow()
        match.scan_error = None
        db.commit()

    from app.jobs.runner import start_profile_enrichment

    started = start_profile_enrichment(
        data.match_id,
        actor_type=_history_actor(ctx),
        session_id=ctx.session_id,
    )
    return {
        "status": "success",
        "started": True,
        "job_id": started["job_id"],
        "match_id": data.match_id,
        "candidate_name": name,
        "message": f"Deep scan started for {name}.",
    }


@register_action(
    "discoveries.reject",
    description="Reject one Hunt discovery while retaining it in the Common Pool.",
    input_model=DiscoveryDecisionInput,
    resource_resolver=_discovery_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="reject_discovery",
)
def reject_discovery_action(data: DiscoveryDecisionInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.candidates.models import DiscoveryHuntMatch
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        match = db.scalar(
            select(DiscoveryHuntMatch)
            .options(selectinload(DiscoveryHuntMatch.profile))
            .where(DiscoveryHuntMatch.id == data.match_id)
        )
        if not match:
            raise ValueError("Discovery match not found.")
        if match.status in {"imported", "enriching"}:
            raise ValueError(f"A discovery in status '{match.status}' cannot be rejected.")
        if match.status == "rejected":
            return {"status": "success", "changed": False, "match_id": match.id}
        previous = {
            "match_id": match.id,
            "status": match.status,
            "scan_error": match.scan_error,
            "rejection_reason": match.rejection_reason,
            "approved_at": match.approved_at.isoformat() if match.approved_at else None,
        }
        name = match.profile.full_name or "candidate"
        match.status = "rejected"
        match.scan_error = None
        match.rejection_reason = (data.reason or "Recruiter passed").strip()
        history = record_action(
            db,
            action_type="reject_discovered_profile",
            summary=f"Rejected discovery {name}",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={"match_id": match.id, "reason": match.rejection_reason},
            undo_payload=previous,
        )
        return {
            "status": "success",
            "changed": True,
            "match_id": match.id,
            "candidate_name": name,
            "action_id": history.id,
            "undoable": True,
        }


@register_action(
    "pipeline.get",
    description="Read one Hunt Pipeline board from the canonical Pipeline source.",
    input_model=PipelineGetInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_pipeline_board",
)
def get_pipeline_action(data: PipelineGetInput, ctx: ActionContext) -> dict[str, Any]:
    from app.hunts.pipeline import get_pipeline_data
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        board = get_pipeline_data(db, data.hunt_id)
        if not board:
            raise ValueError("Talent Hunt not found.")
        return {
            "status": "success",
            "hunt_id": board["hunt_id"],
            "hunt_title": board["hunt_title"],
            "target_role": board["target_role"],
            "hunt_status": board["status"],
            "total_candidates": board["total_candidates"],
            "stages": [
                {
                    "id": stage["id"],
                    "name": stage["name"],
                    "position": stage["position"],
                    "color": stage["color"],
                    "is_terminal": stage["is_terminal"],
                    "count": stage["count"],
                    "candidates": [
                        {
                            "hunt_candidate_id": row.id,
                            "candidate_id": row.candidate_id,
                            "full_name": row.full_name,
                            "current_title": row.current_title,
                            "current_company": row.current_company,
                            "location": row.location,
                            "match_score": row.match_score,
                            "status": row.status,
                            "source_platform": row.source_platform,
                        }
                        for row in stage["candidates"]
                    ],
                }
                for stage in board["stages"]
            ],
        }


@register_action(
    "pipeline.move",
    description="Move one Hunt enrollment to another stage with seven-day undo.",
    input_model=PipelineMoveInput,
    resource_resolver=_pipeline_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="move_pipeline_by_id",
)
def move_pipeline_action(data: PipelineMoveInput, ctx: ActionContext) -> dict[str, Any]:
    from app.hunts.models import HuntCandidate, HuntStage
    from app.hunts.pipeline import move_candidate_stage
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = db.get(HuntCandidate, data.hunt_candidate_id)
        stage = db.get(HuntStage, data.stage_id)
        if not candidate:
            raise ValueError("Pipeline candidate not found.")
        if not stage or stage.hunt_id != candidate.hunt_id:
            raise ValueError("Target stage does not belong to this Candidate's Hunt.")
        old_stage_id = candidate.stage_id
        moved = move_candidate_stage(
            db,
            data.hunt_candidate_id,
            data.stage_id,
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
        )
        if not moved:
            raise RuntimeError("Pipeline move failed.")
        return {
            "status": "success",
            "changed": old_stage_id != data.stage_id,
            "hunt_id": moved.hunt_id,
            "hunt_candidate_id": moved.id,
            "candidate_name": moved.full_name,
            "stage_id": stage.id,
            "stage": stage.name,
            "undoable": old_stage_id != data.stage_id,
        }


@register_action(
    "pipeline.enroll",
    description="Enroll an existing canonical Candidate in a Hunt, optionally moving from other Hunts, with seven-day undo.",
    input_model=PipelineEnrollInput,
    resource_resolver=_pipeline_enroll_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="enroll_candidate_in_hunt",
)
def enroll_pipeline_action(data: PipelineEnrollInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.candidates.models import Candidate, CandidateTag
    from app.hunts.models import HuntCandidate, TalentHunt
    from app.hunts.pipeline import add_candidate_to_hunt
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = db.get(Candidate, data.candidate_id)
        hunt = db.get(TalentHunt, data.hunt_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        if not hunt:
            raise ValueError("Talent Hunt not found.")
        target = db.scalar(
            select(HuntCandidate).where(
                HuntCandidate.hunt_id == hunt.id,
                HuntCandidate.candidate_id == candidate.id,
            )
        )
        removed_rows = []
        removed_tags = []
        others = []
        tags_to_remove = []
        if data.move_from_other_hunts:
            others = list(
                db.scalars(
                    select(HuntCandidate).where(
                        HuntCandidate.candidate_id == candidate.id,
                        HuntCandidate.hunt_id != hunt.id,
                    )
                ).all()
            )
            removed_rows = [_pipeline_row_snapshot(row) for row in others]
            keep_tag = f"Hunt: {hunt.title}".lower()
            tags = list(
                db.scalars(
                    select(CandidateTag).where(
                        CandidateTag.candidate_id == candidate.id,
                        CandidateTag.tag_name.like("Hunt:%"),
                    )
                ).all()
            )
            for tag in tags:
                if (tag.tag_name or "").lower() != keep_tag:
                    removed_tags.append(
                        {
                            "id": tag.id,
                            "tag_name": tag.tag_name,
                            "color": tag.color,
                            "candidate_id": tag.candidate_id,
                        }
                    )
                    tags_to_remove.append(tag)
        created_enrollment = target is None
        if target is None:
            target = add_candidate_to_hunt(
                db,
                hunt_id=hunt.id,
                candidate_id=candidate.id,
                full_name=candidate.full_name,
                email=candidate.email,
                phone=candidate.phone,
                current_title=candidate.current_title,
                current_company=candidate.current_company,
                location=candidate.location,
                linkedin_url=candidate.linkedin_url,
                github_url=candidate.github_url,
                ai_summary=(data.note or "").strip() or f'Assigned to hunt "{hunt.title}".',
                source_platform="manual" if ctx.actor_type != "agent" else "copilot",
                commit=False,
            )
        tag_name = f"Hunt: {hunt.title}"
        target_tag = db.scalar(
            select(CandidateTag).where(
                CandidateTag.candidate_id == candidate.id,
                CandidateTag.tag_name == tag_name,
            )
        )
        created_tag_id = None
        if not target_tag:
            target_tag = CandidateTag(candidate_id=candidate.id, tag_name=tag_name, color="#19d3c5")
            db.add(target_tag)
            db.flush()
            created_tag_id = target_tag.id
        for row in others:
            db.delete(row)
        for tag in tags_to_remove:
            db.delete(tag)
        if others or tags_to_remove:
            db.flush()
        changed = (
            created_enrollment
            or bool(removed_rows)
            or bool(removed_tags)
            or created_tag_id is not None
        )
        if not changed:
            return {
                "status": "success",
                "changed": False,
                "candidate_id": candidate.id,
                "hunt_id": hunt.id,
                "hunt_candidate_id": target.id,
                "message": "Candidate is already enrolled in this Hunt.",
                "undoable": False,
            }
        history = record_action(
            db,
            action_type="enroll_pipeline_candidate",
            summary=f"{'Moved' if data.move_from_other_hunts else 'Added'} {candidate.full_name} to {hunt.title}",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={
                "candidate_id": candidate.id,
                "hunt_id": hunt.id,
                "hunt_candidate_id": target.id,
            },
            undo_payload={
                "candidate_id": candidate.id,
                "hunt_id": hunt.id,
                "hunt_candidate_id": target.id,
                "created_enrollment": created_enrollment,
                "created_activity_ids": [row.id for row in target.activities or []]
                if created_enrollment
                else [],
                "created_tag_id": created_tag_id,
                "removed_rows": removed_rows,
                "removed_tags": removed_tags,
            },
        )
        return {
            "status": "success",
            "changed": True,
            "candidate_id": candidate.id,
            "candidate_name": candidate.full_name,
            "hunt_id": hunt.id,
            "hunt_title": hunt.title,
            "hunt_candidate_id": target.id,
            "moved": data.move_from_other_hunts,
            "action_id": history.id,
            "undoable": True,
            "undo_window_days": 7,
        }


@register_action(
    "pipeline.remove",
    description="Remove one Hunt enrollment while preserving its canonical Candidate, with seven-day undo.",
    input_model=PipelineRemoveInput,
    resource_resolver=_pipeline_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="remove_pipeline_by_id",
)
def remove_pipeline_action(data: PipelineRemoveInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.hunts.models import HuntCandidate
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        row = db.get(HuntCandidate, data.hunt_candidate_id)
        if not row:
            raise ValueError("Pipeline candidate not found.")
        snapshot = _pipeline_row_snapshot(row)
        name, hunt_id, candidate_id = row.full_name, row.hunt_id, row.candidate_id
        db.delete(row)
        db.flush()
        history = record_action(
            db,
            action_type="remove_pipeline_candidate",
            summary=f"Removed {name} from the Hunt pipeline",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={
                "hunt_id": hunt_id,
                "hunt_candidate_id": data.hunt_candidate_id,
                "candidate_id": candidate_id,
            },
            undo_payload={"hunt_id": hunt_id, "row": snapshot},
        )
        return {
            "status": "success",
            "changed": True,
            "hunt_id": hunt_id,
            "hunt_candidate_id": data.hunt_candidate_id,
            "candidate_id": candidate_id,
            "candidate_name": name,
            "canonical_candidate_preserved": True,
            "action_id": history.id,
            "undoable": True,
            "undo_window_days": 7,
        }


@register_action(
    "pipeline.triage",
    description="Keep or pass one sourced Pipeline candidate, log the Playbook decision, and allow seven-day undo.",
    input_model=PipelineTriageInput,
    resource_resolver=_pipeline_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="triage_pipeline_by_id",
)
def triage_pipeline_action(data: PipelineTriageInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.candidates.models import CandidateTag
    from app.hunts.models import HuntActivity, HuntCandidate, TalentHunt
    from app.hunts.playbook import keep_hunt_candidate, pass_hunt_candidate
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        row = db.get(HuntCandidate, data.hunt_candidate_id)
        if not row:
            raise ValueError("Pipeline candidate not found.")
        snapshot = _pipeline_row_snapshot(row)
        hunt = db.get(TalentHunt, row.hunt_id)
        tag_name = f"Hunt: {hunt.title}" if hunt else None
        removed_tags = []
        if data.decision == "pass" and row.candidate_id and tag_name:
            removed_tags = [
                {"id": tag.id, "tag_name": tag.tag_name, "color": tag.color}
                for tag in db.scalars(
                    select(CandidateTag).where(
                        CandidateTag.candidate_id == row.candidate_id,
                        CandidateTag.tag_name == tag_name,
                    )
                ).all()
            ]
        before_activity_ids = set(
            db.scalars(select(HuntActivity.id).where(HuntActivity.hunt_id == row.hunt_id)).all()
        )
        result = (
            keep_hunt_candidate(db, row.id, note=data.note, author_name=data.author, commit=False)
            if data.decision == "keep"
            else pass_hunt_candidate(
                db, row.id, note=data.note, author_name=data.author, commit=False
            )
        )
        after_activity_ids = set(
            db.scalars(
                select(HuntActivity.id).where(HuntActivity.hunt_id == snapshot["hunt_id"])
            ).all()
        )
        created_activity_ids = sorted(after_activity_ids - before_activity_ids)
        history = record_action(
            db,
            action_type="triage_pipeline_candidate",
            summary=f"{data.decision.title()} {snapshot['full_name']} for the Hunt",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={
                "hunt_id": snapshot["hunt_id"],
                "hunt_candidate_id": snapshot["id"],
                "candidate_id": snapshot["candidate_id"],
                "decision": data.decision,
            },
            undo_payload={
                "decision": data.decision,
                "hunt_id": snapshot["hunt_id"],
                "row": snapshot,
                "playbook_entry_id": result.get("playbook_entry_id"),
                "created_activity_ids": created_activity_ids,
                "removed_tags": removed_tags,
            },
        )
        return {
            **result,
            "changed": True,
            "hunt_id": snapshot["hunt_id"],
            "hunt_candidate_id": snapshot["id"],
            "candidate_name": snapshot["full_name"],
            "action_id": history.id,
            "undoable": True,
            "undo_window_days": 7,
        }


@register_action(
    "pipeline.stages.add",
    description="Add a custom stage to one Hunt Pipeline with seven-day undo.",
    input_model=PipelineStageAddInput,
    resource_resolver=_pipeline_hunt_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="add_pipeline_stage",
)
def add_pipeline_stage_action(data: PipelineStageAddInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.hunts.models import HuntStage, TalentHunt
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        if not db.get(TalentHunt, data.hunt_id):
            raise ValueError("Talent Hunt not found.")
        existing = list(
            db.scalars(select(HuntStage).where(HuntStage.hunt_id == data.hunt_id)).all()
        )
        if any((stage.name or "").strip().lower() == data.name.lower() for stage in existing):
            raise ValueError("A Pipeline stage with that name already exists.")
        stage = HuntStage(
            hunt_id=data.hunt_id,
            name=data.name,
            position=max((item.position for item in existing), default=-1) + 1,
            color=data.color,
        )
        db.add(stage)
        db.flush()
        history = record_action(
            db,
            action_type="add_pipeline_stage",
            summary=f"Added Pipeline stage {stage.name}",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={"hunt_id": data.hunt_id, "stage_id": stage.id},
            undo_payload={"hunt_id": data.hunt_id, "stage_id": stage.id},
        )
        return {
            "status": "success",
            "changed": True,
            "hunt_id": data.hunt_id,
            "stage_id": stage.id,
            "stage": stage.name,
            "action_id": history.id,
            "undoable": True,
            "undo_window_days": 7,
        }


@register_action(
    "playbook.list",
    description="List shared sourcing Playbook decisions and insights with bounded filters.",
    input_model=PlaybookListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="consult_sourcing_playbook",
)
def list_playbook_action(data: PlaybookListInput, ctx: ActionContext) -> dict[str, Any]:
    from app.hunts.playbook import list_playbook_entries
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        entries = list_playbook_entries(
            db,
            entry_type=data.entry_type,
            role=data.role,
            platform=data.platform,
            search=data.search,
            limit=data.limit,
        )
        rows = [
            {
                "id": entry.id,
                "entry_type": entry.entry_type,
                "insight_outcome": entry.insight_outcome,
                "role_context": entry.role_context,
                "platform": entry.platform,
                "query_text": entry.query_text,
                "candidate_name": entry.candidate_name,
                "candidate_title": entry.candidate_title,
                "candidate_id": entry.candidate_id,
                "hunt_id": entry.hunt_id,
                "hunt_title": entry.hunt_title,
                "note": entry.note,
                "author_name": entry.author_name,
                "metadata": json.loads(entry.metadata_json) if entry.metadata_json else None,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }
            for entry in entries
        ]
        return {"status": "success", "count": len(rows), "entries": rows}


@register_action(
    "playbook.insights.add",
    description="Add one shared sourcing insight with seven-day Undo.",
    input_model=PlaybookInsightAddInput,
    resource_resolver=_playbook_insight_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="add_sourcing_playbook_insight",
)
def add_playbook_insight_action(
    data: PlaybookInsightAddInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.hunts.models import TalentHunt
    from app.hunts.playbook import add_insight
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        hunt = db.get(TalentHunt, data.hunt_id) if data.hunt_id else None
        if data.hunt_id and not hunt:
            raise ValueError("Talent Hunt not found.")
        entry = add_insight(
            db,
            worked=data.worked,
            note=data.note,
            role_context=(data.role_context or "").strip() or None,
            platform=(data.platform or "").strip() or None,
            query_text=(data.query_text or "").strip() or None,
            hunt_id=data.hunt_id,
            hunt_title=hunt.title if hunt else None,
            author_name=data.author_name,
            commit=False,
        )
        history = record_action(
            db,
            action_type="add_playbook_insight",
            summary=f"Added Playbook insight: {entry.note[:80]}",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={"playbook_entry_id": entry.id, "hunt_id": entry.hunt_id},
            undo_payload={"playbook_entry_id": entry.id},
        )
        return {
            "status": "success",
            "entry_id": entry.id,
            "outcome": entry.insight_outcome,
            "action_id": history.id,
            "undoable": True,
            "undo_window_days": 7,
        }


@register_action(
    "intake.requests.create",
    description="Create a candidate Intake link and draft outreach text; nothing is sent. Supports seven-day Undo until submitted.",
    input_model=IntakeRequestCreateInput,
    resource_resolver=_intake_request_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write", "draft"),
    copilot_enabled=True,
    copilot_tool_name="create_candidate_intake_link",
)
def create_intake_request_action(
    data: IntakeRequestCreateInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.candidates.intake_service import (
        create_intake_request,
        draft_outreach_message,
        get_hunt_jd_context,
        intake_url_for_token,
    )
    from app.candidates.service import get_candidate
    from app.hunts.models import TalentHunt
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        candidate = get_candidate(db, data.candidate_id)
        if not candidate:
            raise ValueError("Candidate not found.")
        if data.hunt_id and not db.get(TalentHunt, data.hunt_id):
            raise ValueError("Talent Hunt not found.")
        request = create_intake_request(
            db,
            data.candidate_id,
            hunt_id=data.hunt_id,
            expires_in_days=data.expires_in_days,
            mark_sent=True,
            commit=False,
        )
        if not request:
            raise RuntimeError("Could not create Intake link.")
        url = intake_url_for_token(request.token)
        jd = get_hunt_jd_context(db, data.hunt_id)
        draft = draft_outreach_message(
            candidate, url=url, hunt_title=jd.get("title"), role=jd.get("role")
        )
        history = record_action(
            db,
            action_type="create_intake_request",
            summary=f"Created Intake link for {candidate.full_name}",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={
                "request_id": request.id,
                "candidate_id": candidate.id,
                "hunt_id": data.hunt_id,
            },
            undo_payload={"request_id": request.id},
        )
        return {
            "status": "success",
            "candidate_id": candidate.id,
            "hunt_id": data.hunt_id,
            "request_id": request.id,
            "url": url,
            "draft_message": draft,
            "sent": False,
            "message": "Link created. Nothing was sent.",
            "action_id": history.id,
            "undoable": True,
            "undo_window_days": 7,
        }


@register_action(
    "intake.submissions.list",
    description="List pending Candidate Intake submissions awaiting recruiter review.",
    input_model=IntakeSubmissionListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="list_pending_intake_submissions",
)
def list_intake_submissions_action(
    data: IntakeSubmissionListInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.candidates.intake_service import list_pending_submissions
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        rows = list_pending_submissions(db, candidate_id=data.candidate_id, limit=data.limit)
        return {"status": "success", "count": len(rows), "submissions": rows}


@register_action(
    "intake.submissions.review",
    description="Accept and apply, or reject, one pending Intake submission as one audited transaction with seven-day Undo.",
    input_model=IntakeSubmissionReviewInput,
    resource_resolver=_intake_submission_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="apply_intake_submission",
)
def review_intake_submission_action(
    data: IntakeSubmissionReviewInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.candidates.intake_service import apply_intake_submission
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        result = apply_intake_submission(
            db,
            data.submission_id,
            mode=data.mode,
            accept=data.accept,
            profile_payload=data.profile_payload,
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
        )
        if result.get("status") != "success":
            raise ValueError(result.get("message") or "Intake submission review failed.")
        return result


@register_action(
    "hunts.list",
    description="List and search Talent Hunts from the canonical Hunt service.",
    input_model=HuntListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="list_hunt_records",
)
def list_hunts_action(data: HuntListInput, ctx: ActionContext) -> dict[str, Any]:
    from app.hunts.service import get_hunt_metrics, list_hunts
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        status = (
            data.status.strip().title() if data.status and data.status.lower() != "all" else None
        )
        hunts = list_hunts(db, status=status, skip=data.offset, limit=data.limit)
        needle = (data.search or "").strip().lower()
        if needle:
            hunts = [
                hunt
                for hunt in hunts
                if needle in (hunt.title or "").lower()
                or needle in (hunt.target_role or "").lower()
            ]
        rows = []
        for hunt in hunts:
            metrics = get_hunt_metrics(db, hunt.id, reconcile=False) or {}
            payload = _hunt_payload(hunt)
            rows.append(
                {
                    **payload,
                    "total_candidates": metrics.get("total_candidates", 0),
                    "hired_count": metrics.get("hired_count", 0),
                    "avg_match_score": metrics.get("avg_match_score", 0.0),
                }
            )
        return {
            "status": "success",
            "count": len(rows),
            "offset": data.offset,
            "limit": data.limit,
            "hunts": rows,
        }


@register_action(
    "hunts.get",
    description="Read one Talent Hunt including search configuration, stages, and canonical Pipeline count.",
    input_model=HuntGetInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_hunt_record",
)
def get_hunt_action(data: HuntGetInput, ctx: ActionContext) -> dict[str, Any]:
    from app.hunts.service import get_hunt, get_hunt_metrics
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        hunt = get_hunt(db, data.hunt_id)
        if not hunt:
            raise ValueError("Talent Hunt not found.")
        metrics = get_hunt_metrics(db, hunt.id, reconcile=False) or {}
        return {"status": "success", "hunt": {**_hunt_payload(hunt), "metrics": metrics}}


@register_action(
    "hunts.create",
    description="Create one canonical Talent Hunt and its Pipeline configuration with guarded seven-day undo.",
    input_model=HuntCreateInput,
    resource_resolver=_hunt_create_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="create_hunt_record",
)
def create_hunt_action(data: HuntCreateInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.hunts.experience import parse_experience_range
    from app.hunts.service import create_hunt
    from app.infrastructure.db import SessionFactory

    experience = (data.experience or "").strip()
    exp_min, exp_max = parse_experience_range(experience) if experience else (None, None)
    location = (data.location or "").strip() or "India"
    config = {
        "required_skills": (data.required_skills or "").strip() or None,
        "preferred_skills": (data.preferred_skills or "").strip() or None,
        "experience_years_min": exp_min,
        "experience_years_max": exp_max,
        "min_experience": experience or None,
        "locations": location,
        "industry": (data.industry or "").strip() or None,
        "remote_policy": (data.remote_policy or "").strip() or None,
        "target_platforms": [
            item.strip().lower() for item in data.target_platforms if item.strip()
        ],
    }
    with SessionFactory() as db:
        hunt = create_hunt(
            db,
            title=data.title,
            target_role=(data.target_role or "").strip() or data.title,
            location=location,
            salary_range=(data.salary_range or "").strip() or None,
            description=(data.description or "").strip() or None,
            search_config=config,
            commit=False,
        )
        if not hunt:
            raise RuntimeError("Talent Hunt creation failed.")
        hunt.status = data.status
        db.flush()
        initial = _hunt_payload(hunt)
        history = record_action(
            db,
            action_type="create_hunt",
            summary=f"Created Talent Hunt '{hunt.title}'",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={"hunt_id": hunt.id, "title": hunt.title},
            undo_payload={
                "hunt_id": hunt.id,
                "initial_state": initial,
                "initial_stage_ids": [stage["id"] for stage in initial["stages"]],
                "initial_activity_ids": [activity.id for activity in hunt.activities or []],
                "initial_search_config_id": (initial["search_config"] or {}).get("id"),
            },
        )
        return {
            "status": "success",
            "changed": True,
            "hunt_id": hunt.id,
            "hunt_title": hunt.title,
            "hunt_status": hunt.status,
            "action_id": history.id,
            "undoable": True,
            "undo_window_days": 7,
        }


@register_action(
    "hunts.update",
    description="Update Hunt details and search configuration with exact seven-day undo.",
    input_model=HuntUpdateInput,
    resource_resolver=_hunt_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="update_hunt_record",
)
def update_hunt_action(data: HuntUpdateInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.hunts.experience import parse_experience_range
    from app.hunts.models import HuntSearchConfig
    from app.hunts.service import get_hunt
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        hunt = get_hunt(db, data.hunt_id)
        if not hunt:
            raise ValueError("Talent Hunt not found.")
        if hunt.status == "Archived":
            raise ValueError("Restore the archived Hunt before editing it.")
        before = _hunt_payload(hunt)
        changed = []
        direct_fields = ("title", "target_role", "location", "salary_range", "description")
        for field in direct_fields:
            if field not in data.model_fields_set:
                continue
            value = getattr(data, field)
            cleaned = value.strip() if isinstance(value, str) else value
            cleaned = cleaned or None
            if getattr(hunt, field) != cleaned:
                setattr(hunt, field, cleaned)
                changed.append(field)

        config_fields = {
            "required_skills": "required_skills",
            "preferred_skills": "preferred_skills",
            "industry": "industry",
            "remote_policy": "remote_policy",
        }
        needs_config = bool(set(config_fields) & data.model_fields_set) or bool(
            {"experience", "target_platforms", "location"} & data.model_fields_set
        )
        if needs_config and not hunt.search_config:
            hunt.search_config = HuntSearchConfig(hunt_id=hunt.id)
            db.add(hunt.search_config)
            db.flush()
        config = hunt.search_config
        if config:
            for input_field, model_field in config_fields.items():
                if input_field not in data.model_fields_set:
                    continue
                value = getattr(data, input_field)
                cleaned = value.strip() if isinstance(value, str) else value
                cleaned = cleaned or None
                if getattr(config, model_field) != cleaned:
                    setattr(config, model_field, cleaned)
                    changed.append(input_field)
            if "location" in data.model_fields_set:
                location = (data.location or "").strip() or None
                if config.locations != location:
                    config.locations = location
                    if "location" not in changed:
                        changed.append("location")
            if "experience" in data.model_fields_set:
                exp_text = (data.experience or "").strip()
                exp_min, exp_max = parse_experience_range(exp_text) if exp_text else (None, None)
                if (config.experience_years_min, config.experience_years_max) != (exp_min, exp_max):
                    config.experience_years_min, config.experience_years_max = exp_min, exp_max
                    changed.append("experience")
                config.keywords = f"Exp: {exp_text}" if exp_text else None
            if "target_platforms" in data.model_fields_set:
                platforms = [
                    item.strip().lower() for item in (data.target_platforms or []) if item.strip()
                ]
                encoded = json.dumps(platforms)
                if config.target_platforms != encoded:
                    config.target_platforms = encoded
                    changed.append("target_platforms")
        if not changed:
            return {
                "status": "success",
                "changed": False,
                "hunt_id": hunt.id,
                "hunt_title": hunt.title,
                "undoable": False,
            }
        db.flush()
        history = record_action(
            db,
            action_type="update_hunt",
            summary=f"Updated Talent Hunt '{hunt.title}'",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={"hunt_id": hunt.id, "changed_fields": sorted(set(changed))},
            undo_payload={"hunt_id": hunt.id, "hunt_state": before},
        )
        return {
            "status": "success",
            "changed": True,
            "hunt_id": hunt.id,
            "hunt_title": hunt.title,
            "changed_fields": sorted(set(changed)),
            "action_id": history.id,
            "undoable": True,
            "undo_window_days": 7,
        }


@register_action(
    "hunts.status.set",
    description="Set a non-archival Talent Hunt lifecycle status with seven-day undo.",
    input_model=HuntStatusInput,
    resource_resolver=_hunt_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="set_hunt_lifecycle_status",
)
def set_hunt_status_action(data: HuntStatusInput, ctx: ActionContext) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.hunts.models import TalentHunt
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        hunt = db.get(TalentHunt, data.hunt_id)
        if not hunt:
            raise ValueError("Talent Hunt not found.")
        if hunt.status == "Archived":
            raise ValueError("Use Action History Undo to restore an archived Hunt.")
        previous = hunt.status
        if previous == data.status:
            return {
                "status": "success",
                "changed": False,
                "hunt_id": hunt.id,
                "hunt_title": hunt.title,
                "new_status": hunt.status,
                "undoable": False,
            }
        hunt.status = data.status
        history = record_action(
            db,
            action_type="set_hunt_status",
            summary=f"Changed '{hunt.title}' from {previous} to {data.status}",
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
            payload={"hunt_id": hunt.id, "new_status": data.status},
            undo_payload={"hunt_id": hunt.id, "previous_status": previous},
        )
        return {
            "status": "success",
            "changed": True,
            "hunt_id": hunt.id,
            "hunt_title": hunt.title,
            "previous_status": previous,
            "new_status": data.status,
            "action_id": history.id,
            "undoable": True,
            "undo_window_days": 7,
        }


@register_action(
    "hunts.archive",
    description="Archive one Talent Hunt after an immutable, trusted preview.",
    preview_handler=_preview_hunt_archive,
    input_model=HuntArchiveInput,
    resource_resolver=_hunt_resources,
    requires_approval=True,
    classification="mutation",
    risk_level="R3",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="archive_hunt_by_id",
)
def archive_hunt_action(data: HuntArchiveInput, ctx: ActionContext) -> dict[str, Any]:
    from app.hunts.models import TalentHunt
    from app.hunts.service import delete_hunt
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        hunt = db.get(TalentHunt, data.hunt_id)
        if not hunt:
            raise ValueError("Hunt not found.")
        title = hunt.title
        if not delete_hunt(
            db,
            hunt.id,
            actor_type=_history_actor(ctx),
            session_id=ctx.session_id,
        ):
            raise RuntimeError("Hunt archive failed.")
        return {
            "status": "success",
            "hunt_id": data.hunt_id,
            "hunt_title": title,
            "new_status": "Archived",
            "undoable": True,
            "undo_window_days": 7,
        }


@register_action(
    "analytics.kpi",
    description="Read canonical recruiting KPIs for all Hunts or one Hunt, including explicit telemetry limitations.",
    input_model=AnalyticsScopeInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_recruiting_kpis",
)
def get_analytics_kpi_action(data: AnalyticsScopeInput, ctx: ActionContext) -> dict[str, Any]:
    from app.analytics.service import get_kpi_summary
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        scope = _analytics_scope(db, data.hunt_id)
        metrics = get_kpi_summary(db, hunt_id=data.hunt_id)
        return _analytics_result(
            metric="kpi",
            service="app.analytics.service.get_kpi_summary",
            scope=scope,
            data=metrics,
            tables=[
                "talent_hunts",
                "candidates",
                "hunt_candidates",
                "hunt_stages",
                "communications",
                "hunt_activities",
            ],
            limitations=[
                "Provider token and billing telemetry is not persisted; cost fields remain zero.",
                "Average time to fill is based only on recorded hired transitions.",
            ],
        )


@register_action(
    "analytics.funnel",
    description="Read the canonical recruiting funnel and stage conversion counts for all Hunts or one Hunt.",
    input_model=AnalyticsScopeInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_recruiting_funnel",
)
def get_analytics_funnel_action(data: AnalyticsScopeInput, ctx: ActionContext) -> dict[str, Any]:
    from app.analytics.service import get_hunt_funnel_data
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        scope = _analytics_scope(db, data.hunt_id)
        metrics = get_hunt_funnel_data(db, hunt_id=data.hunt_id)
        return _analytics_result(
            metric="funnel",
            service="app.analytics.service.get_hunt_funnel_data",
            scope=scope,
            data=metrics,
            tables=["hunt_candidates", "hunt_stages"],
        )


@register_action(
    "analytics.time_to_fill",
    description="Read canonical Hunt velocity and time-to-fill metrics without inventing unavailable stage durations.",
    input_model=AnalyticsScopeInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_time_to_fill_analytics",
)
def get_analytics_time_to_fill_action(
    data: AnalyticsScopeInput,
    ctx: ActionContext,
) -> dict[str, Any]:
    from app.analytics.service import get_time_to_fill_metrics
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        scope = _analytics_scope(db, data.hunt_id)
        metrics = get_time_to_fill_metrics(db, hunt_id=data.hunt_id)
        return _analytics_result(
            metric="time_to_fill",
            service="app.analytics.service.get_time_to_fill_metrics",
            scope=scope,
            data=metrics,
            tables=["talent_hunts", "hunt_candidates", "hunt_stages"],
            limitations=[
                "Per-stage entry timestamps are not stored, so stage bottleneck durations are unavailable."
            ],
        )


@register_action(
    "analytics.sourcing_quality",
    description="Read canonical match-score, source-channel, and stored-skill quality metrics.",
    input_model=AnalyticsScopeInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_sourcing_quality_analytics",
)
def get_analytics_sourcing_quality_action(
    data: AnalyticsScopeInput,
    ctx: ActionContext,
) -> dict[str, Any]:
    from app.analytics.service import get_sourcing_quality_metrics
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        scope = _analytics_scope(db, data.hunt_id)
        metrics = get_sourcing_quality_metrics(db, hunt_id=data.hunt_id)
        return _analytics_result(
            metric="sourcing_quality",
            service="app.analytics.service.get_sourcing_quality_metrics",
            scope=scope,
            data=metrics,
            tables=["hunt_candidates", "candidate_profiles"],
            limitations=[
                "Unscored candidates are reported separately rather than assigned a score."
            ],
        )


@register_action(
    "analytics.outreach",
    description="Read canonical communication and sequence metrics, scoped to candidates in one Hunt when requested.",
    input_model=AnalyticsScopeInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_outreach_analytics",
)
def get_analytics_outreach_action(data: AnalyticsScopeInput, ctx: ActionContext) -> dict[str, Any]:
    from app.analytics.service import get_outreach_analytics
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        scope = _analytics_scope(db, data.hunt_id)
        metrics = get_outreach_analytics(db, hunt_id=data.hunt_id)
        return _analytics_result(
            metric="outreach",
            service="app.analytics.service.get_outreach_analytics",
            scope=scope,
            data=metrics,
            tables=["communications", "outreach_sequences", "outreach_enrollments"],
            limitations=[
                "Hunt scope follows canonical Candidate enrollment because communications do not store a Hunt ID."
            ],
        )


@register_action(
    "analytics.ai_cost",
    description="Read recorded AI operation counts and honest cost telemetry availability for all Hunts or one Hunt.",
    input_model=AnalyticsScopeInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_ai_usage_costs",
)
def get_analytics_ai_cost_action(data: AnalyticsScopeInput, ctx: ActionContext) -> dict[str, Any]:
    from app.analytics.service import get_ai_cost_tracker
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        scope = _analytics_scope(db, data.hunt_id)
        metrics = get_ai_cost_tracker(db, hunt_id=data.hunt_id)
        return _analytics_result(
            metric="ai_cost",
            service="app.analytics.service.get_ai_cost_tracker",
            scope=scope,
            data=metrics,
            tables=["hunt_activities"],
            limitations=[
                "Provider, token, and billing telemetry is not persisted; no cost saving is estimated."
            ],
        )


@register_action(
    "analytics.trends",
    description="Read canonical daily sourcing, outreach, and hire trends for a bounded date window.",
    input_model=AnalyticsTrendInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_recruiting_trends",
)
def get_analytics_trends_action(data: AnalyticsTrendInput, ctx: ActionContext) -> dict[str, Any]:
    from app.analytics.service import get_trend_analytics
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        scope = _analytics_scope(db, data.hunt_id)
        metrics = get_trend_analytics(db, days=data.days, hunt_id=data.hunt_id)
        return _analytics_result(
            metric="trends",
            service="app.analytics.service.get_trend_analytics",
            scope=scope,
            data=metrics,
            tables=["candidates", "hunt_candidates", "hunt_stages", "communications"],
            filters={"hunt_id": data.hunt_id, "days": data.days},
        )


@register_action(
    "jobs.list",
    description="List bounded durable background-job history with status, progress, cancellation, and retry capability.",
    input_model=JobListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="list_background_jobs",
)
def list_background_jobs_action(data: JobListInput, ctx: ActionContext) -> dict[str, Any]:
    from app.jobs import service as jobs

    if data.status == "all":
        statuses = None
    elif data.status == "active":
        statuses = {"running"}
    elif data.status == "retryable":
        statuses = jobs.RETRYABLE_STATUSES
    else:
        statuses = {data.status}
    rows = jobs.list_job_rows(
        statuses=statuses,
        kind=data.kind,
        hunt_id=data.hunt_id,
        limit=data.limit,
    )
    items = [_job_payload(row) for row in rows]
    if data.status == "retryable":
        items = [item for item in items if item["retryable"]]
    return {
        "status": "success",
        "filters": {
            "status": data.status,
            "kind": data.kind,
            "hunt_id": data.hunt_id,
            "limit": data.limit,
        },
        "count": len(items),
        "jobs": items,
    }


@register_action(
    "jobs.get",
    description="Read exact durable status, progress, lineage, error, and available controls for one background job.",
    input_model=JobIdInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_background_job",
)
def get_background_job_action(data: JobIdInput, ctx: ActionContext) -> dict[str, Any]:
    from app.jobs import service as jobs

    row = jobs.get_job_row(data.job_id)
    if not row:
        raise ValueError("Background job not found.")
    return {"status": "success", "job": _job_payload(row)}


@register_action(
    "jobs.cancel",
    description=(
        "Cancel one supported sourcing, profile-enrichment, connected-site, or embedded-AI "
        "job by durable ID when it is still safe to interrupt."
    ),
    input_model=JobCancelInput,
    resource_resolver=_job_control_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write", "compute"),
    copilot_enabled=True,
    copilot_tool_name="cancel_background_job",
)
def cancel_background_job_action(data: JobCancelInput, ctx: ActionContext) -> dict[str, Any]:
    from app.jobs.runner import cancel_job

    result = cancel_job(data.job_id)
    return {
        "status": "success",
        "job_id": result["job_id"],
        "kind": result["kind"],
        "job_status": result["status"],
        "message": result["message"],
    }


@register_action(
    "jobs.retry",
    description="Retry one failed, cancelled, or interrupted durable background job using its stored launch parameters.",
    input_model=JobRetryInput,
    resource_resolver=_job_retry_resources,
    classification="ai_task",
    risk_level="R2",
    required_scopes=("write", "compute"),
    copilot_enabled=True,
    copilot_tool_name="retry_background_job",
)
def retry_background_job_action(data: JobRetryInput, ctx: ActionContext) -> dict[str, Any]:
    from app.jobs.runner import retry_job

    result = retry_job(data.job_id)
    return {
        "status": "success",
        "retried_job_id": data.job_id,
        **result,
    }
