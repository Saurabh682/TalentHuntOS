"""Unit tests for experience band parsing + filtering (P0)."""

from app.hunts.experience import (
    parse_experience_range,
    estimate_years_from_text,
    estimate_years_from_career_dates,
    estimate_years_from_experience_rows,
    experience_within_range,
)


def test_parse_4_5_years():
    assert parse_experience_range("4-5 years") == (4, 5)
    assert parse_experience_range("4–5 yrs") == (4, 5)
    assert parse_experience_range("4 to 5") == (4, 5)


def test_career_dates_span():
    text = "Sales Development Representative Chick-fil-A Mar 2019 - Oct 2024 5 years 8 months"
    years = estimate_years_from_career_dates(text)
    assert years is not None
    assert 5.0 <= years <= 6.5


def test_career_dates_present_over_band():
    # Senior career starting 2010 → clearly > 5 years
    text = (
        "IT Technical Pre&Post Sales Specialist at Refinitiv "
        "Jan 2010 - Present Desktop Eikon Worldwide"
    )
    years = estimate_years_from_text(text)
    assert years is not None
    assert years >= 10
    assert experience_within_range(
        years=years, exp_min=4, exp_max=5, title="IT Technical Pre&Post Sales Specialist",
        reject_unknown=True,
    ) is False


def test_reject_unknown_when_band_set():
    assert experience_within_range(
        years=None, exp_min=4, exp_max=5, title="Sales Specialist", reject_unknown=True
    ) is False
    # Without reject_unknown, non-senior unknown still passes (legacy)
    assert experience_within_range(
        years=None, exp_min=4, exp_max=5, title="Sales Specialist", reject_unknown=False
    ) is True


def test_within_band_passes():
    assert experience_within_range(
        years=4.5, exp_min=4, exp_max=5, title="BD Executive", reject_unknown=True
    ) is True
    assert experience_within_range(
        years=5.0, exp_min=4, exp_max=5, title="SDR", reject_unknown=True
    ) is True
    assert experience_within_range(
        years=6.0, exp_min=4, exp_max=5, title="SDR", reject_unknown=True
    ) is False


def test_fabrizio_style_unknown_rejected_for_4_5():
    """Profiles with no years signal must not enter a 4-5 hunt."""
    title = "IT Technical Pre&Post Sales Specialist..."
    summary = (
        "Competenze consolidate di analisi e supporto tecnici Pre&Post sales "
        "a livello EMEA e Worldwide"
    )
    years = estimate_years_from_text(title, summary)
    assert experience_within_range(
        years=years, exp_min=4, exp_max=5, title=title, reject_unknown=True
    ) is False


def test_joined_year_and_duration_does_not_become_twenty_thousand_years():
    text = (
        "Spine 2D Animator Ocean Studios, Inc. Jun 2022 - Feb 20241 year 9 months "
        "Sector 62 Noida, Uttar Pradesh, India"
    )
    years = estimate_years_from_text(text)
    assert years is not None
    assert 1.5 <= years <= 2.0
    assert experience_within_range(
        years=years,
        exp_min=7,
        exp_max=None,
        title="Spine 2D Animator",
        reject_unknown=True,
    ) is False


def test_absurd_stored_experience_is_unknown_and_rejected_for_band():
    assert experience_within_range(
        years=20241,
        exp_min=7,
        exp_max=None,
        title="Spine 2D Animator",
        reject_unknown=True,
    ) is False


def test_separate_roles_sum_worked_time_without_counting_gap():
    years = estimate_years_from_career_dates(
        "Animator Jan 2018 - Jan 2020 Senior Animator Jan 2021 - Jan 2024"
    )
    assert years == 5.2


def test_overlapping_roles_are_counted_only_once():
    years = estimate_years_from_career_dates(
        "Animator Jan 2018 - Jan 2022 Freelance Jan 2020 - Jan 2024"
    )
    assert years == 6.1


def test_date_ranges_win_over_ambiguous_explicit_duration():
    years = estimate_years_from_text(
        "Animator Jan 2018 - Jan 2020 Senior Animator Jan 2021 - Jan 2024 12 years"
    )
    assert years == 5.2


def test_anas_linkedin_timeline_is_about_five_point_four_years():
    rows = [
        {"start_date": "2021-04", "end_date": "2022-04"},
        {"start_date": "2022-04", "end_date": "2024-03"},
        {"start_date": "2024-03", "end_date": "2025-08"},
        {"start_date": "2025-09", "end_date": "2026-03"},
        {"start_date": "2026-04", "end_date": "2026-08"},
    ]
    assert estimate_years_from_experience_rows(rows) == 5.4
