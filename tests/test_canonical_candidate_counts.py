from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analytics.service import get_hunt_funnel_data, get_kpi_summary
from app.candidates.models import Candidate
from app.hunts.models import HuntCandidate, HuntStage, TalentHunt
from app.hunts.pipeline import add_candidate_to_hunt, get_pipeline_data
from app.hunts.service import get_hunt_metrics
from app.infrastructure.db import Base


def test_pipeline_and_dashboard_counts_follow_visible_master_candidates(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'canonical.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as db:
        hunt = TalentHunt(title="Canonical Hunt", status="Active")
        db.add(hunt)
        db.flush()
        stage = HuntStage(hunt_id=hunt.id, name="Sourced", position=0)
        active = Candidate(full_name="Visible", status="Active")
        archived = Candidate(full_name="Hidden", status="Archived")
        db.add_all([stage, active, archived])
        db.flush()
        db.add_all([
            HuntCandidate(hunt_id=hunt.id, stage_id=stage.id, candidate_id=active.id, full_name=active.full_name),
            HuntCandidate(hunt_id=hunt.id, stage_id=stage.id, candidate_id=archived.id, full_name=archived.full_name),
            HuntCandidate(hunt_id=hunt.id, stage_id=stage.id, candidate_id=None, full_name="Legacy orphan"),
        ])
        db.commit()

        assert get_pipeline_data(db, hunt.id)["total_candidates"] == 1
        assert get_hunt_metrics(db, hunt.id, reconcile=False)["total_candidates"] == 1
        assert get_kpi_summary(db)["total_sourced"] == 1
        funnel = get_hunt_funnel_data(db)
        assert funnel["total_candidates"] == 1
        assert funnel["stages"][0]["count"] == 1


def test_pipeline_add_without_candidate_id_creates_canonical_master(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'canonical-add.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as db:
        hunt = TalentHunt(title="Canonical Add", status="Active")
        db.add(hunt)
        db.flush()
        db.add(HuntStage(hunt_id=hunt.id, name="Sourced", position=0))
        db.commit()

        row = add_candidate_to_hunt(
            db,
            hunt_id=hunt.id,
            full_name="Canonical Person",
            email="canonical@example.com",
            current_title="Backend Engineer",
            match_score=91,
        )

        assert row.candidate_id is not None
        assert row.candidate is not None
        assert row.candidate.full_name == "Canonical Person"
        assert get_pipeline_data(db, hunt.id)["total_candidates"] == 1
