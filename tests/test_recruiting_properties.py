"""Bounded property tests for core recruiting and Copilot invariants."""

from __future__ import annotations

import pytest
hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.actions.history import record_action, undo_action
from app.candidates.discovery import normalize_profile_url
from app.candidates.models import Candidate
from app.copilot.direct_actions import parse_pending_hunt_clear_confirmation
from app.hunts.experience import estimate_years_from_experience_rows
from app.infrastructure.db import Base

PROFILE_SLUGS = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=1,
    max_size=30,
).filter(lambda value: value.strip("-"))


@settings(max_examples=30, deadline=None)
@given(slug=PROFILE_SLUGS)
def test_linkedin_identity_is_stable_across_locale_case_and_tracking(slug):
    canonical = f"https://linkedin.com/in/{slug.lower()}"
    variants = [
        f"https://www.linkedin.com/in/{slug}/",
        f"https://in.linkedin.com/in/{slug.upper()}?trk=people-search#about",
        f"linkedin.com/in/{slug}?utm_source=talenthunt",
    ]
    assert {normalize_profile_url(value) for value in variants} == {canonical}


@st.composite
def overlapping_month_ranges(draw):
    first_start = draw(st.integers(min_value=2000 * 12, max_value=2015 * 12))
    first_length = draw(st.integers(min_value=6, max_value=60))
    second_start = draw(
        st.integers(min_value=first_start, max_value=first_start + first_length - 1)
    )
    second_length = draw(st.integers(min_value=1, max_value=60))
    return (first_start, first_start + first_length - 1), (
        second_start,
        second_start + second_length - 1,
    )


def _month_text(month_index: int) -> str:
    year, zero_based_month = divmod(month_index, 12)
    return f"{year:04d}-{zero_based_month + 1:02d}"


@settings(max_examples=40, deadline=None)
@given(intervals=overlapping_month_ranges())
def test_overlapping_experience_counts_each_calendar_month_once(intervals):
    rows = [
        {"start_date": _month_text(start), "end_date": _month_text(end)} for start, end in intervals
    ]
    unique_months = set()
    for start, end in intervals:
        unique_months.update(range(start, end + 1))
    expected = round(len(unique_months) / 12.0, 1)

    assert estimate_years_from_experience_rows(rows) == expected
    assert estimate_years_from_experience_rows(reversed(rows)) == expected


@settings(max_examples=30, deadline=None)
@given(
    hunt_id=st.integers(min_value=1, max_value=100_000),
    count=st.integers(min_value=1, max_value=500),
)
def test_copilot_confirmation_is_bound_to_the_previewed_hunt_and_count(hunt_id, count):
    messages = [
        {
            "role": "assistant",
            "content": (
                f"Removal preview. pending-action:hunt-clear:{hunt_id}:{count} "
                f"Confirm removal of {count} candidates."
            ),
        }
    ]

    assert parse_pending_hunt_clear_confirmation("yes", messages) == {
        "hunt_id": hunt_id,
        "expected_count": count,
    }
    assert (
        parse_pending_hunt_clear_confirmation(
            f"confirm removal of {count + 1} candidates",
            messages,
        )
        is None
    )


@settings(max_examples=12, deadline=None)
@given(
    statuses=st.lists(
        st.sampled_from(["Active", "Passive", "Sourced", "Placed"]),
        min_size=1,
        max_size=8,
    )
)
def test_archive_compensation_restores_every_original_candidate_status(statuses):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as db:
        candidates = [
            Candidate(full_name=f"Property Candidate {index}", status=status)
            for index, status in enumerate(statuses)
        ]
        db.add_all(candidates)
        db.flush()
        previous = {str(candidate.id): candidate.status for candidate in candidates}
        for candidate in candidates:
            candidate.status = "Archived"
        action = record_action(
            db,
            action_type="archive_candidates",
            summary="Property-test candidate archive",
            payload={"candidate_ids": [candidate.id for candidate in candidates]},
            undo_payload={"previous_statuses": previous},
        )
        action_id = action.id
        db.commit()

        undo_action(db, action_id)
        restored = [candidate.status for candidate in db.query(Candidate).order_by(Candidate.id)]
        assert restored == statuses
