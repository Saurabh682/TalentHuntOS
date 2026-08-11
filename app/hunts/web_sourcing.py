"""Free web sourcing for Talent Hunts (LinkedIn + Naukri via DuckDuckGo, no paid APIs)."""

from __future__ import annotations

import logging
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.infrastructure.db import SessionFactory
from app.config.constants import MAX_SOURCING_TARGET
from app.candidates.service import create_candidate, add_candidate_tag
from app.candidates.models import Candidate, CandidateTag
from app.hunts.pipeline import add_candidate_to_hunt
from app.hunts.models import TalentHunt, HuntCandidate

logger = logging.getLogger("talenthunt.hunts.web_sourcing")

HUNT_TAG_COLOR = "#19d3c5"
PLATFORM_COLORS = {
    "linkedin": "#0A66C2",
    "naukri": "#2557A7",
    "github": "#24292F",
    "behance": "#1769FF",
    "artstation": "#13AFF0",
    "dribbble": "#EA4C89",
}
DEFAULT_SOURCING_BUDGET_SEC = 180.0
PROFILE_SCAN_TIMEOUT_MS = 10_000
PROFILE_CALL_BUDGET_SEC = 16.0
AI_VERIFY_BUDGET_SEC = 12.0
DDG_QUERY_BUDGET_SEC = 6.0
DDG_BACKEND_TIMEOUT_SEC = 4.0
MAX_CONSECUTIVE_SEARCH_FAILURES = 3
SEARCH_CACHE_TTL_SEC = 6 * 60 * 60
SEARCH_CACHE_STALE_SEC = 7 * 24 * 60 * 60
_search_cache_lock = threading.Lock()
SEARCH_WORKERS = 3
SUPPORTED_SOURCING_PLATFORMS = (
    "linkedin",
    "naukri",
    "github",
    "behance",
    "artstation",
    "dribbble",
)


def normalize_source_platforms(value: Any = None) -> List[str]:
    """Normalize user/config platform input while preserving a stable search order."""
    if value is None:
        return list(SUPPORTED_SOURCING_PLATFORMS)
    if isinstance(value, str):
        raw = re.split(r"[,;|\s]+", value.lower())
    else:
        raw = [str(item).lower() for item in value]
    aliases = {
        "linkedin.com": "linkedin",
        "naukri.com": "naukri",
        "github.com": "github",
        "behance.net": "behance",
        "artstation.com": "artstation",
        "dribbble.com": "dribbble",
    }
    requested = {aliases.get(item.strip(), item.strip()) for item in raw if item.strip()}
    selected = [platform for platform in SUPPORTED_SOURCING_PLATFORMS if platform in requested]
    return selected or list(SUPPORTED_SOURCING_PLATFORMS)


def _search_cache_path() -> Path:
    from app.config.settings import DATA_DIR

    return DATA_DIR / "sourcing_search_cache.json"


def _query_cache_key(query: str) -> str:
    return " ".join((query or "").lower().split())


def _read_cached_search(
    query: str,
    *,
    max_results: int,
    max_age_sec: float = SEARCH_CACHE_TTL_SEC,
) -> List[Dict[str, str]]:
    path = _search_cache_path()
    with _search_cache_lock:
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError, TypeError):
            return []
    entry = raw.get(_query_cache_key(query)) if isinstance(raw, dict) else None
    if not isinstance(entry, dict):
        return []
    try:
        age = time.time() - float(entry.get("saved_at") or 0)
    except (TypeError, ValueError):
        return []
    if age < 0 or age > max_age_sec:
        return []
    hits = entry.get("hits")
    if not isinstance(hits, list):
        return []
    return [hit for hit in hits if isinstance(hit, dict)][:max_results]


def _write_cached_search(query: str, hits: List[Dict[str, str]]) -> None:
    if not hits:
        return
    path = _search_cache_path()
    with _search_cache_lock:
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError, TypeError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        cutoff = time.time() - SEARCH_CACHE_STALE_SEC
        kept: Dict[str, Dict[str, Any]] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            try:
                saved_at = float(value.get("saved_at") or 0)
            except (TypeError, ValueError):
                continue
            if saved_at >= cutoff:
                kept[key] = value
        raw = kept
        raw[_query_cache_key(query)] = {"saved_at": time.time(), "hits": hits[:20]}
        if len(raw) > 250:
            newest = sorted(
                raw.items(),
                key=lambda item: float(item[1].get("saved_at") or 0),
                reverse=True,
            )[:250]
            raw = dict(newest)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            temp.replace(path)
        except OSError:
            logger.debug("Could not persist sourcing search cache", exc_info=True)


def _run_cancellable(
    call,
    *,
    job_id: Optional[str],
    timeout_sec: Optional[float] = None,
    poll_sec: float = 0.1,
):
    """Run a blocking call with prompt cancellation and an optional hard deadline."""
    import threading
    from app.hunts import sourcing_jobs

    box: Dict[str, Any] = {}

    def _run() -> None:
        try:
            box["value"] = call()
        except Exception as exc:
            box["error"] = exc

    worker = threading.Thread(target=_run, daemon=True, name="sourcing-blocking-call")
    worker.start()
    deadline = time.monotonic() + timeout_sec if timeout_sec else None
    while worker.is_alive():
        if sourcing_jobs.should_cancel(job_id):
            return None, True
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError(f"Sourcing integration timed out after {timeout_sec:.0f}s")
        worker.join(timeout=poll_sec)
    if "error" in box:
        raise box["error"]
    return box.get("value"), False


def _ddg_search(
    query: str,
    max_results: int = 8,
    *,
    timeout_sec: float = 25.0,
    job_id: Optional[str] = None,
) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """Run a free DuckDuckGo search; return (hits, error).

    error is set when every backend failed — empty hits with error=None means a real empty result set.
    Hard-timeout so a hung DDG call cannot freeze the orange banner forever.
    """
    cached = _read_cached_search(query, max_results=max_results)
    if cached:
        logger.info("[sourcing] search cache hit for %r", query)
        return cached, None

    box: Dict[str, Any] = {}

    def _run() -> None:
        try:
            box["result"] = _ddg_search_inner(query, max_results=max_results)
        except Exception as exc:
            box["result"] = ([], str(exc))

    t = threading.Thread(target=_run, daemon=True, name="ddg-search")
    t.start()
    from app.hunts import sourcing_jobs

    deadline = time.time() + timeout_sec
    while t.is_alive() and time.time() < deadline:
        if sourcing_jobs.should_cancel(job_id):
            return [], "cancelled"
        t.join(timeout=0.1)
    if t.is_alive():
        msg = f"DuckDuckGo search timed out after {timeout_sec:.0f}s"
        logger.warning("%s for query %r", msg, query)
        stale = _read_cached_search(
            query,
            max_results=max_results,
            max_age_sec=SEARCH_CACHE_STALE_SEC,
        )
        if stale:
            return stale, None
        return [], msg
    result = box.get("result") or ([], "search returned nothing")
    hits, error = result
    if hits and not error:
        _write_cached_search(query, hits)
    elif error:
        stale = _read_cached_search(
            query,
            max_results=max_results,
            max_age_sec=SEARCH_CACHE_STALE_SEC,
        )
        if stale:
            logger.warning("[sourcing] provider failed; using stale cache for %r", query)
            return stale, None
    return hits, error


