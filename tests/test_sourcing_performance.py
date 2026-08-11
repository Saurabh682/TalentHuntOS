import time
import types
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.browser.page_reader import _expand_collapsibles
from app.candidates.models import Candidate
from app.hunts.models import HuntCandidate, HuntSearchConfig, TalentHunt
from app.hunts.web_sourcing import (
    _build_sourcing_queries,
    _ddg_search,
    _ddg_search_inner,
    _run_cancellable,
    _write_cached_search,
    source_candidates_for_hunt,
)
from app.copilot.direct_actions import parse_clear_and_source
from app.candidates.models import DiscoveryHuntMatch, DiscoveredProfile
from app.infrastructure.db import Base


class _FakeElement:
    def __init__(self, page):
        self.page = page

    def is_visible(self):
        return True

    def click(self, timeout):
        self.page.clicks += 1


class _FakeLocator:
    def __init__(self, page):
        self.page = page

    def count(self):
        return 6

    def nth(self, _index):
        return _FakeElement(self.page)


class _FakePage:
    def __init__(self):
        self.clicks = 0

    def locator(self, _selector):
        return _FakeLocator(self)

    def wait_for_timeout(self, _milliseconds):
        return None


def test_profile_expansion_uses_a_total_click_budget():
    page = _FakePage()
    assert _expand_collapsibles(page, max_clicks=5) == 5
    assert page.clicks == 5


def test_blocking_sourcing_call_has_a_hard_timeout():
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="timed out"):
        _run_cancellable(
            lambda: time.sleep(0.5),
            job_id=None,
            timeout_sec=0.05,
            poll_sec=0.01,
        )
    assert time.monotonic() - started < 0.25


def test_ddgs_uses_explicit_fast_backends(monkeypatch):
    calls = {}

    class FakeDDGS:
        def __init__(self, **kwargs):
            calls["init"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def text(self, query, **kwargs):
            calls["query"] = query
            calls["text"] = kwargs
            return [{
                "title": "Asha Rao - Spine Animator | LinkedIn",
                "href": "https://www.linkedin.com/in/asha-rao/",
                "body": "Spine Animator in Noida, India",
            }]

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FakeDDGS))
    hits, error = _ddg_search_inner("spine animator")

    assert error is None
    assert hits[0]["link"].endswith("/asha-rao/")
    assert calls["init"]["timeout"] <= 4
    assert calls["text"]["backend"] == "brave,yahoo,yandex,duckduckgo"


def test_naukri_command_and_queries_stay_source_specific():
    parsed = parse_clear_and_source("let's hunt 25 spine animators on naukri.com")
    assert parsed == {"clear": False, "target": 25, "platforms": ["naukri"]}

    queries = _build_sourcing_queries(
        role_label="Spine Animator",
        skill_bits=["Spine"],
        primary="Spine",
        exp_clause="3-8 years",
        loc="Noida, India",
        platforms=["naukri"],
    )
    assert queries
    assert all("site:naukri.com" in query for query in queries)
    assert all("linkedin.com" not in query for query in queries)


def test_three_digit_sourcing_target_is_preserved():
    parsed = parse_clear_and_source(
        "look for more leads for spine on naukri, around 100"
    )

    assert parsed == {"clear": False, "target": 100, "platforms": ["naukri"]}


def test_default_queries_interleave_profile_sources():
    queries = _build_sourcing_queries(
        role_label="Spine Animator",
        skill_bits=["Spine"],
        primary="Spine",
        exp_clause="3-8 years",
        loc="Noida, India",
    )
    first_domains = [query.rsplit("site:", 1)[-1] for query in queries[:6]]
    assert first_domains == [
        "linkedin.com/in",
        "naukri.com",
        "github.com",
        "behance.net",
        "artstation.com",
        "dribbble.com",
    ]


def test_search_reuses_persistent_cache_without_calling_provider(monkeypatch, tmp_path):
    cache_path = tmp_path / "search-cache.json"
    monkeypatch.setattr("app.hunts.web_sourcing._search_cache_path", lambda: cache_path)
    hit = {
        "title": "Asha Rao - Spine Animator | LinkedIn",
        "link": "https://www.linkedin.com/in/asha-rao/",
        "snippet": "Spine Animator in Noida, India",
    }
    _write_cached_search("spine animator", [hit])
    monkeypatch.setattr(
        "app.hunts.web_sourcing._ddg_search_inner",
        lambda *args, **kwargs: pytest.fail("fresh cache must bypass the provider"),
    )

    hits, error = _ddg_search("  SPINE   animator ", max_results=8, timeout_sec=1)

    assert error is None
    assert hits == [hit]


