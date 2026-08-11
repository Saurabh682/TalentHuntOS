from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.candidates.discovery import (
    common_pool_count,
    common_pool_linked_candidate_count,
    discovery_counts,
    list_common_pool_profiles,
    normalize_profile_url,
    prune_raw_discoveries,
    record_discovery,
    recover_stale_enrichments,
    set_discovery_status,
    sync_candidate_identities_to_common_pool,
    import_approved_discovery,
)
from app.actions.history import undo_action
from app.actions.models import ActionHistory
from app.candidates.profile_extract import ExperienceDraft, ProfileExtractResult
from app.candidates.service import create_candidate
from app.candidates.models import Candidate, DiscoveredProfile, DiscoveryHuntMatch
from app.hunts.models import HuntCandidate, TalentHunt
from app.infrastructure.db import Base


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'discovery.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_normalize_linkedin_identity_ignores_locale_query_and_case():
    assert normalize_profile_url("https://in.linkedin.com/in/Asha-Rao/?trk=search") == (
        "https://linkedin.com/in/asha-rao"
    )


def test_discovery_deduplicates_identity_but_keeps_hunt_matches(tmp_path):
    factory = _factory(tmp_path)
    with factory() as db:
        first = TalentHunt(title="Animator", target_role="Animator")
        second = TalentHunt(title="Lead Animator", target_role="Lead Animator")
        db.add_all([first, second])
        db.commit()

        record_discovery(
            db,
            hunt_id=first.id,
            url="https://in.linkedin.com/in/Asha-Rao/?trk=search",
            platform="linkedin",
            source_query="animator",
            full_name="Asha Rao",
            status="shortlisted",
        )
        record_discovery(
            db,
            hunt_id=second.id,
            url="https://www.linkedin.com/in/asha-rao",
            platform="linkedin",
            source_query="lead animator",
            full_name="Asha Rao",
            status="shortlisted",
        )

        assert db.query(DiscoveredProfile).count() == 1
        assert db.query(DiscoveryHuntMatch).count() == 2
        assert db.query(Candidate).count() == 0
        assert db.query(HuntCandidate).count() == 0


def test_repeat_shortlist_is_not_reported_as_new(tmp_path):
    factory = _factory(tmp_path)
    with factory() as db:
        hunt = TalentHunt(title="Animator", target_role="Animator")
        db.add(hunt)
        db.commit()
        _, first = record_discovery(
            db,
            hunt_id=hunt.id,
            url="https://linkedin.com/in/asha-rao",
            platform="linkedin",
            source_query="animator",
            status="shortlisted",
        )
        assert first.was_newly_shortlisted is True
        _, repeat = record_discovery(
            db,
            hunt_id=hunt.id,
            url="https://linkedin.com/in/asha-rao?trk=again",
            platform="linkedin",
            source_query="animator second pass",
            status="shortlisted",
        )
        assert repeat.was_newly_shortlisted is False
        assert discovery_counts(db, hunt_id=hunt.id)["reviewable"] == 1


def test_review_status_and_common_pool_retention_is_permanent(tmp_path):
    factory = _factory(tmp_path)
    with factory() as db:
        hunt = TalentHunt(title="Animator", target_role="Animator")
        db.add(hunt)
        db.commit()
        profile, match = record_discovery(
            db,
            hunt_id=hunt.id,
            url="https://github.com/asha-rao",
            platform="github",
            source_query="animator github",
            full_name="Asha Rao",
            status="shortlisted",
        )
        assert discovery_counts(db, hunt_id=hunt.id)["reviewable"] == 1
        set_discovery_status(db, match.id, "rejected")
        assert discovery_counts(db, hunt_id=hunt.id)["reviewable"] == 0

        profile = db.get(DiscoveredProfile, profile.id)
        profile.status = "raw"
        profile.last_seen_at = datetime.now(timezone.utc) - timedelta(days=31)
        db.commit()
        assert prune_raw_discoveries(db, retention_days=30) == 0
        assert db.query(DiscoveredProfile).count() == 1