def _ddg_search_inner(query: str, max_results: int = 8) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """Search explicit DDGS providers instead of its slow ``auto`` engine sweep."""
    results: List[Dict[str, str]] = []
    errors: List[str] = []

    def _normalize(items) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            out.append({
                "title": str(item.get("title") or ""),
                "link": str(item.get("href") or item.get("link") or ""),
                "snippet": str(item.get("body") or item.get("snippet") or ""),
            })
        return out

    # ``auto`` starts with several low-signal engines and can wait on all of them.
    # Brave + DuckDuckGo return profile results directly and obey a short timeout.
    try:
        from ddgs import DDGS  # type: ignore
        with DDGS(timeout=DDG_BACKEND_TIMEOUT_SEC) as client:
            results = _normalize(client.text(
                query,
                max_results=max_results,
                backend="brave,yahoo,yandex,duckduckgo",
                region="in-en",
                safesearch="moderate",
            ))
        if results:
            return results, None
    except Exception as exc:
        errors.append(f"ddgs: {exc}")
        logger.debug("ddgs search failed: %s", exc)

    if errors and not results:
        return [], errors[0]
    return results, None


def _search_queries_concurrently(
    queries: List[str],
    *,
    max_results: int,
    timeout_sec: float,
    job_id: Optional[str],
) -> Dict[str, Tuple[List[Dict[str, str]], Optional[str]]]:
    """Fan out independent source queries while keeping one bounded search job."""
    if not queries:
        return {}
    results: Dict[str, Tuple[List[Dict[str, str]], Optional[str]]] = {}
    for offset in range(0, len(queries), SEARCH_WORKERS):
        batch = queries[offset:offset + SEARCH_WORKERS]
        executor = ThreadPoolExecutor(
            max_workers=len(batch),
            thread_name_prefix="talent-source",
        )
        futures = {
            query: executor.submit(
                _ddg_search,
                query,
                max_results=max_results,
                timeout_sec=timeout_sec,
                job_id=job_id,
            )
            for query in batch
        }
        try:
            for query, future in futures.items():
                try:
                    results[query] = future.result(timeout=timeout_sec + 1.0)
                except Exception as exc:
                    results[query] = ([], str(exc))
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        if all(error for _, error in (results[query] for query in batch)):
            break
    return results


def _detect_platform(url: str, title: str = "") -> str:
    hay = f"{url} {title}".lower()
    if "linkedin.com" in hay:
        return "linkedin"
    if "naukri.com" in hay:
        return "naukri"
    if "github.com" in hay:
        return "github"
    if "behance.net" in hay:
        return "behance"
    if "artstation.com" in hay:
        return "artstation"
    if "dribbble.com" in hay:
        return "dribbble"
    return "web"


def _is_profile_hit(link: str, title: str) -> bool:
    """Skip job boards / articles / aggregate pages; keep real person profile URLs only."""
    url = (link or "").strip().lower().split("?")[0].split("#")[0]
    title_l = (title or "").lower()
    hay = f"{url} {title_l}"

    # Hard reject non-profile LinkedIn surfaces (advice articles were slipping through)
    reject_bits = (
        "/jobs/",
        "/job/",
        "/advice/",
        "/pulse/",
        "/posts/",
        "/company/",
        "/school/",
        "/learning/",
        "/newsletter/",
        "job-listings",
        "job search",
        "jobs in ",
        "hiring an ",
        " vacancies",
        "vacancy",
        "we are hiring",
        "jobsdb",
        "smarthire",
        "indeed.com",
        "glassdoor",
        "linkedin.com/jobs",
        "naukri.com/job-listings",
        "naukrigulf",
        "ambitionbox",
        "shine.com/jobs",
        "salary range",
        "key responsibilities",
        "struggling to",
        "/dir/",
        "/search/",
    )
    if any(x in hay for x in reject_bits):
        return False

    # LinkedIn: ONLY /in/<slug> (with optional country subdomain)
    if "linkedin.com" in url:
        return bool(re.search(r"linkedin\.com/(?:[a-z]{2}/)?in/[\w%-]+/?$", url))

    # Naukri people profiles
    if "naukri.com" in url:
        if any(x in url for x in ("/mnjuser/profile", "/resume-display", "/recruiters/", "/job-listings")):
            return "/mnjuser/profile" in url or "/resume-display" in url
        # Avoid bare naukri.com category pages
        return False

    # GitHub account roots only; repositories, issues, organizations and search are not people.
    if "github.com" in url:
        path = re.sub(r"^https?://(?:www\.)?github\.com/", "", url).strip("/")
        reserved = {"about", "apps", "collections", "enterprise", "explore", "features", "issues", "marketplace", "orgs", "pricing", "search", "settings", "site", "sponsors", "topics"}
        return bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?", path)) and path not in reserved

    if "behance.net" in url:
        path = re.sub(r"^https?://(?:www\.)?behance\.net/", "", url).strip("/")
        return bool(path and "/" not in path and path not in {"galleries", "joblist", "search"})

    if "artstation.com" in url:
        path = re.sub(r"^https?://(?:www\.)?artstation\.com/", "", url).strip("/")
        return bool(path and "/" not in path and path not in {"artwork", "jobs", "marketplace", "search"})

    if "dribbble.com" in url:
        path = re.sub(r"^https?://(?:www\.)?dribbble\.com/", "", url).strip("/")
        return bool(path and "/" not in path and path not in {"designers", "jobs", "search", "shots"})

    return False


