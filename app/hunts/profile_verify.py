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
    name: str = "",
    title: str = "",
    years: Optional[float] = None,
    page_text: str = "",
) -> Dict[str, Any]:
    """Ask the LLM whether this person fits the hunt. Returns pass/fail + years estimate.

    Reply shape:
      {"pass": bool, "years": float|null, "reason": str, "title": str}
    """
    band = "any"
    if exp_min is not None and exp_max is not None:
        band = f"{exp_min}-{exp_max} years"
    elif exp_min is not None:
        band = f"{exp_min}+ years"
    elif exp_max is not None:
        band = f"up to {exp_max} years"

    excerpt = (page_text or "")[:3500]
    prompt = (
        "You are a recruiter screener. Decide if this LinkedIn/Naukri profile fits the hunt.\n"
        "Rules:\n"
        f"1. Target role: {role}\n"
        f"2. Skills (soft guidance): {skills or 'n/a'}\n"
        f"3. Experience band: {band}\n"
        "4. PASS only if the person's CURRENT/RECENT work matches the role family "
        "(e.g. Sales/BD/Account for a BD Executive hunt — reject Animators, Engineers unrelated to sales, "
        "and people clearly outside the experience band).\n"
        "5. Estimate total years of professional experience from dates/text when possible.\n"
        "6. Reply with ONLY compact JSON: "
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
            return {"pass": False, "years": years, "title": title, "reason": "AI returned no JSON"}
        data = json.loads(m.group(0))
        return {
            "pass": bool(data.get("pass")),
            "years": data.get("years", years),
            "title": (data.get("title") or title or "")[:120],
            "reason": str(data.get("reason") or "")[:240],
        }
    except Exception as exc:
        logger.warning("ai_verify_profile failed: %s", exc)
        # Fail closed when band is tight and years unknown/senior — else soft pass on heuristics
        return {
            "pass": True,
            "years": years,
            "title": title,
            "reason": f"AI verify unavailable ({exc}); using heuristics only",
            "fallback": True,
        }
