"""Experience range helpers for hunt search + sourcing filters."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional, Tuple

# Titles that imply seniority far above a mid/junior exp band
_SENIOR_TITLE_RE = re.compile(
    r"\b("
    r"gm|general\s+manager|ceo|cto|cfo|coo|cmo|cio|"
    r"vp|vice[\s-]?president|svp|evp|"
    r"managing\s+director|executive\s+director|director|"
    r"founder|co[\s-]?founder|owner|partner|"
    r"chief\s+\w+|president|head\s+of|"
    r"practice\s+head|country\s+head|board\s+member|"
    r"principal|staff\s+\w+|distinguished"
    r")\b",
    re.I,
)

_MONTH = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


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


def _parse_month_year(token: str) -> Optional[Tuple[int, int]]:
    """Parse '2019', 'Mar 2019', 'March 2019' → (year, month)."""
    t = (token or "").strip().lower()
    if not t or t in {"present", "current", "now", "oggi", "attuale", "heute"}:
        return None
    m = re.match(r"([a-z]+)\.?\s+(\d{4})$", t)
    if m and m.group(1) in _MONTH:
        return int(m.group(2)), _MONTH[m.group(1)]
    m = re.match(r"(\d{4})$", t)
    if m:
        return int(m.group(1)), 1
    m = re.match(r"(\d{1,2})[/-](\d{4})$", t)
    if m:
        return int(m.group(2)), max(1, min(12, int(m.group(1))))
    m = re.match(r"(\d{4})[/-](\d{1,2})$", t)
    if m:
        return int(m.group(1)), max(1, min(12, int(m.group(2))))
    return None


def _years_from_month_intervals(intervals: Iterable[Tuple[int, int]]) -> Optional[float]:
    """Merge inclusive month intervals and return unique worked years."""
    valid = sorted((start, end) for start, end in intervals if end >= start)
    if not valid:
        return None
    merged: List[List[int]] = []
    for start_month, end_month in valid:
        # End months are inclusive on LinkedIn-style employment timelines.
        exclusive_end = end_month + 1
        if not merged or start_month > merged[-1][1]:
            merged.append([start_month, exclusive_end])
        else:
            merged[-1][1] = max(merged[-1][1], exclusive_end)
    months = sum(end - start for start, end in merged)
    if months < 6:
        return None
    years = round(months / 12.0, 1)
    return years if years <= 50 else None


def estimate_years_from_career_dates(*parts: str) -> Optional[float]:
    """Estimate unique worked time from all job date ranges in profile text.

    Examples matched:
      Mar 2019 - Oct 2024
      2015 – Present
      2012-2018
    """
    blob = " ".join(p for p in parts if p)
    if not blob:
        return None

    # Normalize dashes
    text = blob.replace("—", "-").replace("–", "-").replace("−", "-")
    now = datetime.now(timezone.utc)
    intervals: List[Tuple[int, int]] = []

    range_re = re.compile(
        r"(?P<start>(?:[A-Za-z]{3,9}\.?\s+)?\d{4}|\d{1,2}[/-]\d{4})"
        r"\s*-\s*"
        r"(?P<end>Present|Current|Now|Oggi|Attuale|Heute|(?:[A-Za-z]{3,9}\.?\s+)?\d{4}|\d{1,2}[/-]\d{4})",
        re.I,
    )
    for m in range_re.finditer(text):
        start = _parse_month_year(m.group("start"))
        end_raw = m.group("end")
        if re.match(r"^(present|current|now|oggi|attuale|heute)$", end_raw.strip(), re.I):
            end = (now.year, now.month)
        else:
            end = _parse_month_year(end_raw)
        if not start:
            continue
        if not end:
            end = (now.year, now.month)
        # Ignore nonsense / far-future
        if start[0] < 1975 or start[0] > now.year + 1:
            continue
        if end[0] < start[0]:
            continue
        start_month = start[0] * 12 + start[1]
        end_month = end[0] * 12 + end[1]
        if end_month >= start_month:
            intervals.append((start_month, end_month))

    return _years_from_month_intervals(intervals)


def estimate_years_from_experience_rows(rows: Iterable[Any]) -> Optional[float]:
    """Calculate unique worked time from structured ORM objects or dictionaries."""
    now = datetime.now(timezone.utc)
    intervals: List[Tuple[int, int]] = []
    for row in rows:
        getter = row.get if isinstance(row, dict) else lambda key, default=None: getattr(row, key, default)
        start = _parse_month_year(str(getter("start_date") or ""))
        if not start:
            continue
        is_current = bool(getter("is_current", False))
        end_raw = str(getter("end_date") or "").strip()
        if is_current or end_raw.lower() in {"present", "current", "now"}:
            end = (now.year, now.month)
        else:
            end = _parse_month_year(end_raw)
        if not end or start[0] < 1975 or start[0] > now.year + 1 or end < start:
            continue
        intervals.append((start[0] * 12 + start[1], end[0] * 12 + end[1]))
    return _years_from_month_intervals(intervals)


def estimate_years_from_text(*parts: str) -> Optional[float]:
    """Best-effort years estimate from explicit phrases and/or career date spans.

    Date ranges are preferred because they can represent multiple positions.
    Explicit claims are used only when no usable career ranges are available.
    """
    blob = " ".join(p for p in parts if p).lower()
    if not blob:
        return None

    explicit: Optional[float] = None
    patterns = [
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:exp|experience)",
        r"(?:experience|exp)[:\s]+(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)",
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:in|as|with)",
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+\d+\s*(?:months?|mos?)",
        r"\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
    ]
    found: List[float] = []
    for pat in patterns:
        for m in re.finditer(pat, blob):
            try:
                value = float(m.group(1))
                if 0 <= value <= 60:
                    found.append(value)
            except ValueError:
                continue
    if found:
        # Prefer the largest explicit claim (seniors often list "15+ years")
        explicit = max(found)

    career = estimate_years_from_career_dates(*parts)
    if career is not None:
        return career
    return explicit


def title_implies_seniority(title: Optional[str]) -> bool:
    if not title:
        return False
    return bool(_SENIOR_TITLE_RE.search(title))


def band_is_configured(exp_min: Optional[int], exp_max: Optional[int]) -> bool:
    return exp_min is not None or exp_max is not None


def experience_within_range(
    *,
    years: Optional[float],
    exp_min: Optional[int],
    exp_max: Optional[int],
    title: Optional[str] = None,
    reject_unknown_senior: bool = True,
    reject_unknown: bool = False,
) -> bool:
    """Return False when the candidate is clearly outside the hunt experience band.

    P0: when ``reject_unknown`` is True and a band is configured, unknown years
    are treated as a hard fail (do not add to pipeline).
    """
    if years is not None:
        try:
            y = float(years)
        except (TypeError, ValueError):
            y = None
        else:
            if y < 0 or y > 60:
                y = None
            else:
                if exp_min is not None and y < float(exp_min):
                    return False
                if exp_max is not None and y > float(exp_max):
                    return False
                return True

    # Unknown years
    if reject_unknown and band_is_configured(exp_min, exp_max):
        return False

    # Unknown years: still reject obvious leadership titles when a modest max is set
    if reject_unknown_senior and exp_max is not None and exp_max <= 10:
        if title_implies_seniority(title):
            return False

    return True
