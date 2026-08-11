"""LLM structured extraction of experience / education / skills from profile text."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("talenthunt.candidates.profile_extract")


class ExperienceDraft(BaseModel):
    company: str = ""
    title: str = ""
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    employment_type: Optional[str] = None
    description: Optional[str] = None
    skills: List[str] = Field(default_factory=list)


class EducationDraft(BaseModel):
    institution: str = ""
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    grade: Optional[str] = None
    activities: Optional[str] = None
    description: Optional[str] = None


class ProfileExtractSchema(BaseModel):
    """Schema the LLM must fill — only factual fields from source text."""

    full_name: Optional[str] = None
    pronouns: Optional[str] = None
    connection_degree: Optional[str] = None
    connections_count: Optional[int] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    profile_image_url: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    experience_years: Optional[float] = None
    highlights: List[str] = Field(default_factory=list)
    experiences: List[ExperienceDraft] = Field(default_factory=list)
    educations: List[EducationDraft] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)


class ProfileExtractResult(ProfileExtractSchema):
    raw_text_kept: Optional[str] = None
    status: str = "success"
    error: Optional[str] = None


SYSTEM_PROMPT = """You extract structured candidate profile data from resume or profile page text.
Rules:
- Only use facts explicitly present in the text. Never invent companies, titles, degrees, years, or skills.
- If a field is unknown, omit it or use null / empty string.
- Prefer ISO-ish dates like YYYY-MM or YYYY when present.
- Capture the profile identity header: exact full name, pronouns, connection degree, connection count,
  location, professional headline, current title, and current company.
- `summary` is the About section, not navigation text or a concatenation of the whole page.
- `highlights` contains each visible Highlights item as a separate factual sentence.
- `skills` contains Top skills and other explicitly named profile skills.
- For every Experience row capture title, company, employment type, location, start/end dates,
  whether current, description/bullets, and skills attached to that specific role.
- For every Education row capture institution, degree, field, dates, grade, activities, and description.
- Return as many distinct experience and education entries as evidenced; do not merge unrelated roles.
- Do not treat LinkedIn navigation, recommendations, ads, or unrelated people as candidate data.
"""


def _normalize(schema: ProfileExtractSchema, *, raw_kept: str) -> ProfileExtractResult:
    experiences = []
    for row in schema.experiences:
        if not (row.company or "").strip() or not (row.title or "").strip():
            continue
        role_skills = list(dict.fromkeys(
            str(skill).strip() for skill in (row.skills or []) if str(skill).strip()
        ))
        experiences.append(row.model_copy(update={
            "company": row.company.strip(),
            "title": row.title.strip(),
            "employment_type": (row.employment_type or "").strip() or None,
            "skills": role_skills,
        }))
    educations = [
        e for e in schema.educations
        if (e.institution or "").strip()
    ]
    skills = [s.strip() for s in (schema.skills or []) if s and str(s).strip()]
    seen: set[str] = set()
    uniq_skills: List[str] = []
    for s in skills:
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq_skills.append(s)

    years = schema.experience_years
    if years is not None and years < 0:
        years = None

    connections = schema.connections_count
    if connections is not None and connections < 0:
        connections = None
    highlights = list(dict.fromkeys(
        str(item).strip() for item in (schema.highlights or []) if str(item).strip()
    ))

    return ProfileExtractResult(
        full_name=(schema.full_name or "").strip() or None,
        pronouns=(schema.pronouns or "").strip() or None,
        connection_degree=(schema.connection_degree or "").strip() or None,
        connections_count=connections,
        email=(schema.email or "").strip() or None,
        phone=(schema.phone or "").strip() or None,
        location=(schema.location or "").strip() or None,
        current_title=(schema.current_title or "").strip() or None,
        current_company=(schema.current_company or "").strip() or None,
        profile_image_url=(schema.profile_image_url or "").strip() or None,
        headline=(schema.headline or "").strip() or None,
        summary=(schema.summary or "").strip() or None,
        experience_years=years,
        highlights=highlights,
        experiences=experiences,
        educations=educations,
        skills=uniq_skills,
        raw_text_kept=raw_kept[:2000] if raw_kept else None,
        status="success",
    )


def extract_profile_from_text(text: str, *, max_chars: int = 30000) -> ProfileExtractResult:
    """Run structured LLM extract over page/resume text. Never fabricates missing fields."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ProfileExtractResult(
            status="empty",
            error="No text provided to extract.",
            raw_text_kept="",
        )

    truncated = cleaned[:max_chars]
    prompt = (
        "Extract the identity header, highlights, About, top skills, every experience row, "
        "every education row, and total years of experience "
        "from the following candidate profile / resume text.\n\n"
        f"---\n{truncated}\n---"
    )

    try:
        from app.ai.engine import ai_engine

        parsed = ai_engine.generate_structured(
            prompt=prompt,
            schema=ProfileExtractSchema,
            system_prompt=SYSTEM_PROMPT,
        )
        if parsed is None:
            return ProfileExtractResult(
                status="error",
                error="LLM structured extract failed to parse.",
                raw_text_kept=truncated[:2000],
            )
        return _normalize(parsed, raw_kept=truncated)
    except Exception as exc:
        logger.exception("profile extract failed")
        return ProfileExtractResult(
            status="error",
            error=str(exc),
            raw_text_kept=truncated[:2000],
            experiences=[],
            educations=[],
            skills=[],
        )


def extract_result_to_dict(result: ProfileExtractResult) -> Dict[str, Any]:
    """Serialize extract result for UI / Copilot JSON."""
    return result.model_dump()