def test_common_pool_lists_identity_once_across_hunts_and_supports_search(tmp_path):
    factory = _factory(tmp_path)
    with factory() as db:
        first = TalentHunt(title="Animator", target_role="Animator")
        second = TalentHunt(title="Lead Animator", target_role="Lead Animator")
        db.add_all([first, second])
        db.commit()
        for hunt in (first, second):
            record_discovery(
                db,
                hunt_id=hunt.id,
                url="https://linkedin.com/in/asha-rao",
                platform="linkedin",
                source_query=hunt.title,
                full_name="Asha Rao",
                company="Pixel Studio",
                status="shortlisted",
            )

        assert common_pool_count(db) == 1
        assert common_pool_count(db, hunt_id=first.id) == 1
        assert common_pool_count(db, search="Pixel") == 1
        profiles = list_common_pool_profiles(db, search="Asha")
        assert len(profiles) == 1
        assert len(profiles[0].hunt_matches) == 2
        assert list_common_pool_profiles(db, search="unrelated") == []


def test_existing_candidate_is_backfilled_into_common_pool_idempotently(tmp_path):
    factory = _factory(tmp_path)
    with factory() as db:
        candidate = create_candidate(
            db,
            full_name="Asha Rao",
            linkedin_url="https://www.linkedin.com/in/asha-rao/?trk=profile",
            current_title="Spine Animator",
            location="Noida, India",
            experience_years=5,
        )
        candidate_id = candidate.id

        assert sync_candidate_identities_to_common_pool(db) == {"created": 1, "linked": 0}
        profile = db.query(DiscoveredProfile).one()
        assert profile.candidate_id == candidate_id
        assert profile.status == "imported"
        assert profile.normalized_url == "https://linkedin.com/in/asha-rao"
        assert profile.seen_count == 1
        assert common_pool_linked_candidate_count(db) == 1

        assert sync_candidate_identities_to_common_pool(db) == {"created": 0, "linked": 0}
        assert db.query(DiscoveredProfile).count() == 1
        assert db.query(DiscoveredProfile).one().seen_count == 1


def test_interrupted_enrichment_becomes_retryable(tmp_path):
    factory = _factory(tmp_path)
    with factory() as db:
        hunt = TalentHunt(title="Animator", target_role="Animator")
        db.add(hunt)
        db.commit()
        _, match = record_discovery(
            db,
            hunt_id=hunt.id,
            url="https://linkedin.com/in/interrupted",
            platform="linkedin",
            source_query="animator",
            status="enriching",
        )
        match.approved_at = datetime.now(timezone.utc) - timedelta(minutes=11)
        db.commit()

        assert recover_stale_enrichments(db, stale_after_minutes=10) == 1
        db.refresh(match)
        assert match.status == "scan_failed"
        assert "interrupted" in match.scan_error.lower()


