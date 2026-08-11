"""AI cross-check of Playwright-read profiles against hunt criteria."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("talenthunt.hunts.profile_verify")


def ai_verify_profile(
    *,
    role: str,
    skills: str = "",
    exp_min: Optional[int] = None,
    exp_max: Optional[int] = None,
    location: str = "",
    name: str = "",
    title: str = "",
    years: Optional[float] = None,
    page_text: str = "",
) -> Dict[str, Any]:
    """Ask the LLM whether this person fits the hunt. Returns pass/fail + years estimate.

    Reply shape:
      {"pass": bool, "years": float|null, "reason": str, "title": str}
    """
    from app.hunts.experience import band_is_configured, experience_within_range

    band = "any"
    if exp_min is not None and exp_max is not None:
        band = f"{exp_min}-{exp_max} years"
    elif exp_min is not None:
        band = f"{exp_min}+ years"
    elif exp_max is not None:
        band = f"up to {exp_max} years"

    has_band = band_is_configured(exp_min, exp_max)
    target_loc = (location or "").strip() or "any"
    excerpt = (page_text or "")[:3500]
    prompt = (
        "You are a recruiter screener. Decide if this LinkedIn/Naukri profile fits the hunt.\n"
        "Rules:\n"
        f"1. Target role: {role}\n"
        f"2. Skills (soft guidance): {skills or 'n/a'}\n"
        f"3. Experience band: {band}  ← HARD REQUIREMENT when not 'any'\n"
        f"4. Target location: {target_loc}  ← HARD when set (e.g. India). "
        "Reject people clearly based in other countries (USA, Italy, UK, etc.). "
        "If location is not evidenced and target is India → pass=false.\n"
        "5. PASS only if the person's CURRENT/RECENT work matches the role family "
        "(e.g. Sales/BD/Account for a BD Executive hunt — reject Animators, Engineers unrelated to sales).\n"
        "6. Experience HARD RULES:\n"
        "   - Estimate total years from job date ranges and/or explicit 'N years' claims.\n"
        "   - Outside band → pass=false. Unknown years with a band set → pass=false.\n"
        "   - NEVER invent a years number.\n"
        "7. Reply with ONLY compact JSON: "
        '{"pass": true|false, "years": number|null, "title": "best job title", "reason": "short"}\n'
    )
    human = (
        f"Name: {name}\n"
        f"Parsed title: {title}\n"
        f"Heuristic years: {years}\n\n"
        f"PROFILE TEXT:\n{excerpt}"
    )

    try:
        from app.ai.engine import ai_engine
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ai_engine.get_llm(temperature=0.1, max_tokens=300)
        raw = llm.invoke([SystemMessage(content=prompt), HumanMessage(content=human)]).content
        text = str(raw or "").strip()
        # Extract JSON object even if wrapped in markdown
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {
                "pass": False if has_band else False,
                "years": years,
                "title": title,
                "reason": "AI returned no JSON",
            }
        data = json.loads(m.group(0))
        ai_years = data.get("years", years)
        try:
            ai_years_f = float(ai_years) if ai_years is not None else years
        except (TypeError, ValueError):
            ai_years_f = years

        ai_pass = bool(data.get("pass"))
        # Hard gate: never trust AI pass that violates the experience band
        if has_band and not experience_within_range(
            years=ai_years_f,
            exp_min=exp_min,
            exp_max=exp_max,
            title=(data.get("title") or title or ""),
            reject_unknown=True,
        ):
            ai_pass = False
            reason = str(data.get("reason") or "")
            reason = (reason + " | hard reject: outside experience band").strip(" |")
        else:
            reason = str(data.get("reason") or "")[:240]

        return {
            "pass": ai_pass,
            "years": ai_years_f,
            "title": (data.get("title") or title or "")[:120],
            "reason": reason[:240],
        }
    except Exception as exc:
        logger.warning("ai_verify_profile failed: %s", exc)
        # Fail closed when a band is set
        if has_band:
            ok = experience_within_range(
                years=years,
                exp_min=exp_min,
                exp_max=exp_max,
                title=title,
                reject_unknown=True,
            )
            return {
                "pass": ok,
                "years": years,
                "title": title,
                "reason": f"AI verify unavailable ({exc}); heuristics only (fail-closed on band)",
                "fallback": True,
            }
        return {
            "pass": True,
            "years": years,
            "title": title,
            "reason": f"AI verify unavailable ({exc}); using heuristics only",
            "fallback": True,
        }
