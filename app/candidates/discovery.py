"""Raw discovery pool and recruiter-approved candidate import workflow."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import unquote, urlparse

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.candidates.models import Candidate, DiscoveredProfile, DiscoveryHuntMatch

logger = logging.getLogger("talenthunt.candidates.discovery")

REVIEWABLE_STATUSES = ("shortlisted", "approved", "enriching", "scan_failed")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_profile_url(url: str) -> str:
    """Return one stable public identity URL across tracking and locale variants."""
    target = (url or "").strip()
    if not target:
        return ""
    if not target.startswith(("http://", "https://")):
        target = "https://" + target
    parsed = urlparse(target)
    host = (parsed.hostname or "").lower()
    path = re.sub(r"/+", "/", unquote(parsed.path or "/")).rstrip("/")

    if host.endswith("linkedin.com"):
        host = "linkedin.com"
        match = re.search(r"/(?:[a-z]{2}/)?in/([^/?#]+)", path, re.I)
        if match:
            path = f"/in/{match.group(1).lower()}"
    elif host.startswith("www."):
        host = host[4:]

    return f"https://{host}{path or '/'}"


def record_discovery(
    db: Session,
    *,
    hunt_id: int,
    url: str,
    platform: str,
    source_query: str,
    full_name: Optional[str] = None,
    headline: Optional[str] = None,
    company: Optional[str] = None,
    location: Optional[str] = None,
    experience_years: Optional[float] = None,
    snippet: Optional[str] = None,
    raw_payload: Optional[Dict[str, Any]] = None,
    status: str = "raw",
    rejection_reason: Optional[str] = None,
    match_score: Optional[float] = None,
) -> Tuple[DiscoveredProfile, DiscoveryHuntMatch]:
    """Upsert a global public identity and its independent hunt match."""
    normalized = normalize_profile_url(url)
    if not normalized:
        raise ValueError("A discovery requires a profile URL")
    now = utcnow()
    profile = db.scalar(
        select(DiscoveredProfile).where(DiscoveredProfile.normalized_url == normalized)
    )
    if profile is None:
        profile = DiscoveredProfile(
            normalized_url=normalized,
            source_url=url.strip(),
            platform=(platform or "web").strip().lower(),
            full_name=(full_name or "").strip() or None,
            headline=(headline or "").strip() or None,
            current_company=(company or "").strip() or None,
            location=(location or "").strip() or None,
            experience_years=experience_years,
            snippet=(snippet or "").strip() or None,
            raw_payload_json=json.dumps(raw_payload or {}, ensure_ascii=False),
            status="raw",
            first_seen_at=now,
            last_seen_at=now,
            seen_count=1,
        )
        db.add(profile)
        db.flush()
    else:
        profile.last_seen_at = now
        profile.seen_count = int(profile.seen_count or 0) + 1
        profile.source_url = url.strip() or profile.source_url
        for attr, value in (
            ("full_name", full_name),
            ("headline", headline),
            ("current_company", company),
            ("location", location),
            ("snippet", snippet),
        ):
            cleaned = (value or "").strip()
            if cleaned and (not getattr(profile, attr) or len(cleaned) > len(getattr(profile, attr) or "")):
                setattr(profile, attr, cleaned)
        if experience_years is not None and 0 <= float(experience_years) <= 60:
            profile.experience_years = float(experience_years)
        if raw_payload:
            profile.raw_payload_json = json.dumps(raw_payload, ensure_ascii=False)

    match = db.scalar(
        select(DiscoveryHuntMatch).where(
            DiscoveryHuntMatch.discovered_profile_id == profile.id,
            DiscoveryHuntMatch.hunt_id == int(hunt_id),
        )
    )
    previous_status = match.status if match is not None else None
    if match is None:
        match = DiscoveryHuntMatch(
            discovered_profile_id=profile.id,
            hunt_id=int(hunt_id),
            status=status,
            source_platform=platform,
            source_query=source_query,
            match_score=match_score,
            rejection_reason=rejection_reason,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(match)
    else:
        match.last_seen_at = now
        match.source_platform = platform or match.source_platform
        match.source_query = source_query or match.source_query
        match.match_score = match_score if match_score is not None else match.match_score
        # Recruiter decisions and imports are never reset by a later search sighting.
        if match.status not in {"approved", "enriching", "imported", "scan_failed", "rejected"}:
            match.status = status
            match.rejection_reason = rejection_reason
    match.was_newly_shortlisted = bool(
        status == "shortlisted"
        and match.status == "shortlisted"
        and previous_status not in REVIEWABLE_STATUSES
    )
    db.commit()
    db.refresh(profile)
    db.refresh(match)
    return profile, match


def list_discoveries(
    db: Session,
    *,
    hunt_id: Optional[int] = None,
    statuses: Optional[Iterable[str]] = None,
    limit: int = 200,
) -> list[DiscoveryHuntMatch]:
    stmt = select(DiscoveryHuntMatch).options(
        selectinload(DiscoveryHuntMatch.profile),
        selectinload(DiscoveryHuntMatch.hunt),
    )
    if hunt_id is not None:
        stmt = stmt.where(DiscoveryHuntMatch.hunt_id == int(hunt_id))
    if statuses:
        stmt = stmt.where(DiscoveryHuntMatch.status.in_(tuple(statuses)))
    stmt = stmt.order_by(DiscoveryHuntMatch.last_seen_at.desc()).limit(max(1, min(limit, 500)))
    return list(db.scalars(stmt).all())


def list_common_pool_profiles(
    db: Session,
    *,
    hunt_id: Optional[int] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> list[DiscoveredProfile]:
    """List permanent identities once, independent of Hunt-specific decisions."""
    stmt = select(DiscoveredProfile).options(
        selectinload(DiscoveredProfile.candidate),
        selectinload(DiscoveredProfile.hunt_matches).selectinload(DiscoveryHuntMatch.hunt),
    )
    if hunt_id is not None:
        stmt = stmt.join(DiscoveryHuntMatch).where(
            DiscoveryHuntMatch.hunt_id == int(hunt_id)
        )
    needle = (search or "").strip()
    if needle:
        pattern = f"%{needle}%"
        stmt = stmt.where(
            or_(
                DiscoveredProfile.full_name.ilike(pattern),
                DiscoveredProfile.headline.ilike(pattern),
                DiscoveredProfile.current_company.ilike(pattern),
                DiscoveredProfile.location.ilike(pattern),
                DiscoveredProfile.platform.ilike(pattern),
                DiscoveredProfile.snippet.ilike(pattern),
            )
        )
    stmt = (
        stmt.order_by(DiscoveredProfile.last_seen_at.desc(), DiscoveredProfile.id.desc())
        .offset(max(0, int(offset)))
        .limit(max(1, min(int(limit), 250)))
    )
    return list(db.scalars(stmt).unique().all())


def common_pool_count(
    db: Session,
    *,
    hunt_id: Optional[int] = None,
    search: Optional[str] = None,
) -> int:
    stmt = select(func.count(func.distinct(DiscoveredProfile.id)))
    if hunt_id is not None:
        stmt = stmt.select_from(DiscoveredProfile).join(DiscoveryHuntMatch).where(
            DiscoveryHuntMatch.hunt_id == int(hunt_id)
        )
    needle = (search or "").strip()
    if needle:
        pattern = f"%{needle}%"
        stmt = stmt.where(
            or_(
                DiscoveredProfile.full_name.ilike(pattern),
                DiscoveredProfile.headline.ilike(pattern),
                DiscoveredProfile.current_company.ilike(pattern),
                DiscoveredProfile.location.ilike(pattern),
                DiscoveredProfile.platform.ilike(pattern),
                DiscoveredProfile.snippet.ilike(pattern),
            )
        )
    return int(db.scalar(stmt) or 0)


def common_pool_linked_candidate_count(
    db: Session,
    *,
    hunt_id: Optional[int] = None,
    search: Optional[str] = None,
) -> int:
    """Count pool identities linked to canonical Candidate records."""
    stmt = select(func.count(func.distinct(DiscoveredProfile.id))).where(
        DiscoveredProfile.candidate_id.is_not(None)
    )
    if hunt_id is not None:
        stmt = stmt.select_from(DiscoveredProfile).join(DiscoveryHuntMatch).where(
            DiscoveryHuntMatch.hunt_id == int(hunt_id)
        )
    needle = (search or "").strip()
    if needle:
        pattern = f"%{needle}%"
        stmt = stmt.where(
            or_(
                DiscoveredProfile.full_name.ilike(pattern),
                DiscoveredProfile.headline.ilike(pattern),
                DiscoveredProfile.current_company.ilike(pattern),
                DiscoveredProfile.location.ilike(pattern),
                DiscoveredProfile.platform.ilike(pattern),
                DiscoveredProfile.snippet.ilike(pattern),
            )
        )
    return int(db.scalar(stmt) or 0)


def sync_candidate_identities_to_common_pool(db: Session) -> Dict[str, int]:
    """Backfill canonical candidates into permanent identity memory idempotently."""
    candidates = list(
        db.scalars(select(Candidate).options(selectinload(Candidate.profile))).all()
    )
    profiles = list(db.scalars(select(DiscoveredProfile)).all())
    by_url = {profile.normalized_url: profile for profile in profiles}
    by_candidate = {
        int(profile.candidate_id): profile
        for profile in profiles
        if profile.candidate_id is not None
    }
    created = 0
    linked = 0
    for candidate in candidates:
        urls = [
            ("linkedin", candidate.linkedin_url),
            ("github", candidate.github_url),
            ("portfolio", candidate.portfolio_url),
        ]
        urls = [(platform, url) for platform, url in urls if (url or "").strip()]
        if not urls:
            continue
        profile = by_candidate.get(candidate.id)
        platform, source_url = urls[0]
        if profile is None:
            for candidate_platform, candidate_url in urls:
                normalized = normalize_profile_url(candidate_url)
                if normalized in by_url:
                    profile = by_url[normalized]
                    platform, source_url = candidate_platform, candidate_url
                    break
        if profile is None:
            normalized = normalize_profile_url(source_url)
            profile = DiscoveredProfile(
                normalized_url=normalized,
                source_url=source_url.strip(),
                platform=platform,
                full_name=candidate.full_name,
                headline=candidate.current_title,
                current_company=candidate.current_company,
                location=candidate.location,
                experience_years=candidate.experience_years,
                snippet=(candidate.profile.summary if candidate.profile else None),
                raw_payload_json=json.dumps(
                    {"origin": "candidate_backfill", "candidate_id": candidate.id}
                ),
                status="imported",
                candidate_id=candidate.id,
                first_seen_at=candidate.created_at or utcnow(),
                last_seen_at=candidate.updated_at or candidate.created_at or utcnow(),
                seen_count=1,
            )
            db.add(profile)
            db.flush()
            by_url[normalized] = profile
            by_candidate[candidate.id] = profile
            created += 1
            continue
        changed = False
        if profile.candidate_id != candidate.id:
            profile.candidate_id = candidate.id
            linked += 1
            changed = True
        if profile.status != "imported":
            profile.status = "imported"
            changed = True
        for attr, value in (
            ("full_name", candidate.full_name),
            ("headline", candidate.current_title),
            ("current_company", candidate.current_company),
            ("location", candidate.location),
        ):
            if value and not getattr(profile, attr):
                setattr(profile, attr, value)
                changed = True
        if profile.experience_years is None and candidate.experience_years is not None:
            profile.experience_years = candidate.experience_years
            changed = True
        if changed:
            by_candidate[candidate.id] = profile
    if created or linked or db.dirty:
        db.commit()
    return {"created": created, "linked": linked}


def discovery_counts(db: Session, *, hunt_id: Optional[int] = None) -> Dict[str, int]:
    stmt = select(DiscoveryHuntMatch.status, func.count(DiscoveryHuntMatch.id)).group_by(
        DiscoveryHuntMatch.status
    )
    if hunt_id is not None:
        stmt = stmt.where(DiscoveryHuntMatch.hunt_id == int(hunt_id))
    counts = {str(status): int(count) for status, count in db.execute(stmt).all()}
    counts["reviewable"] = sum(counts.get(status, 0) for status in REVIEWABLE_STATUSES)
    counts["total"] = sum(value for key, value in counts.items() if key != "reviewable")
    return counts


def set_discovery_status(
    db: Session,
    match_id: int,
    status: str,
    *,
    error: Optional[str] = None,
    rejection_reason: Optional[str] = None,
) -> Optional[DiscoveryHuntMatch]:
    match = db.get(DiscoveryHuntMatch, int(match_id))
    if not match:
        return None
    match.status = status
    match.scan_error = error
    if rejection_reason is not None:
        match.rejection_reason = rejection_reason
    if status == "approved":
        match.approved_at = utcnow()
    db.commit()
    db.refresh(match)
    return match


def recover_stale_enrichments(db: Session, *, stale_after_minutes: int = 10) -> int:
    """Make interrupted approval scans retryable after an app or worker restart."""
    cutoff = utcnow() - timedelta(minutes=max(1, int(stale_after_minutes)))
    matches = list(db.scalars(
        select(DiscoveryHuntMatch).where(
            DiscoveryHuntMatch.status == "enriching",
            or_(
                DiscoveryHuntMatch.approved_at.is_(None),
                DiscoveryHuntMatch.approved_at < cutoff,
            ),
        )
    ).all())
    for match in matches:
        match.status = "scan_failed"
        match.scan_error = "The previous deep scan was interrupted. Retry approval to scan again."
    if matches:
        db.commit()
    return len(matches)


def prune_raw_discoveries(db: Session, *, retention_days: int | None = None) -> int:
    """Compatibility no-op: common-pool identities are permanent OS memory."""
    logger.info(
        "Common-pool pruning is disabled; requested retention_days=%s",
        retention_days,
    )
    return 0


def _find_candidate_for_profile(db: Session, profile: DiscoveredProfile) -> Optional[Candidate]:
    if profile.candidate_id:
        candidate = db.get(Candidate, int(profile.candidate_id))
        if candidate:
            return candidate
    normalized = profile.normalized_url
    candidates = list(db.scalars(select(Candidate)).all())
    for candidate in candidates:
        for url in (candidate.linkedin_url, candidate.github_url, candidate.portfolio_url):
            if url and normalize_profile_url(url) == normalized:
                return candidate
    return None


def import_approved_discovery(match_id: int, *, actor_type: str = "recruiter") -> Dict[str, Any]:
    """Deep-scan one approved discovery and import it into canonical OS data."""
    from app.infrastructure.db import SessionFactory

    import_completed = False

    with SessionFactory() as db:
        match = db.scalar(
            select(DiscoveryHuntMatch)
            .options(selectinload(DiscoveryHuntMatch.profile), selectinload(DiscoveryHuntMatch.hunt))
            .where(DiscoveryHuntMatch.id == int(match_id))
        )
        if not match:
            return {"status": "error", "error": "Discovery match not found"}
        if match.status not in {"approved", "scan_failed"}:
            return {"status": "error", "error": f"Discovery is {match.status}, not approved"}
        match.status = "enriching"
        match.scan_error = None
        profile_id = match.profile.id
        hunt_id = match.hunt_id
        url = match.profile.source_url
        db.commit()

    try:
        from app.browser.page_reader import enrich_profile_from_url

        enriched = enrich_profile_from_url(
            url,
            headless=True,
            save_snapshot=True,
            timeout_ms=35_000,
            scan_mode=False,
        )
        if not enriched or enriched.get("status") != "success" or enriched.get("blocked"):
            raise RuntimeError((enriched or {}).get("error") or "Profile scan failed")

        page_text = (enriched.get("text") or "").strip()
        from app.candidates.profile_extract import extract_profile_from_text, extract_result_to_dict
        from app.hunts.experience import estimate_years_from_text
        from app.hunts.location import extract_location_from_text

        extracted_result = extract_profile_from_text(page_text)
        draft = extract_result_to_dict(extracted_result)
        years = estimate_years_from_text(page_text)
        if years is None and draft.get("experience_years") is not None:
            try:
                structured_years = float(draft["experience_years"])
                if 0 <= structured_years <= 60:
                    years = structured_years
            except (TypeError, ValueError):
                pass
        location = draft.get("location") or enriched.get("location") or extract_location_from_text(page_text)
        profile_image_url = enriched.get("profile_image_url") or draft.get("profile_image_url")

        with SessionFactory() as db:
            match = db.scalar(
                select(DiscoveryHuntMatch)
                .options(selectinload(DiscoveryHuntMatch.profile), selectinload(DiscoveryHuntMatch.hunt))
                .where(DiscoveryHuntMatch.id == int(match_id))
            )
            if not match:
                raise RuntimeError("Discovery match disappeared during scan")
            profile = match.profile
            existing = _find_candidate_for_profile(db, profile)
            existing_candidate_ids = set(db.scalars(select(Candidate.id)).all())
            created_candidate = False

            if existing is None:
                from app.candidates.service import create_candidate

                candidate = create_candidate(
                    db,
                    full_name=draft.get("full_name") or profile.full_name or "Unknown candidate",
                    email=draft.get("email"),
                    phone=draft.get("phone"),
                    location=location or profile.location,
                    current_title=draft.get("current_title") or profile.headline,
                    current_company=draft.get("current_company") or profile.current_company,
                    pronouns=draft.get("pronouns"),
                    connection_degree=draft.get("connection_degree"),
                    connections_count=draft.get("connections_count"),
                    profile_image_url=profile_image_url,
                    experience_years=years,
                    linkedin_url=profile.source_url if profile.platform == "linkedin" else None,
                    github_url=profile.source_url if profile.platform == "github" else None,
                    portfolio_url=(
                        profile.source_url
                        if profile.platform not in {"linkedin", "github"}
                        else None
                    ),
                    status="Sourced",
                    headline=draft.get("headline") or profile.headline,
                    summary=draft.get("summary") or enriched.get("summary") or profile.snippet,
                    resume_text=page_text[:50_000],
                    skills=draft.get("skills") or None,
                    highlights=draft.get("highlights") or None,
                    tags=[f"Hunt: {match.hunt.title}", profile.platform.capitalize()],
                )
                if not candidate:
                    raise RuntimeError("Could not create canonical candidate")
                created_candidate = candidate.id not in existing_candidate_ids
            else:
                candidate = existing
                # Existing recruiter data wins; enrichment fills blanks and machine evidence.
                if not candidate.location and location:
                    candidate.location = location
                if not candidate.current_title and (
                    draft.get("current_title") or draft.get("headline") or profile.headline
                ):
                    candidate.current_title = draft.get("current_title") or draft.get("headline") or profile.headline
                if not candidate.current_company and draft.get("current_company"):
                    candidate.current_company = draft["current_company"]
                if not candidate.pronouns and draft.get("pronouns"):
                    candidate.pronouns = draft["pronouns"]
                if not candidate.connection_degree and draft.get("connection_degree"):
                    candidate.connection_degree = draft["connection_degree"]
                if candidate.connections_count is None and draft.get("connections_count") is not None:
                    candidate.connections_count = draft["connections_count"]
                if not candidate.profile_image_url and profile_image_url:
                    candidate.profile_image_url = profile_image_url
                if not candidate.email and draft.get("email"):
                    candidate.email = draft["email"]
                if not candidate.phone and draft.get("phone"):
                    candidate.phone = draft["phone"]
                if candidate.experience_years is None and years is not None:
                    candidate.experience_years = years
                if candidate.profile and not candidate.profile.resume_text:
                    candidate.profile.resume_text = page_text[:50_000]
                if candidate.profile and not candidate.profile.summary and draft.get("summary"):
                    candidate.profile.summary = draft["summary"]
                db.commit()

            if extracted_result.status == "success":
                from app.candidates.service import replace_or_merge_profile_sections

                profile_row = candidate.profile
                replace_or_merge_profile_sections(
                    db,
                    candidate.id,
                    experiences=draft.get("experiences") or None,
                    educations=draft.get("educations") or None,
                    skills=draft.get("skills") or None,
                    highlights=draft.get("highlights") or None,
                    full_name=draft.get("full_name") if created_candidate else None,
                    email=draft.get("email"),
                    phone=draft.get("phone"),
                    location=location,
                    current_title=draft.get("current_title"),
                    current_company=draft.get("current_company"),
                    pronouns=draft.get("pronouns"),
                    connection_degree=draft.get("connection_degree"),
                    connections_count=draft.get("connections_count"),
                    profile_image_url=profile_image_url,
                    headline=(
                        draft.get("headline")
                        if created_candidate or not profile_row or not profile_row.headline
                        else None
                    ),
                    summary=(
                        draft.get("summary")
                        if created_candidate or not profile_row or not profile_row.summary
                        else None
                    ),
                    experience_years=(
                        years if created_candidate or candidate.experience_years is None else None
                    ),
                    resume_text=(
                        page_text[:50_000]
                        if created_candidate or not profile_row or not profile_row.resume_text
                        else None
                    ),
                    mode="replace" if created_candidate else "merge",
                    record_history=False,
                )

            from app.hunts.models import HuntCandidate
            from app.hunts.pipeline import add_candidate_to_hunt

            enrollment = db.scalar(select(HuntCandidate).where(
                HuntCandidate.hunt_id == hunt_id,
                HuntCandidate.candidate_id == candidate.id,
            ))
            created_enrollment = enrollment is None
            if enrollment is None:
                enrollment = add_candidate_to_hunt(
                    db,
                    hunt_id=hunt_id,
                    candidate_id=candidate.id,
                    full_name=candidate.full_name,
                    current_title=candidate.current_title,
                    current_company=candidate.current_company,
                    location=candidate.location,
                    linkedin_url=candidate.linkedin_url,
                    github_url=candidate.github_url,
                    ai_summary=f"Recruiter-approved deep scan from {profile.platform}.",
                    match_score=match.match_score,
                    source_platform=profile.platform,
                    source_query=match.source_query,
                )

            profile.status = "imported"
            profile.candidate_id = candidate.id
            profile.deep_scanned_at = utcnow()
            match.status = "imported"
            match.imported_at = utcnow()
            match.scan_error = None
            db.commit()
            import_completed = True

            pending_snapshot = enriched.get("snapshot")
            if pending_snapshot:
                try:
                    from app.browser.snapshots import attach_pending_snapshot_to_candidate

                    attach_pending_snapshot_to_candidate(
                        candidate_id=candidate.id,
                        snapshot_info=pending_snapshot,
                    )
                except Exception as snapshot_exc:
                    logger.warning(
                        "Candidate %s imported, but snapshot registration failed: %s",
                        candidate.id,
                        snapshot_exc,
                    )

            from app.actions.history import record_action

            try:
                action = record_action(
                    db,
                    action_type="approve_discovered_profile",
                    summary=f"Approved and imported {candidate.full_name} into {match.hunt.title}",
                    actor_type=actor_type,
                    payload={"match_id": match.id, "candidate_id": candidate.id, "hunt_id": hunt_id},
                    undo_payload={
                        "match_id": match.id,
                        "profile_id": profile.id,
                        "candidate_id": candidate.id,
                        "hunt_id": hunt_id,
                        "created_candidate": created_candidate,
                        "created_enrollment": created_enrollment,
                    },
                )
                action_id = action.id
                warning = None
            except Exception as action_exc:
                logger.exception(
                    "Candidate %s imported, but approval action history failed",
                    candidate.id,
                )
                action_id = None
                warning = f"Imported successfully, but undo history could not be recorded: {action_exc}"
            return {
                "status": "success",
                "candidate_id": candidate.id,
                "match_id": match.id,
                "action_id": action_id,
                "created_candidate": created_candidate,
                "warning": warning,
            }
    except Exception as exc:
        logger.exception("Approved discovery import failed for match %s", match_id)
        if not import_completed:
            with SessionFactory() as db:
                match = db.get(DiscoveryHuntMatch, int(match_id))
                if match:
                    match.status = "scan_failed"
                    match.scan_error = str(exc)[:1000]
                    db.commit()
        return {
            "status": "partial" if import_completed else "error",
            "error": str(exc),
            "match_id": int(match_id),
        }