def _parse_name_title(title: str, snippet: str) -> Tuple[str, str, str]:
    """Extract rough name, job title, company from a search result title/snippet."""
    clean = re.sub(
        r"\s*[|\-–—]\s*(LinkedIn|Naukri\.com|Indeed|Google|Professional Profile).*$",
        "",
        title,
        flags=re.I,
    ).strip()
    # "Name - India" / "Name - City, Country"
    clean = re.sub(r"\s*[|\-–—]\s*[A-Za-z].*(India|Remote).*$", "", clean, flags=re.I).strip() or clean
    parts = re.split(r"\s*[|\-–—•]\s*", clean)
    parts = [p.strip() for p in parts if p.strip()]

    name = parts[0] if parts else "Unknown Candidate"
    # Heuristic: person names are usually 2–4 words without digits
    if not re.match(r"^[A-Za-z][A-Za-z.'\-\s]{1,60}$", name) or len(name.split()) > 5:
        m = re.search(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", snippet or "")
        name = m.group(1) if m else (parts[0] if parts else "Unknown Candidate")

    job_title = parts[1] if len(parts) > 1 else ""
    company = parts[2] if len(parts) > 2 else ""

    if not job_title and snippet:
        m2 = re.search(
            r"(?:as|is|working as)\s+(?:a|an)?\s*([A-Za-z0-9 /&+\-]{3,60})",
            snippet,
            re.I,
        )
        if m2:
            job_title = m2.group(1).strip()
        else:
            # Snippet often starts with role: "Business Development Executive — ..."
            m3 = re.match(r"^([A-Za-z][A-Za-z0-9 /&+\-]{2,50})\s*[—\-–|]", snippet.strip())
            if m3:
                job_title = m3.group(1).strip()

    return name[:120], job_title[:120], company[:120]


def _looks_like_person(name: str) -> bool:
    if not name or name.lower() in {"unknown candidate", "linkedin", "naukri"}:
        return False
    low = name.lower()
    if any(x in low for x in ("jobs", "job ", "hiring", "vacancy", "vacancies", "youtube", "booster")):
        return False
    words = [w for w in re.split(r"[\s,]+", name) if w]
    if len(words) < 2 or len(words) > 5:
        return False
    if any(ch.isdigit() for ch in name):
        return False
    # Reject titles that look like role phrases, not people
    if sum(1 for w in words if w[:1].isupper()) < 2:
        return False
    return True


def _role_relevance(role: str, title: str, snippet: str, job_title: str) -> bool:
    """Require at least one meaningful role token in the hit text."""
    role_tokens = [w for w in re.split(r"[^a-z0-9]+", (role or "").lower()) if len(w) > 2]
    # Drop ultra-generic tokens
    role_tokens = [w for w in role_tokens if w not in {"india", "remote", "senior", "junior", "lead"}]
    if not role_tokens:
        return True
    blob = f"{title} {snippet} {job_title}".lower()
    hits = sum(1 for t in role_tokens if t in blob)
    # Single distinctive token (e.g. "spine", "naukri-style roles) is enough; multi-word roles need 1+
    return hits >= 1


def _purge_out_of_band_enrollments(
    hunt_id: int,
    *,
    exp_min: Optional[int],
    exp_max: Optional[int],
) -> int:
    """Remove hunt enrollments that fail the experience band (P0 self-heal).

    Uses stored experience_years and/or years estimated from profile text.
    When a band is set, unknown years are treated as out-of-band.
    """
    from app.hunts.experience import (
        estimate_years_from_text,
        experience_within_range,
        band_is_configured,
    )

    if not band_is_configured(exp_min, exp_max):
        return 0

    removed = 0
    with SessionFactory() as db:
        rows = list(
            db.scalars(
                select(HuntCandidate)
                .options(selectinload(HuntCandidate.candidate).selectinload(Candidate.profile))
                .where(HuntCandidate.hunt_id == hunt_id)
            ).all()
        )
        for hc in rows:
            cand = hc.candidate
            years = None
            title = hc.current_title
            if cand:
                years = cand.experience_years
                title = cand.current_title or title
                summary = ""
                resume = ""
                if cand.profile:
                    summary = cand.profile.summary or ""
                    resume = cand.profile.resume_text or ""
                if years is None:
                    years = estimate_years_from_text(
                        title or "",
                        summary,
                        resume,
                        hc.ai_summary or "",
                    )
            ok = experience_within_range(
                years=years,
                exp_min=exp_min,
                exp_max=exp_max,
                title=title,
                reject_unknown=True,
            )
            if ok:
                continue
            logger.info(
                "[sourcing] purge out-of-band hc=%s name=%s years=%s title=%s band=%s-%s",
                hc.id,
                hc.full_name,
                years,
                title,
                exp_min,
                exp_max,
            )
            # Keep Candidates list in sync — drop Hunt: tag when removing from Kanban
            if cand:
                from app.hunts.pipeline import strip_hunt_tag
                from app.hunts.models import TalentHunt as _TH
                hunt_row = db.get(_TH, hunt_id)
                if hunt_row:
                    strip_hunt_tag(db, cand.id, hunt_row.title)
            db.delete(hc)
            removed += 1
        if removed:
            db.commit()
    return removed


def _purge_wrong_location_enrollments(hunt_id: int, *, target_location: str) -> int:
    """Remove enrollments whose profile location clearly fails the hunt geo filter."""
    from app.hunts.location import location_matches_target
    from app.hunts.pipeline import strip_hunt_tag
    from app.hunts.models import TalentHunt as _TH

    removed = 0
    with SessionFactory() as db:
        hunt_row = db.get(_TH, hunt_id)
        rows = list(
            db.scalars(
                select(HuntCandidate)
                .options(selectinload(HuntCandidate.candidate).selectinload(Candidate.profile))
                .where(HuntCandidate.hunt_id == hunt_id)
            ).all()
        )
        for hc in rows:
            cand = hc.candidate
            cand_loc = (cand.location if cand else None) or hc.location
            url = (cand.linkedin_url if cand else None) or hc.linkedin_url or ""
            page = ""
            if cand and cand.profile:
                page = f"{cand.profile.summary or ''} {cand.profile.resume_text or ''}"
            ok, reason = location_matches_target(
                candidate_location=cand_loc,
                target_location=target_location,
                profile_url=url,
                page_text=page,
                reject_unknown=True,
            )
            if ok:
                continue
            logger.info(
                "[sourcing] purge wrong-location hc=%s name=%s loc=%s reason=%s want=%s",
                hc.id,
                hc.full_name,
                cand_loc,
                reason,
                target_location,
            )
            if cand and hunt_row:
                strip_hunt_tag(db, cand.id, hunt_row.title)
            db.delete(hc)
            removed += 1
        if removed:
            db.commit()
    return removed


def _build_sourcing_queries(
    *,
    role_label: str,
    skill_bits: List[str],
    primary: str,
    exp_clause: str,
    loc: str,
    round_idx: int = 0,
    platforms: Any = None,
) -> List[str]:
    """Build balanced source queries; later rounds use alternate phrasings."""
    role = (role_label or "Professional").strip()
    location = (loc or "India").strip() or "India"
    exp = (exp_clause or "").strip()
    skills = [s for s in skill_bits if s][:6]
    prim = (primary or role).strip()

    selected = normalize_source_platforms(platforms)
    source_queries: Dict[str, List[str]] = {
        "linkedin": [
            f'"{role}" {prim} {exp} {location} site:linkedin.com/in',
            f"{role} {exp} {location} site:in.linkedin.com/in",
            f'"{role}" {location} profile site:linkedin.com/in',
        ],
        "naukri": [
            f'"{role}" {prim} {exp} {location} site:naukri.com',
            f'"{role}" {location} resume site:naukri.com',
            f"{role} {exp} {location} profile site:naukri.com",
        ],
        "github": [
            f'"{role}" {prim} {location} site:github.com',
            f'"{role}" {location} portfolio site:github.com',
        ],
        "behance": [
            f'"{role}" {prim} {location} site:behance.net',
            f'"{role}" {location} portfolio site:behance.net',
        ],
        "artstation": [
            f'"{role}" {prim} {location} site:artstation.com',
            f'"{role}" {location} portfolio site:artstation.com',
        ],
        "dribbble": [
            f'"{role}" {prim} {location} site:dribbble.com',
            f'"{role}" {location} designer site:dribbble.com',
        ],
    }
    for platform in selected:
        for skill in skills[:2]:
            domain = {
                "linkedin": "linkedin.com/in",
                "naukri": "naukri.com",
                "github": "github.com",
                "behance": "behance.net",
                "artstation": "artstation.com",
                "dribbble": "dribbble.com",
            }[platform]
            source_queries[platform].append(
                f'"{role}" "{skill}" {exp} {location} site:{domain}'
            )
        if round_idx >= 1:
            domain = source_queries[platform][0].rsplit("site:", 1)[-1]
            source_queries[platform].append(
                f'"{role}" {prim} India OR remote {location} site:{domain}'
            )
        if round_idx >= 2:
            domain = source_queries[platform][0].rsplit("site:", 1)[-1]
            source_queries[platform].append(
                f'"{role}" candidate {exp} Bangalore OR Mumbai OR Noida OR Pune site:{domain}'
            )

    # Interleave sources so one prolific platform cannot consume the whole scan budget.
    base: List[str] = []
    longest = max((len(source_queries[p]) for p in selected), default=0)
    for index in range(longest):
        for platform in selected:
            variants = source_queries[platform]
            if index < len(variants):
                base.append(variants[index])

    # Unique, cleaned
    seen: set[str] = set()
    out: List[str] = []
    for q in base:
        cleaned = " ".join(q.split())
        key = cleaned.lower()
        if key in seen or len(cleaned) < 12:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def source_candidates_for_hunt(
    hunt_id: int,
    *,
    role: str,
    skills: str = "",
    location: str = "India",
    hunt_title: Optional[str] = None,
    max_per_query: int = 6,
    experience_years_min: Optional[int] = None,
    experience_years_max: Optional[int] = None,
    enrich_pages: bool = True,
    verify_with_ai: bool = True,
    job_id: Optional[str] = None,
    target_added: Optional[int] = None,
    time_budget_sec: float = DEFAULT_SOURCING_BUDGET_SEC,
    approval_required: bool = False,
    platforms: Any = None,
) -> Dict[str, Any]:
    """Discover profiles across sources and queue them for recruiter approval.

    ``target_added`` is the desired review-queue size. Search only stores lightweight
    evidence; canonical Candidate and HuntCandidate rows are created after approval.
    ``approval_required=False`` preserves the legacy direct-import path for maintenance.

    enrich_pages: open each /in profile in Playwright and read text (default True).
    verify_with_ai: cross-check role + experience band with the LLM after page read.
    job_id: optional sourcing_jobs id for progress/cancel.
    """
    from app.hunts.experience import (
        estimate_years_from_text,
        experience_within_range,
        title_implies_seniority,
        band_is_configured,
    )
    from app.hunts.location import (
        extract_location_from_text,
        location_matches_target,
        normalize_candidate_location,
        linkedin_host_country,
    )
    from app.hunts import sourcing_jobs

    started_monotonic = time.monotonic()
    budget_sec = max(30.0, min(float(time_budget_sec or DEFAULT_SOURCING_BUDGET_SEC), 600.0))
    deadline = started_monotonic + budget_sec

    def _remaining_sec() -> float:
        return max(0.0, deadline - time.monotonic())

    def _time_exhausted() -> bool:
        return _remaining_sec() <= 0.0

    loc = (location or "India").strip() or "India"
    role_label = (role or "").strip() or "Professional"
    skill_bits = [s.strip() for s in (skills or "").split(",") if s.strip()]
    primary = skill_bits[0] if skill_bits else role_label

    with SessionFactory() as db:
        hunt = db.get(TalentHunt, hunt_id)
        if not hunt:
            return {"status": "error", "error": f"Hunt {hunt_id} not found", "added": 0}
        title_label = hunt_title or hunt.title
        hunt_tag = f"Hunt: {title_label}"
        sc = hunt.search_config
        if sc:
            if experience_years_min is None:
                experience_years_min = sc.experience_years_min
            if experience_years_max is None:
                experience_years_max = sc.experience_years_max
            if not skill_bits and sc.required_skills:
                skill_bits = [s.strip() for s in sc.required_skills.split(",") if s.strip()]
                primary = skill_bits[0] if skill_bits else role_label
            if platforms is None and sc.target_platforms:
                platforms = sc.target_platforms
            # Prefer hunt search_config locations when caller left default
            if sc.locations and (not location or location.strip().lower() == "india"):
                # Only override if hunt has explicit locations and caller used default India
                # Actually: always prefer hunt.location / sc.locations for filter target
                pass
        hunt_location = (hunt.location or "").strip() or loc
        if sc and sc.locations:
            hunt_location = (sc.locations or hunt_location).strip() or hunt_location

    # P0: when hunt has an experience band, unknown years = reject
    require_years = band_is_configured(experience_years_min, experience_years_max)

    # Discovery stays cheap. Playwright and AI deep inspection belong to approval.
    page_reads_enabled = bool(enrich_pages and not approval_required)
    if approval_required:
        verify_with_ai = False
    session_issue: Optional[str] = None
    if page_reads_enabled:
        try:
            from app.communications.service import get_decrypted_cookies_for_platform

            with SessionFactory() as db:
                linkedin_cookies = get_decrypted_cookies_for_platform(db, "linkedin") or []
            if not linkedin_cookies:
                page_reads_enabled = False
                session_issue = (
                    "LinkedIn login is unavailable or expired. Reconnect it in Settings; "
                    "this run used fast search-result snippets only."
                )
        except Exception as exc:
            page_reads_enabled = False
            session_issue = f"LinkedIn login could not be loaded ({exc}); snippets only."

    # Drop existing pipeline people who no longer fit the band (self-heal)
    purged = 0 if approval_required else _purge_out_of_band_enrollments(
        hunt_id, exp_min=experience_years_min, exp_max=experience_years_max
    )
    if purged:
        logger.info(
            "[sourcing] purged %s out-of-band enrollments from hunt=%s (band %s-%s)",
            purged,
            hunt_id,
            experience_years_min,
            experience_years_max,
        )

    loc_purged = 0 if approval_required else _purge_wrong_location_enrollments(
        hunt_id, target_location=hunt_location
    )
    if loc_purged:
        logger.info(
            "[sourcing] purged %s wrong-location enrollments from hunt=%s (want %s)",
            loc_purged,
            hunt_id,
            hunt_location,
        )

    exp_clause = ""
    if experience_years_min is not None and experience_years_max is not None:
        exp_clause = f"{experience_years_min}-{experience_years_max} years"
    elif experience_years_min is not None:
        exp_clause = f"{experience_years_min}+ years"
    elif experience_years_max is not None:
        exp_clause = f"under {experience_years_max} years"

    fill_to = int(target_added or 25)
    fill_to = max(1, min(fill_to, MAX_SOURCING_TARGET))

    def _current_count() -> int:
        with SessionFactory() as db:
            if approval_required:
                from app.candidates.discovery import discovery_counts

                return discovery_counts(db, hunt_id=hunt_id).get("reviewable", 0)
            from app.hunts.pipeline import list_active_hunt_candidates
            return len(list_active_hunt_candidates(db, hunt_id))

    already_in = _current_count()
    need = max(0, fill_to - already_in)
    if need == 0:
        noun = "Review queue" if approval_required else "Pipeline"
        msg = f"{noun} already has {already_in}/{fill_to} - nothing to add."
        logger.info("[sourcing] %s", msg)
        if job_id:
            sourcing_jobs.finish_job(job_id, status="done", message=msg)
        return {
            "status": "success",
            "hunt_id": hunt_id,
            "scanned": 0,
            "added": 0,
            "goal": fill_to,
            "already_in": already_in,
            "pipeline_count": _current_count() if not approval_required else None,
            "review_count": already_in if approval_required else None,
            "candidates_sourced": 0,
            "message": msg,
        }

    selected_platforms = normalize_source_platforms(platforms)
    queries = _build_sourcing_queries(
        role_label=role_label,
        skill_bits=skill_bits,
        primary=primary,
        exp_clause=exp_clause,
        loc=hunt_location or loc,
        round_idx=0,
        platforms=selected_platforms,
    )

    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    added = 0
    scanned = 0
    skipped_exp = 0
    skipped_ai = 0
    skipped_url = 0
    search_failures = 0
    search_ok = 0
    consecutive_search_failures = 0
    discovery_circuit_open = False
    source_counts: Dict[str, Dict[str, int]] = {
        platform: {"queries": 0, "hits": 0, "profiles": 0, "review": 0, "filtered": 0}
        for platform in selected_platforms
    }
    errors: List[str] = []
    goal = need
    max_scan = min(150, max(60, goal * 6))
    max_rounds = 3
    per_query = max(max_per_query, min(15, 4 + goal // 2))

    logger.info(
        "[sourcing] start hunt=%s role=%r fill_to=%s already=%s need=%s "
        "queries=%s max_scan=%s job=%s",
        hunt_id,
        role_label,
        fill_to,
        already_in,
        need,
        len(queries),
        max_scan,
        job_id,
    )

    if job_id:
        sourcing_jobs.update_job(
            job_id,
            message=(
                f"Finding profiles for review ({already_in}/{fill_to}) for {role_label} "
                f"(have {already_in}, need {need}) · fast scan, up to {int(budget_sec // 60)}m."
                + (" LinkedIn reconnect required; snippets only." if session_issue else "")
            ),
            session_issue=session_issue,
        )

    for round_idx in range(max_rounds):
        if sourcing_jobs.should_cancel(job_id) or _time_exhausted():
            logger.info("[sourcing] cancel requested at round %s", round_idx + 1)
            break
        if added >= goal or scanned >= max_scan:
            break

        if round_idx > 0:
            queries = _build_sourcing_queries(
                role_label=role_label,
                skill_bits=skill_bits,
                primary=primary,
                exp_clause=exp_clause,
                loc=hunt_location or loc,
                round_idx=round_idx,
                platforms=selected_platforms,
            )
            logger.info(
                "[sourcing] round %s/%s — %s new queries (added %s/%s)",
                round_idx + 1,
                max_rounds,
                len(queries),
                added,
                goal,
            )

        if job_id:
            sourcing_jobs.update_job(
                job_id,
                message=f"Searching {len(queries)} source queries with {SEARCH_WORKERS} workers...",
            )
        query_results = _search_queries_concurrently(
            queries,
            max_results=per_query,
            timeout_sec=max(1.0, min(DDG_QUERY_BUDGET_SEC, _remaining_sec())),
            job_id=job_id,
        )

        for qi, query in enumerate(queries, start=1):
            if sourcing_jobs.should_cancel(job_id) or _time_exhausted():
                logger.info("[sourcing] cancel requested before query %s", qi)
                break
            if scanned >= max_scan:
                break
            if job_id:
                sourcing_jobs.update_job(
                    job_id,
                    message=(
                        f"Round {round_idx + 1} · DDG {qi}/{len(queries)} · "
                        f"found {added}/{goal} for review"
                    ),
                    scanned=scanned,
                    added=added,
                )
            logger.info("[sourcing] DDG r%s q%s/%s: %s", round_idx + 1, qi, len(queries), query)
            hits, search_err = query_results.get(query, ([], "search result unavailable"))
            query_platform = next(
                (
                    platform
                    for platform in selected_platforms
                    if {
                        "linkedin": "linkedin.com",
                        "naukri": "naukri.com",
                        "github": "github.com",
                        "behance": "behance.net",
                        "artstation": "artstation.com",
                        "dribbble": "dribbble.com",
                    }[platform] in query.lower()
                ),
                None,
            )
            if query_platform:
                source_counts[query_platform]["queries"] += 1
            if sourcing_jobs.should_cancel(job_id):
                break
            if search_err:
                search_failures += 1
                consecutive_search_failures += 1
                errors.append(f"search_failed: {search_err}")
                logger.warning("[sourcing] query failed: %s", search_err)
                if job_id:
                    sourcing_jobs.update_job(
                        job_id,
                        message=f"Search backend issue on query {qi} — trying next…",
                    )
                if consecutive_search_failures >= MAX_CONSECUTIVE_SEARCH_FAILURES:
                    discovery_circuit_open = True
                    logger.error(
                        "[sourcing] discovery circuit opened after %s consecutive failures",
                        consecutive_search_failures,
                    )
                    if job_id:
                        sourcing_jobs.update_job(
                            job_id,
                            message="Search service unavailable - stopping early instead of waiting.",
                        )
                    break
                continue
            search_ok += 1
            consecutive_search_failures = 0
            if query_platform:
                source_counts[query_platform]["hits"] += len(hits)
            logger.info("[sourcing] query returned %s hits", len(hits))
            for hit in hits:
                if sourcing_jobs.should_cancel(job_id) or _time_exhausted():
                    break
                if scanned >= max_scan:
                    break

                scanned += 1
                title = hit.get("title") or ""
                link = hit.get("link") or ""
                snippet = hit.get("snippet") or ""
                if not _is_profile_hit(link, title):
                    skipped_url += 1
                    continue
                link_key = link.lower().split("?")[0]
                if link_key in seen_urls:
                    continue
                seen_urls.add(link_key)

                platform = _detect_platform(link, title)
                if platform not in selected_platforms:
                    skipped_url += 1
                    continue
                name, job_title, company = _parse_name_title(title, snippet)
                if not _looks_like_person(name):
                    continue
                source_counts[platform]["profiles"] += 1
                raw_match_id: Optional[int] = None
                try:
                    from app.candidates.discovery import record_discovery

                    with SessionFactory() as db:
                        _, raw_match = record_discovery(
                            db,
                            hunt_id=hunt_id,
                            url=link,
                            platform=platform,
                            source_query=query,
                            full_name=name,
                            headline=job_title or title,
                            company=company,
                            snippet=snippet,
                            raw_payload=hit,
                            status="raw",
                        )
                        raw_match_id = raw_match.id
                except Exception as discovery_exc:
                    logger.warning("Could not record raw discovery %s: %s", link, discovery_exc)

                def mark_filtered(reason: str) -> None:
                    if raw_match_id is None:
                        return
                    try:
                        from app.candidates.discovery import set_discovery_status

                        with SessionFactory() as filter_db:
                            set_discovery_status(
                                filter_db,
                                raw_match_id,
                                "filtered",
                                rejection_reason=reason[:255],
                            )
                        source_counts[platform]["filtered"] += 1
                    except Exception as filter_exc:
                        logger.warning("Could not mark raw discovery %s filtered: %s", link, filter_exc)

                if not _role_relevance(role_label, title, snippet, job_title):
                    mark_filtered("Role mismatch in search-result evidence")
                    continue

                est_years = estimate_years_from_text(title, snippet, job_title)
                page_summary = snippet
                page_text = snippet
                profile_location = extract_location_from_text(title, snippet) or linkedin_host_country(link)

                if job_id:
                    sourcing_jobs.update_job(
                        job_id,
                        scanned=scanned,
                        added=added,
                        skipped=skipped_exp + skipped_ai,
                        message=f"Reading profile: {name}… ({added}/{goal} added)",
                    )

                # Open real /in profile in Chromium, expand, read text (+ free local snapshot)
                pending_snapshot = None
                if page_reads_enabled and link and "linkedin.com" in link.lower():
                    try:
                        logger.info("[sourcing] Playwright open: %s (%s)", name, link[:80])
                        from app.browser.page_reader import enrich_profile_from_url
                        enriched, was_cancelled = _run_cancellable(
                            lambda: enrich_profile_from_url(
                                link,
                                headless=True,
                                save_snapshot=False,
                                timeout_ms=PROFILE_SCAN_TIMEOUT_MS,
                                scan_mode=True,
                                cookies=linkedin_cookies,
                            ),
                            job_id=job_id,
                            timeout_sec=max(1.0, min(PROFILE_CALL_BUDGET_SEC, _remaining_sec())),
                        )
                        if was_cancelled:
                            break
                        if not enriched or enriched.get("blocked") or enriched.get("status") != "success":
                            skipped_ai += 1
                            logger.info("Skip %s — page read blocked/failed: %s", link, enriched.get("error"))
                            mark_filtered("Profile page could not be read")
                            continue
                        page_text = enriched.get("text") or ""
                        page_summary = (enriched.get("summary") or page_text or "")[:800]
                        pending_snapshot = enriched.get("snapshot")

                        # Prefer richer estimate from full page (dates + explicit years)
                        page_years = estimate_years_from_text(page_text, title, job_title or "")
                        if page_years is not None:
                            est_years = page_years
                        elif enriched.get("experience_years") is not None:
                            est_years = enriched["experience_years"]
                        if enriched.get("location"):
                            profile_location = enriched["location"]
                        else:
                            profile_location = (
                                extract_location_from_text(page_text, title)
                                or linkedin_host_country(link)
                                or profile_location
                            )
                        if enriched.get("headline"):
                            hl = enriched["headline"]
                            if len(hl) < 120:
                                job_title = job_title or hl
                        if enriched.get("senior_title") and experience_years_max is not None and experience_years_max <= 10:
                            skipped_exp += 1
                            logger.info("[sourcing] skip senior title %s", name)
                            mark_filtered("Title indicates experience above the configured range")
                            continue
                    except Exception as page_exc:
                        logger.warning("Page read failed for %s: %s", link, page_exc)
                        skipped_ai += 1
                        mark_filtered("Profile page read failed")
                        continue

                # Hard location filter (P0: do not stamp hunt country onto foreign profiles)
                loc_ok, loc_reason = location_matches_target(
                    candidate_location=profile_location,
                    target_location=hunt_location,
                    profile_url=link,
                    page_text=page_text,
                    reject_unknown=True,
                )
                if not loc_ok:
                    skipped_url += 1
                    logger.info(
                        "[sourcing] skip location %s loc=%s reason=%s want=%s",
                        name,
                        profile_location,
                        loc_reason,
                        hunt_location,
                    )
                    mark_filtered(f"Location mismatch: {loc_reason}")
                    continue

                cand_location = normalize_candidate_location(
                    extracted=profile_location,
                    profile_url=link,
                )

                # Hard experience band from heuristics / page (P0: unknown years fail when band set)
                if not experience_within_range(
                    years=est_years,
                    exp_min=experience_years_min,
                    exp_max=experience_years_max,
                    title=job_title or title,
                    reject_unknown=require_years,
                ):
                    skipped_exp += 1
                    logger.info(
                        "[sourcing] skip exp-band %s years=%s band=%s-%s title=%s",
                        name,
                        est_years,
                        experience_years_min,
                        experience_years_max,
                        (job_title or title)[:60],
                    )
                    mark_filtered("Experience is outside the configured range or unavailable")
                    continue

                # AI cross-check against role + experience band using full page text
                if verify_with_ai and page_text.strip():
                    if job_id:
                        sourcing_jobs.update_job(job_id, message=f"AI verifying: {name}…")
                    try:
                        from app.hunts.profile_verify import ai_verify_profile
                        verdict, was_cancelled = _run_cancellable(
                            lambda: ai_verify_profile(
                                role=role_label,
                                skills=", ".join(skill_bits) if skill_bits else skills,
                                exp_min=experience_years_min,
                                exp_max=experience_years_max,
                                location=hunt_location,
                                name=name,
                                title=job_title or title,
                                years=est_years,
                                page_text=page_text,
                            ),
                            job_id=job_id,
                            timeout_sec=max(1.0, min(AI_VERIFY_BUDGET_SEC, _remaining_sec())),
                        )
                        if was_cancelled:
                            break
                        if verdict.get("years") is not None:
                            try:
                                est_years = float(verdict["years"])
                            except (TypeError, ValueError):
                                pass
                        if verdict.get("title"):
                            job_title = verdict["title"] or job_title
                        if not verdict.get("pass"):
                            skipped_ai += 1
                            logger.info(
                                "AI reject %s (%s): %s",
                                name,
                                link,
                                verdict.get("reason"),
                            )
                            mark_filtered(f"AI qualification mismatch: {verdict.get('reason') or 'not a fit'}")
                            continue
                        # Re-check band after AI years estimate (fail closed on unknown)
                        if not experience_within_range(
                            years=est_years,
                            exp_min=experience_years_min,
                            exp_max=experience_years_max,
                            title=job_title,
                            reject_unknown=require_years,
                        ):
                            skipped_exp += 1
                            logger.info(
                                "[sourcing] AI-pass but exp-band reject %s years=%s band=%s-%s",
                                name,
                                est_years,
                                experience_years_min,
                                experience_years_max,
                            )
                            mark_filtered("AI evidence places experience outside the configured range")
                            continue
                    except Exception as ver_exc:
                        logger.warning("AI verify error for %s: %s", name, ver_exc)

                key = name.strip().lower()
                if key in seen_names and not approval_required:
                    continue
                seen_names.add(key)

                if approval_required:
                    if added >= goal:
                        mark_filtered("Review target was already filled; retained in the Common Pool")
                        continue
                    try:
                        from app.candidates.discovery import record_discovery

                        with SessionFactory() as db:
                            _, shortlisted_match = record_discovery(
                                db,
                                hunt_id=hunt_id,
                                url=link,
                                platform=platform,
                                source_query=query,
                                full_name=name,
                                headline=job_title or title,
                                company=company,
                                location=cand_location,
                                experience_years=est_years,
                                snippet=page_summary,
                                raw_payload=hit,
                                status="shortlisted",
                                match_score=72.0,
                            )
                        if not getattr(shortlisted_match, "was_newly_shortlisted", False):
                            logger.info("[sourcing] already queued for review: %s", link)
                            continue
                        added += 1
                        source_counts[platform]["review"] += 1
                        if job_id:
                            sourcing_jobs.update_job(
                                job_id,
                                added=added,
                                scanned=scanned,
                                skipped=skipped_exp + skipped_ai + skipped_url,
                                message=f"Found {added}/{goal} for review: {name}",
                            )
                    except Exception as discovery_exc:
                        logger.error("Failed to shortlist discovery %r: %s", title, discovery_exc)
                        errors.append(str(discovery_exc))
                    continue

                try:
                    with SessionFactory() as db:
                        # Skip if same name already exists
                        existing = db.scalars(
                            select(Candidate)
                            .options(selectinload(Candidate.tags))
                            .where(Candidate.full_name.ilike(name.strip()))
                            .limit(1)
                        ).first()

                        # Existing master profile must also fit experience band
                        if existing and not experience_within_range(
                            years=existing.experience_years or est_years,
                            exp_min=experience_years_min,
                            exp_max=experience_years_max,
                            title=existing.current_title or job_title,
                            reject_unknown=require_years,
                        ):
                            skipped_exp += 1
                            continue

                        linkedin_url = link if platform == "linkedin" else None

                        # Existing profile must also fit location
                        if existing:
                            ex_ok, ex_reason = location_matches_target(
                                candidate_location=cand_location or existing.location,
                                target_location=hunt_location,
                                profile_url=linkedin_url or existing.linkedin_url or link,
                                page_text=page_text,
                                reject_unknown=True,
                            )
                            if not ex_ok:
                                skipped_url += 1
                                logger.info(
                                    "[sourcing] skip existing wrong-location %s (%s)",
                                    existing.full_name,
                                    ex_reason,
                                )
                                continue
                            # Correct falsely stamped hunt country
                            if cand_location and (
                                not existing.location
                                or (existing.location or "").strip().lower()
                                == (hunt_location or "").strip().lower()
                            ):
                                from app.candidates.service import update_candidate
                                update_candidate(db, existing.id, location=cand_location)

                        if existing:
                            candidate = existing
                            # Ensure linked to hunt
                            already = db.scalars(
                                select(HuntCandidate).where(
                                    HuntCandidate.hunt_id == hunt_id,
                                    HuntCandidate.candidate_id == candidate.id,
                                ).limit(1)
                            ).first()
                            if not already:
                                add_candidate_to_hunt(
                                    db,
                                    hunt_id=hunt_id,
                                    full_name=candidate.full_name,
                                    candidate_id=candidate.id,
                                    current_title=candidate.current_title or job_title or role_label,
                                    current_company=candidate.current_company or company or None,
                                    location=cand_location or candidate.location,
                                    linkedin_url=candidate.linkedin_url or linkedin_url,
                                    ai_summary=f"Matched to hunt '{title_label}' via free {platform} web search.",
                                    match_score=72.0,
                                    source_platform=platform,
                                    source_query=query,
                                )
                                added += 1
                                if job_id:
                                    sourcing_jobs.update_job(
                                        job_id,
                                        added=added,
                                        scanned=scanned,
                                        skipped=skipped_exp + skipped_ai,
                                        message=f"Added {added}/{goal}: {name}",
                                    )
                        else:
                            # Only store skills evidenced on the page snippet/text — never invent hunt skills as theirs
                            evidenced_skills: List[str] = []
                            blob = f"{page_text} {page_summary} {job_title}".lower()
                            for sk in skill_bits[:12]:
                                if sk and sk.lower() in blob:
                                    evidenced_skills.append(sk)
                            candidate = create_candidate(
                                db,
                                full_name=name.strip(),
                                current_title=job_title or role_label,
                                current_company=company or None,
                                location=cand_location,
                                experience_years=est_years if est_years and est_years > 0 else None,
                                skills=evidenced_skills or None,
                                summary=(page_summary[:400] if page_summary else f"Sourced from {platform} for {title_label}"),
                                linkedin_url=linkedin_url,
                                status="Sourced",
                                tags=[hunt_tag, platform.capitalize()],
                            )
                            if not candidate:
                                continue
                            add_candidate_to_hunt(
                                db,
                                hunt_id=hunt_id,
                                full_name=candidate.full_name,
                                candidate_id=candidate.id,
                                current_title=candidate.current_title,
                                current_company=candidate.current_company,
                                location=candidate.location,
                                linkedin_url=linkedin_url,
                                ai_summary=(
                                    f"Playwright+AI verified for hunt '{title_label}' "
                                    f"({est_years or '?'} yrs)."
                                ),
                                match_score=78.0,
                                source_platform=platform,
                                source_query=query,
                            )
                            added += 1
                            if job_id:
                                sourcing_jobs.update_job(
                                    job_id,
                                    added=added,
                                    scanned=scanned,
                                    skipped=skipped_exp + skipped_ai,
                                    message=f"Added {added}/{goal}: {name}",
                                )

                        # Ensure hunt tag exists even for existing candidates
                        if candidate:
                            db.refresh(candidate)
                            tag_rows = db.scalars(
                                select(CandidateTag).where(CandidateTag.candidate_id == candidate.id)
                            ).all()
                            existing_tags = {t.tag_name.lower() for t in tag_rows}
                            if hunt_tag.lower() not in existing_tags:
                                add_candidate_tag(db, candidate.id, hunt_tag, color=HUNT_TAG_COLOR)
                            plat_label = platform.capitalize()
                            if plat_label.lower() not in existing_tags:
                                add_candidate_tag(
                                    db,
                                    candidate.id,
                                    plat_label,
                                    color=PLATFORM_COLORS.get(platform, "#8da2b2"),
                                )
                            # Persist full page text + move snapshot under cand_{id}
                            if page_text and len(page_text.strip()) > 40:
                                from app.candidates.service import update_candidate
                                profile_kw: dict = {"resume_text": page_text[:50000]}
                                if page_summary:
                                    profile_kw["summary"] = page_summary[:400]
                                update_candidate(db, candidate.id, **profile_kw)
                            if pending_snapshot:
                                try:
                                    from app.browser.snapshots import attach_pending_snapshot_to_candidate
                                    attach_pending_snapshot_to_candidate(
                                        candidate_id=candidate.id,
                                        snapshot_info=pending_snapshot,
                                    )
                                except Exception as snap_exc:
                                    logger.warning(
                                        "Snapshot attach failed for cand %s: %s",
                                        candidate.id,
                                        snap_exc,
                                    )
                except Exception as exc:
                    logger.error("Failed to ingest search hit %r: %s", title, exc)
                    errors.append(str(exc))

        if added >= goal or discovery_circuit_open:
            break

    cancelled = sourcing_jobs.should_cancel(job_id)
    timed_out = _time_exhausted() and not cancelled and added < goal
    final_count = _current_count()
    if cancelled:
        status = "cancelled"
    elif search_ok == 0 and search_failures > 0:
        status = "search_failed"
    elif added == 0 and scanned == 0 and search_ok > 0:
        status = "empty"
    elif added < goal:
        status = "partial"
    else:
        status = "success"

    if status == "search_failed":
        result_message = (
            f"Web search service was unavailable after {search_failures} quick attempts; "
            "the hunt stopped early instead of waiting 3 minutes."
        )
    elif status == "cancelled":
        result_message = (
            f"Cancelled after finding {added} profiles; review queue {final_count}/{fill_to}."
            if approval_required
            else f"Cancelled after adding {added}; pipeline {final_count}/{fill_to}."
        )
    elif status == "success":
        result_message = (
            f"Found {added} profiles for review; queue now {final_count}/{fill_to}."
            if approval_required
            else f"Filled pipeline to {final_count}/{fill_to} (added {added}, scanned {scanned})."
        )
    elif timed_out:
        result_message = (
            f"Fast scan stopped at the {int(budget_sec)}s limit: found {added}, scanned {scanned}, "
            f"{'review queue' if approval_required else 'pipeline'} {final_count}/{fill_to}."
        )
    elif status == "empty":
        result_message = f"Search ran but found no usable profile hits (scanned={scanned})."
    else:
        result_message = (
            f"Partial search: found {added} for review; queue {final_count}/{fill_to} "
            f"(scanned {scanned}, skipped exp {skipped_exp}, location/url {skipped_url})."
            if approval_required
            else f"Partial fill: added {added}; pipeline {final_count}/{fill_to} "
            f"(scanned {scanned}, skipped exp {skipped_exp}, location/url {skipped_url}, AI {skipped_ai})."
        )
    with SessionFactory() as db:
        from app.candidates.discovery import discovery_counts

        raw_counts = discovery_counts(db, hunt_id=hunt_id)
    raw_pool_count = raw_counts.get("raw", 0) + raw_counts.get("filtered", 0)
    source_summary = ", ".join(
        f"{platform.capitalize()} {counts['queries']}q/{counts['hits']} hits/"
        f"{counts['profiles']} profiles/{counts['review']} review"
        for platform, counts in source_counts.items()
    )
    result_message = (
        f"{result_message} Sources checked: {source_summary}. "
        f"Common Pool: {raw_pool_count} retained profile(s)."
    )
    if session_issue:
        result_message = f"{result_message} {session_issue}"

    logger.info(
        "[sourcing] done hunt=%s status=%s added=%s/%s pipeline_now=%s/%s scanned=%s",
        hunt_id,
        status,
        added,
        goal,
        final_count,
        fill_to,
        scanned,
    )

    result = {
        "status": status,
        "hunt_id": hunt_id,
        "scanned": scanned,
        "added": added,
        "discovered": added,
        "goal": fill_to,
        "need": need,
        "pipeline_count": final_count if not approval_required else None,
        "review_count": final_count if approval_required else None,
        "candidates_sourced": added,
        "skipped_exp": skipped_exp,
        "skipped_ai": skipped_ai,
        "skipped_url": skipped_url,
        "search_ok": search_ok,
        "search_failures": search_failures,
        "timed_out": timed_out,
        "time_budget_sec": budget_sec,
        "session_issue": session_issue,
        "exp_min": experience_years_min,
        "exp_max": experience_years_max,
        "queries": len(queries),
        "platforms": selected_platforms,
        "source_counts": source_counts,
        "raw_pool_count": raw_pool_count,
        "errors": errors[:5],
        "message": result_message,
    }
    if job_id:
        sourcing_jobs.update_job(
            job_id,
            scanned=scanned,
            added=added,
            skipped=skipped_exp + skipped_ai + skipped_url,
            timed_out=timed_out,
            session_issue=session_issue,
        )
        sourcing_jobs.finish_job(
            job_id,
            status="cancelled" if cancelled else ("error" if status == "search_failed" else "done"),
            message=result["message"],
            error="; ".join(errors[:2]) if status == "search_failed" else None,
        )
        finished = sourcing_jobs.get_job(job_id) or {}
        result["elapsed_sec"] = finished.get("elapsed_sec")
        result["elapsed_label"] = finished.get("elapsed_label")
        result["message"] = finished.get("message") or result["message"]
        logger.info(
            "[sourcing] job=%s finished in %s",
            job_id,
            finished.get("elapsed_label") or "?",
        )
    return result


def get_hunt_labels_for_candidates(db: Session, candidate_ids: List[int]) -> Dict[int, List[str]]:
    """Map candidate_id -> list of related Talent Hunt titles."""
    if not candidate_ids:
        return {}
    stmt = (
        select(HuntCandidate.candidate_id, TalentHunt.title)
        .join(TalentHunt, TalentHunt.id == HuntCandidate.hunt_id)
        .where(HuntCandidate.candidate_id.in_(candidate_ids))
    )
    mapping: Dict[int, List[str]] = {}
    for cid, title in db.execute(stmt).all():
        if cid is None:
            continue
        mapping.setdefault(cid, [])
        if title and title not in mapping[cid]:
            mapping[cid].append(title)
    return mapping