def test_search_backend_circuit_breaker_stops_after_three_failures(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'search-circuit.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("app.hunts.web_sourcing.SessionFactory", factory)

    with factory() as db:
        hunt = TalentHunt(
            title="Circuit Hunt",
            target_role="Spine Animator",
            location="Noida, India",
        )
        db.add(hunt)
        db.commit()
        hunt_id = hunt.id

    calls = []

    def failed_search(query, **kwargs):
        calls.append(query)
        return [], "provider unavailable"

    monkeypatch.setattr("app.hunts.web_sourcing._ddg_search", failed_search)
    result = source_candidates_for_hunt(
        hunt_id,
        role="Spine Animator",
        location="Noida, India",
        target_added=5,
        enrich_pages=False,
        verify_with_ai=False,
        time_budget_sec=180,
    )

    assert result["status"] == "search_failed"
    assert result["search_failures"] == 3
    assert len(calls) == 3
    assert "stopped early" in result["message"]


def test_disconnected_linkedin_uses_fast_snippet_fallback(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fast-source.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("app.hunts.web_sourcing.SessionFactory", factory)

    with factory() as db:
        hunt = TalentHunt(
            title="Fast Spine Hunt",
            target_role="Spine Animator",
            location="Noida, India",
        )
        db.add(hunt)
        db.flush()
        db.add(HuntSearchConfig(
            hunt_id=hunt.id,
            required_skills="Spine, 2D Animation",
            experience_years_min=7,
            locations="Noida, India",
        ))
        db.commit()
        hunt_id = hunt.id

    hit = {
        "title": "Asha Rao - Senior Spine Animator | LinkedIn",
        "link": "https://in.linkedin.com/in/asha-rao",
        "snippet": (
            "Asha Rao is a Spine Animator in Noida, India with 8 years of "
            "experience using Spine and 2D Animation."
        ),
    }
    monkeypatch.setattr(
        "app.hunts.web_sourcing._ddg_search",
        lambda *args, **kwargs: ([hit], None),
    )
    monkeypatch.setattr(
        "app.browser.page_reader.enrich_profile_from_url",
        lambda *args, **kwargs: pytest.fail("disconnected sourcing must not open profile pages"),
    )

    result = source_candidates_for_hunt(
        hunt_id,
        role="Spine Animator",
        skills="Spine, 2D Animation",
        location="Noida, India",
        target_added=1,
        verify_with_ai=False,
        time_budget_sec=30,
    )

    assert result["added"] == 1
    assert result["session_issue"]
    with factory() as db:
        assert db.query(Candidate).count() == 1
        assert db.query(HuntCandidate).count() == 1


def test_filtered_people_are_retained_in_raw_pool(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'raw-source.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("app.hunts.web_sourcing.SessionFactory", factory)

    with factory() as db:
        hunt = TalentHunt(
            title="Spine Hunt",
            target_role="Spine Animator",
            location="Noida, India",
        )
        db.add(hunt)
        db.commit()
        hunt_id = hunt.id

    unrelated = {
        "title": "Asha Rao - Chartered Accountant | Naukri",
        "link": "https://www.naukri.com/mnjuser/profile/asha-rao",
        "snippet": "Asha Rao is a chartered accountant in Noida, India.",
    }
    monkeypatch.setattr(
        "app.hunts.web_sourcing._ddg_search",
        lambda *args, **kwargs: ([unrelated], None),
    )

    result = source_candidates_for_hunt(
        hunt_id,
        role="Spine Animator",
        location="Noida, India",
        target_added=1,
        approval_required=True,
        platforms=["naukri"],
        time_budget_sec=30,
    )

    assert result["added"] == 0
    assert result["raw_pool_count"] == 1
    assert result["source_counts"]["naukri"]["queries"] > 0
    assert result["source_counts"]["naukri"]["hits"] > 0
    assert result["source_counts"]["naukri"]["filtered"] == 1
    with factory() as db:
        assert db.query(DiscoveredProfile).count() == 1
        match = db.query(DiscoveryHuntMatch).one()
        assert match.status == "filtered"
        assert "role mismatch" in (match.rejection_reason or "").lower()