def test_approval_deep_scans_imports_and_is_undoable(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.candidates.service._reindex_candidate", lambda *args: None)
    monkeypatch.setattr(
        "app.candidates.search.candidate_search_index.index_candidate",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "app.browser.page_reader.enrich_profile_from_url",
        lambda *args, **kwargs: {
            "status": "success",
            "blocked": False,
            "text": "Asha Rao Spine Animator at Pixel Co Jan 2020 - Jan 2025 Noida India",
            "headline": "Spine Animator",
            "location": "Noida, India",
            "summary": "Spine Animator at Pixel Co",
            "snapshot": None,
        },
    )
    monkeypatch.setattr(
        "app.candidates.profile_extract.extract_profile_from_text",
        lambda text: ProfileExtractResult(
            headline="Spine Animator",
            summary="Spine Animator at Pixel Co",
            experience_years=12,
            skills=["Spine"],
            status="success",
        ),
    )

    with factory() as db:
        hunt = TalentHunt(title="Animator", target_role="Spine Animator")
        db.add(hunt)
        db.commit()
        _, match = record_discovery(
            db,
            hunt_id=hunt.id,
            url="https://linkedin.com/in/asha-rao",
            platform="linkedin",
            source_query="spine animator",
            full_name="Asha Rao",
            status="approved",
        )
        match_id = match.id

    result = import_approved_discovery(match_id)
    assert result["status"] == "success"

    with factory() as db:
        assert db.query(Candidate).count() == 1
        assert db.query(HuntCandidate).count() == 1
        assert db.query(Candidate).one().experience_years == 5.1
        action = db.query(ActionHistory).one()
        match = db.get(DiscoveryHuntMatch, match_id)
        assert match.status == "imported"
        undo_action(db, action.id)
        assert db.query(HuntCandidate).count() == 0
        assert db.query(Candidate).count() == 0
        assert db.get(DiscoveryHuntMatch, match_id).status == "shortlisted"


def test_existing_candidate_merges_scan_evidence_without_duplicates(monkeypatch, tmp_path):
    factory = _factory(tmp_path)
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    monkeypatch.setattr("app.candidates.service._reindex_candidate", lambda *args: None)
    monkeypatch.setattr(
        "app.candidates.search.candidate_search_index.index_candidate",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "app.browser.page_reader.enrich_profile_from_url",
        lambda *args, **kwargs: {
            "status": "success",
            "blocked": False,
            "text": "Asha Rao Animator at Pixel Co Jan 2020 - Jan 2025 Noida India",
            "location": "Noida, India",
            "summary": "Machine-generated longer replacement summary that must not win.",
            "snapshot": None,
        },
    )
    monkeypatch.setattr(
        "app.candidates.profile_extract.extract_profile_from_text",
        lambda text: ProfileExtractResult(
            headline="Machine headline",
            summary="Machine-generated longer replacement summary that must not win.",
            experience_years=5,
            experiences=[ExperienceDraft(
                company="Pixel Co",
                title="Animator",
                start_date="2020-01",
                end_date="2025-01",
            )],
            skills=["Spine", "spine"],
            status="success",
        ),
    )

    with factory() as db:
        first_hunt = TalentHunt(title="Animator", target_role="Animator")
        second_hunt = TalentHunt(title="Lead Animator", target_role="Lead Animator")
        db.add_all([first_hunt, second_hunt])
        db.commit()
        candidate = create_candidate(
            db,
            full_name="Asha Rao",
            linkedin_url="https://linkedin.com/in/asha-rao",
            experience_years=4,
            headline="Recruiter headline",
            summary="Recruiter summary",
            skills=["Animation"],
        )
        match_ids = []
        for hunt in (first_hunt, second_hunt):
            _, match = record_discovery(
                db,
                hunt_id=hunt.id,
                url="https://linkedin.com/in/asha-rao",
                platform="linkedin",
                source_query="animator",
                full_name="Asha Rao",
                status="approved",
            )
            match_ids.append(match.id)
        candidate_id = candidate.id

    first_result = import_approved_discovery(match_ids[0])
    assert first_result["status"] == "success"
    assert first_result["created_candidate"] is False

    def fail_action_history(*args, **kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr("app.actions.history.record_action", fail_action_history)
    second_result = import_approved_discovery(match_ids[1])
    assert second_result["status"] == "success"
    assert second_result["created_candidate"] is False
    assert second_result["action_id"] is None
    assert "undo history" in second_result["warning"]

    with factory() as db:
        candidate = db.get(Candidate, candidate_id)
        assert db.query(Candidate).count() == 1
        assert db.query(HuntCandidate).count() == 2
        assert db.get(DiscoveryHuntMatch, match_ids[1]).status == "imported"
        assert len(candidate.experiences) == 1
        assert candidate.experience_years == 5.1
        assert candidate.profile.headline == "Recruiter headline"
        assert candidate.profile.summary == "Recruiter summary"
        assert candidate.profile.skills_json == '["Animation", "Spine"]'
