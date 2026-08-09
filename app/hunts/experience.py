"""Experience range helpers for hunt search + sourcing filters."""

from __future__ import annotations

import re
from typing import Optional, Tuple

# Titles that imply seniority far above a mid/junior exp band
_SENIOR_TITLE_RE = re.compile(
    r"\b("
    r"gm|general\s+manager|ceo|cto|cfo|coo|cmo|cio|"
    r"vp|vice[\s-]?president|svp|evp|"
    r"managing\s+director|executive\s+director|director|"
    r"founder|co[\s-]?founder|owner|partner|"
    r"chief\s+\w+|president|head\s+of|"
    r"practice\s+head|country\s+head|board\s+member"
    r")\b",
    re.I,
)


def parse_experience_range(text: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """Parse free-text like '4-5 years', '4–8 yrs', '5+', '3 to 5' into (min, max)."""
    if text is None:
        return None, None
    raw = str(text).strip().lower()
    if not raw:
        return None, None

    # 4-5 / 4–5 / 4 to 5 / 4 - 5 years
    m = re.search(
        r"(\d+)\s*(?:\+|plus)?\s*(?:-|–|—|to)\s*(\d+)",
        raw,
    )
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return min(a, b), max(a, b)

    # 5+ / 5 plus (before single-number fallback)
    m = re.search(r"(\d+)\s*\+", raw)
    if m:
        return int(m.group(1)), None
    m = re.search(r"(\d+)\s*plus\b", raw)
    if m:
        return int(m.group(1)), None

    # single number: "5 years" → min=max=5 (tight band)
    m = re.search(r"(\d+)", raw)
    if m:
        n = int(m.group(1))
        return n, n

    return None, None


def estimate_years_from_text(*parts: str) -> Optional[float]:
    """Best-effort years estimate from titles/snippets (e.g. '14 years experience')."""
    blob = " ".join(p for p in parts if p).lower()
    if not blob:
        return None

    patterns = [
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:exp|experience)",
        r"(?:experience|exp)[:\s]+(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)",
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:in|as|with)",
        r"\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
    ]
    for pat in patterns:
        m = re.search(pat, blob)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None


def title_implies_seniority(title: Optional[str]) -> bool:
    if not title:
        return False
    return bool(_SENIOR_TITLE_RE.search(title))


def experience_within_range(
    *,
    years: Optional[float],
    exp_min: Optional[int],
    exp_max: Optional[int],
    title: Optional[str] = None,
    reject_unknown_senior: bool = True,
) -> bool:
    """Return False when the candidate is clearly outside the hunt experience band."""
    if years is not None:
        if exp_min is not None and years < float(exp_min):
            return False
        if exp_max is not None and years > float(exp_max):
            return False
        return True

    # Unknown years: still reject obvious leadership titles when a modest max is set
    if reject_unknown_senior and exp_max is not None and exp_max <= 10:
        if title_implies_seniority(title):
            return False

    return True
