"""Free web sourcing for Talent Hunts (LinkedIn + Naukri via DuckDuckGo, no paid APIs)."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.infrastructure.db import SessionFactory
from app.candidates.service import create_candidate, add_candidate_tag
from app.candidates.models import Candidate, CandidateTag
from app.hunts.pipeline import add_candidate_to_hunt
from app.hunts.models import TalentHunt, HuntCandidate

logger = logging.getLogger("talenthunt.hunts.web_sourcing")

HUNT_TAG_COLOR = "#19d3c5"
PLATFORM_COLORS = {
    "linkedin": "#0A66C2",
    "naukri": "#2557A7",
}


def _ddg_search(query: str, max_results: int = 8) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """Run a free DuckDuckGo search; return (hits, error).

    error is set when every backend failed — empty hits with error=None means a real empty result set.
    """
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

    # 1) New package name (ddgs) — most reliable currently
    try:
        from ddgs import DDGS  # type: ignore
        with DDGS() as client:
            results = _normalize(client.text(query, max_results=max_results))
        if results:
            return results, None
    except Exception as exc:
        errors.append(f"ddgs: {exc}")
        logger.debug("ddgs search failed: %s", exc)

    # 2) Legacy duckduckgo_search
    try:
        from duckduckgo_search import DDGS as LegacyDDGS  # type: ignore
        with LegacyDDGS() as client:
            results = _normalize(client.text(query, max_results=max_results))
        if results:
            return results, None
    except Exception as exc:
        errors.append(f"duckduckgo_search: {exc}")
        logger.debug("duckduckgo_search failed: %s", exc)

    # 3) LangChain wrapper
    try:
        from langchain_community.tools import DuckDuckGoSearchResults
        ddg = DuckDuckGoSearchResults(num_results=max_results)
        raw = ddg.run(query)
        if isinstance(raw, list):
            results = _normalize(raw)
            if results:
                return results, None

        # Parse string blobs: "snippet: ... title: ... link: ..."
        current: Dict[str, str] = {}
        chunks = re.split(r"(?:,\s*)?(?=snippet:|title:|link:)", str(raw))
        for chunk in chunks:
            chunk = chunk.strip().strip(",")
            if chunk.startswith("title:"):
                if current.get("title") or current.get("link"):
                    results.append(current)
                    current = {}
                current["title"] = chunk[6:].strip()
            elif chunk.startswith("link:"):
                current["link"] = chunk[5:].strip()
            elif chunk.startswith("snippet:"):
                current["snippet"] = chunk[8:].strip()
        if current.get("title") or current.get("link"):
            results.append(current)
        if results:
            return results, None
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return [], None  # genuine empty
    except Exception as exc:
        errors.append(f"langchain_ddg: {exc}")
        logger.warning("DuckDuckGo search failed for %r: %s", query, exc)

    if errors and not results:
        return [], "; ".join(errors[:3])
    return results, None


def _detect_platform(url: str, title: str = "") -> str:
    hay = f"{url} {title}".lower()
    if "linkedin.com" in hay:
        return "linkedin"
    if "naukri.com" in hay:
        return "naukri"
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
) -> Dict[str, Any]:
    """Search LinkedIn + Naukri (via DuckDuckGo), create candidates, tag with hunt, link to pipeline.

    enrich_pages: open each /in profile in Playwright and read text (default True).
    verify_with_ai: cross-check role + experience band with the LLM after page read.
    job_id: optional sourcing_jobs id for progress/cancel.
    """
    from app.hunts.experience import (
        estimate_years_from_text,
        experience_within_range,
        title_implies_seniority,
    )
    from app.hunts import sourcing_jobs

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

    exp_clause = ""
    if experience_years_min is not None and experience_years_max is not None:
        exp_clause = f"{experience_years_min}-{experience_years_max} years"
    elif experience_years_min is not None:
        exp_clause = f"{experience_years_min}+ years"
    elif experience_years_max is not None:
        exp_clause = f"under {experience_years_max} years"

    queries = [
        f'{role_label} {primary} {exp_clause} {loc} site:linkedin.com/in'.strip(),
        f'{role_label} {exp_clause} {loc} site:linkedin.com/in'.strip(),
        f'{role_label} {primary} {exp_clause} {loc} site:naukri.com'.strip(),
        f'"{role_label}" "{primary}" {exp_clause} site:linkedin.com/in {loc}'.strip(),
        f'{role_label} {exp_clause} India site:linkedin.com/in'.strip(),
    ]
    # Drop empty double-spaces from missing exp clause
    queries = [" ".join(q.split()) for q in queries]

    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    added = 0
    scanned = 0
    skipped_exp = 0
    skipped_ai = 0
    skipped_url = 0
    search_failures = 0
    search_ok = 0
    errors: List[str] = []
    goal = target_added or 25

    if job_id:
        sourcing_jobs.update_job(
            job_id,
            message=f"Searching web for {role_label} ({exp_clause or 'any exp'})…",
        )

    for query in queries:
        if sourcing_jobs.should_cancel(job_id):
            break
        if added >= goal:
            break
        hits, search_err = _ddg_search(query, max_results=max_per_query)
        if search_err:
            search_failures += 1
            errors.append(f"search_failed: {search_err}")
            continue
        search_ok += 1
        for hit in hits:
            if sourcing_jobs.should_cancel(job_id):
                break
            if added >= goal:
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
            name, job_title, company = _parse_name_title(title, snippet)
            if not _looks_like_person(name):
                continue
            if not _role_relevance(role_label, title, snippet, job_title):
                continue

            est_years = estimate_years_from_text(title, snippet, job_title)
            page_summary = snippet
            page_text = snippet

            if job_id:
                sourcing_jobs.update_job(
                    job_id,
                    scanned=scanned,
                    added=added,
                    skipped=skipped_exp + skipped_ai,
                    message=f"Reading profile: {name}…",
                )

            # Open real /in profile in Chromium, expand, read text
            if enrich_pages and link and "linkedin.com" in link.lower():
                try:
                    from app.browser.page_reader import enrich_profile_from_url
                    enriched = enrich_profile_from_url(link, headless=True)
                    if enriched.get("blocked") or enriched.get("status") != "success":
                        # Without page text we cannot trust experience — skip
                        skipped_ai += 1
                        logger.info("Skip %s — page read blocked/failed: %s", link, enriched.get("error"))
                        continue
                    page_text = enriched.get("text") or ""
                    page_summary = (enriched.get("summary") or page_text or "")[:800]
                    if enriched.get("experience_years") is not None:
                        est_years = enriched["experience_years"]
                    if enriched.get("headline"):
                        hl = enriched["headline"]
                        if len(hl) < 120:
                            job_title = job_title or hl
                    if enriched.get("senior_title") and experience_years_max is not None and experience_years_max <= 10:
                        skipped_exp += 1
                        continue
                except Exception as page_exc:
                    logger.warning("Page read failed for %s: %s", link, page_exc)
                    skipped_ai += 1
                    continue

            # Hard experience band from heuristics / page
            if not experience_within_range(
                years=est_years,
                exp_min=experience_years_min,
                exp_max=experience_years_max,
                title=job_title or title,
            ):
                skipped_exp += 1
                continue

            # AI cross-check against role + experience band using full page text
            if verify_with_ai and page_text.strip():
                if job_id:
                    sourcing_jobs.update_job(job_id, message=f"AI verifying: {name}…")
                try:
                    from app.hunts.profile_verify import ai_verify_profile
                    verdict = ai_verify_profile(
                        role=role_label,
                        skills=", ".join(skill_bits) if skill_bits else skills,
                        exp_min=experience_years_min,
                        exp_max=experience_years_max,
                        name=name,
                        title=job_title or title,
                        years=est_years,
                        page_text=page_text,
                    )
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
                        continue
                    # Re-check band after AI years estimate
                    if not experience_within_range(
                        years=est_years,
                        exp_min=experience_years_min,
                        exp_max=experience_years_max,
                        title=job_title,
                    ):
                        skipped_exp += 1
                        continue
                except Exception as ver_exc:
                    logger.warning("AI verify error for %s: %s", name, ver_exc)

            key = name.strip().lower()
            if key in seen_names:
                continue
            seen_names.add(key)

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
                    ):
                        skipped_exp += 1
                        continue

                    linkedin_url = link if platform == "linkedin" else None
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
                                location=candidate.location or loc,
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
                                    message=f"Added {added}: {name}",
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
                            location=loc,
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
                                message=f"Added {added}: {name}",
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
            except Exception as exc:
                logger.error("Failed to ingest search hit %r: %s", title, exc)
                errors.append(str(exc))

    cancelled = sourcing_jobs.should_cancel(job_id)
    if cancelled:
        status = "cancelled"
    elif search_ok == 0 and search_failures > 0:
        status = "search_failed"
    elif added == 0 and scanned == 0 and search_ok > 0:
        status = "empty"
    else:
        status = "success"

    result = {
        "status": status,
        "hunt_id": hunt_id,
        "scanned": scanned,
        "added": added,
        "skipped_exp": skipped_exp,
        "skipped_ai": skipped_ai,
        "skipped_url": skipped_url,
        "search_ok": search_ok,
        "search_failures": search_failures,
        "exp_min": experience_years_min,
        "exp_max": experience_years_max,
        "queries": len(queries),
        "errors": errors[:5],
        "message": (
            f"Web search backends failed ({search_failures} queries). Not the same as zero candidates."
            if status == "search_failed"
            else (
                f"Search ran but found no usable profile hits (scanned={scanned})."
                if status == "empty"
                else f"Added {added}, scanned {scanned}, skipped exp {skipped_exp}, AI rejects {skipped_ai}."
            )
        ),
    }
    if job_id:
        sourcing_jobs.finish_job(
            job_id,
            status="cancelled" if cancelled else ("error" if status == "search_failed" else "done"),
            message=(
                f"Cancelled after adding {added}."
                if cancelled
                else result["message"]
            ),
            error="; ".join(errors[:2]) if status == "search_failed" else None,
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
