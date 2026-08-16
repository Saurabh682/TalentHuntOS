from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.hunts.models  # noqa: F401
from app.candidates.discovery import (
    common_pool_count,
    common_pool_linked_candidate_count,
    list_common_pool_profiles,
)
from app.candidates.models import Candidate, DiscoveredProfile
from app.candidates.service import list_candidates
from app.infrastructure.db import Base
from app.infrastructure.migrations import _candidate_full_text_search


def _session(tmp_path, *, with_fts: bool):
    engine = create_engine(f"sqlite:///{tmp_path / 'search.db'}")
    Base.metadata.create_all(engine)
    if with_fts:
        with engine.begin() as conn:
            _candidate_full_text_search(conn)
    return sessionmaker(bind=engine)()


def test_candidate_fts_prefix_search_tracks_insert_update_and_delete(tmp_path):
    db = _session(tmp_path, with_fts=True)
    candidate = Candidate(
        full_name="Mina Patel",
        current_title="Senior Spine Animator",
        current_company="Motion Forge",
        location="Noida, India",
        status="Active",
    )
    db.add(candidate)
    db.commit()

    assert [row.id for row in list_candidates(db, search="animat")] == [candidate.id]
    assert [row.id for row in list_candidates(db, search="motion noi")] == [candidate.id]

    candidate.current_title = "Compositor"
    db.commit()
    assert list_candidates(db, search="animat") == []
    assert [row.id for row in list_candidates(db, search="composit")] == [candidate.id]

    db.delete(candidate)
    db.commit()
    assert list_candidates(db, search="composit") == []
    db.close()


def test_common_pool_fts_is_shared_by_rows_and_counts(tmp_path):
    db = _session(tmp_path, with_fts=True)
    profile = DiscoveredProfile(
        normalized_url="https://example.test/people/42",
        source_url="https://example.test/people/42",
        platform="ArtStation",
        full_name="Asha Rao",
        headline="Creature Animator and Rigger",
        current_company="Pixel House",
        location="Bengaluru, India",
        snippet="Spine and skeletal animation portfolio",
        status="raw",
    )
    db.add(profile)
    db.commit()

    rows = list_common_pool_profiles(db, search="skelet portf")
    assert [row.id for row in rows] == [profile.id]
    assert common_pool_count(db, search="skelet portf") == 1
    assert common_pool_linked_candidate_count(db, search="skelet portf") == 0
    db.close()


def test_search_falls_back_to_like_when_fts_schema_is_unavailable(tmp_path):
    db = _session(tmp_path, with_fts=False)
    db.add(
        Candidate(full_name="Fallback Candidate", current_title="Lighting Artist", status="Active")
    )
    db.commit()

    assert [row.full_name for row in list_candidates(db, search="Lighting")] == [
        "Fallback Candidate"
    ]
    db.close()
