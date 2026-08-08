"""Template Rendering Engine for personalized recruiting outreach with merge fields."""

import re
import json
from typing import Any, Dict, List, Optional, Union


DEFAULT_FALLBACKS = {
    "candidate_name": "Candidate",
    "first_name": "there",
    "last_name": "",
    "job_title": "Open Role",
    "company": "our team",
    "current_title": "your role",
    "current_company": "your current company",
    "skills": "your technical background",
    "location": "your location",
    "recruiter_name": "Talent Team",
    "experience_years": "several",
}


def extract_merge_fields(template_str: str) -> List[str]:
    """Extract all double-curly variable names e.g. {{candidate_name}} from template text."""
    if not template_str:
        return []
    # Match {{ variable_name }} or { variable_name }
    pattern = r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}|\{\s*([a-zA-Z0-9_]+)\s*\}"
    matches = re.findall(pattern, template_str)
    var_set = set()
    for m in matches:
        var_name = m[0] or m[1]
        if var_name:
            var_set.add(var_name)
    return sorted(list(var_set))


def render_template(template_str: str, context: Dict[str, Any]) -> str:
    """Render template string with context dict, safely filling missing tags with fallbacks."""
    if not template_str:
        return ""

    merged_context = {**DEFAULT_FALLBACKS, **{k: str(v) for k, v in context.items() if v is not None and str(v).strip() != ""}}

    def replace_var(match: re.Match) -> str:
        var_name = match.group(1)
        if not var_name:
            return match.group(0)
        var_name = var_name.strip()
        val = merged_context.get(var_name)
        if val is not None and str(val).strip() != "":
            return str(val)
        return DEFAULT_FALLBACKS.get(var_name, f"[{var_name}]")

    # Match {{ variable }} double curly braces
    pattern = r"\{\{\s*([a-zA-Z0-9_\.]+)\s*\}\}"
    rendered = re.sub(pattern, replace_var, template_str)
    return rendered


def generate_candidate_outreach(
    template_body: str,
    candidate: Any,
    recruiter_name: str = "Talent Hunt Recruiter",
    job_title: str = "Senior Engineer",
    company: str = "Innovate Tech Solutions",
    custom_fields: Optional[Dict[str, Any]] = None,
) -> str:
    """Helper to build context from a Candidate ORM model/dict and render personalized outreach."""
    ctx: Dict[str, Any] = {
        "recruiter_name": recruiter_name,
        "job_title": job_title,
        "company": company,
    }
    if custom_fields and isinstance(custom_fields, dict):
        ctx.update(custom_fields)

    if candidate:
        if isinstance(candidate, dict):
            full_name = (candidate.get("full_name") or "").strip()
            name_parts = full_name.split() if full_name else []
            ctx["candidate_name"] = full_name or "Candidate"
            ctx["first_name"] = name_parts[0] if name_parts else "there"
            ctx["last_name"] = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
            ctx["email"] = candidate.get("email", "")
            ctx["current_title"] = candidate.get("current_title", "")
            ctx["current_company"] = candidate.get("current_company", "")
            ctx["location"] = candidate.get("location", "")
            ctx["experience_years"] = candidate.get("experience_years", "")
            if "skills" in candidate:
                skills_val = candidate["skills"]
                ctx["skills"] = ", ".join(str(s) for s in skills_val if s) if isinstance(skills_val, list) else str(skills_val)
        else:
            # SQLAlchemy Model object
            full_name = (getattr(candidate, "full_name", "") or "").strip()
            name_parts = full_name.split() if full_name else []
            ctx["candidate_name"] = full_name or "Candidate"
            ctx["first_name"] = name_parts[0] if name_parts else "there"
            ctx["last_name"] = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
            ctx["email"] = getattr(candidate, "email", "") or ""
            ctx["current_title"] = getattr(candidate, "current_title", "") or ""
            ctx["current_company"] = getattr(candidate, "current_company", "") or ""
            ctx["location"] = getattr(candidate, "location", "") or ""
            ctx["experience_years"] = getattr(candidate, "experience_years", "") or ""

            # Check profile skills
            profile = getattr(candidate, "profile", None)
            if profile and getattr(profile, "skills_json", None):
                try:
                    skills_arr = json.loads(profile.skills_json)
                    ctx["skills"] = ", ".join(str(s) for s in skills_arr)
                except Exception:
                    ctx["skills"] = ""

    if custom_fields:
        ctx.update(custom_fields)

    return render_template(template_body, ctx)
