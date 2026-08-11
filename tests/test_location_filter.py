"""Unit tests for location extract + India hunt geo filter."""

from app.hunts.location import (
    extract_location_from_text,
    linkedin_host_country,
    location_matches_target,
    normalize_candidate_location,
)


def test_linkedin_host_country():
    assert linkedin_host_country("https://it.linkedin.com/in/valentina") == "Italy"
    assert linkedin_host_country("https://in.linkedin.com/in/someone") == "India"
    assert linkedin_host_country("https://www.linkedin.com/in/william") is None


def test_reject_atlanta_for_india_hunt():
    ok, reason = location_matches_target(
        candidate_location="Atlanta, Georgia, United States",
        target_location="India",
        profile_url="https://www.linkedin.com/in/william-fogle-5a0431236",
        page_text="Business Development Representative Atlanta Georgia United States",
        reject_unknown=True,
    )
    assert ok is False
    assert "non_india" in reason or "unknown" in reason


def test_reject_italy_host_for_india_hunt():
    ok, reason = location_matches_target(
        candidate_location="India",  # falsely stamped
        target_location="India",
        profile_url="https://it.linkedin.com/in/valentina-lombardi",
        page_text="Admin Coordinator Monza Lombardy Italy",
        reject_unknown=True,
    )
    assert ok is False
    assert "linkedin_host" in reason or "non_india" in reason


def test_accept_bengaluru_for_india():
    ok, reason = location_matches_target(
        candidate_location="Bengaluru, Karnataka, India",
        target_location="India",
        profile_url="https://www.linkedin.com/in/someone",
        page_text="",
        reject_unknown=True,
    )
    assert ok is True


def test_unknown_rejected_for_india():
    ok, reason = location_matches_target(
        candidate_location=None,
        target_location="India",
        profile_url="https://www.linkedin.com/in/someone",
        page_text="Sales professional with CRM experience",
        reject_unknown=True,
    )
    assert ok is False
    assert reason == "unknown_location_for_india_hunt"


def test_normalize_does_not_invent_hunt_country():
    assert normalize_candidate_location(extracted=None, profile_url="", fallback="India") is None
    assert normalize_candidate_location(
        extracted=None, profile_url="https://it.linkedin.com/in/x", fallback="India"
    ) == "Italy"


def test_extract_location_line():
    text = "William Fogle\nBusiness Development\nAtlanta, Georgia, United States\n500+ connections"
    loc = extract_location_from_text(text)
    assert loc is not None
    assert "Atlanta" in loc or "Georgia" in loc or "United States" in loc


def test_company_comma_does_not_override_real_india_location():
    text = (
        "Spine 2D Animator Ocean Studios, Inc. Jun 2022 - Feb 2024 "
        "1 year 9 months Sector 62 Noida, Uttar Pradesh, India"
    )
    location = extract_location_from_text(text)
    assert location is not None
    assert "Noida" in location
    assert "Ocean Studios" not in location
