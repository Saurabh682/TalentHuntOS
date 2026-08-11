import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.candidates.models import Candidate
from app.candidates.profile_extract import (
    EducationDraft,
    ExperienceDraft,
    ProfileExtractSchema,
    extract_profile_from_text,
)
from app.candidates.service import create_candidate, replace_or_merge_profile_sections
from app.infrastructure.db import Base


def test_linkedin_sections_are_normalized(monkeypatch):
    structured = ProfileExtractSchema(
        full_name=" Radha Raman ",
        pronouns="He/Him",
        connection_degree="1st",
        connections_count=500,
        email="radha@example.com",
        phone="+91 99999 99999",
        location="Noida, Uttar Pradesh, India",
        current_title="3D Visualizer",
        current_company="Arrise Solutions (India) Pvt. Ltd.",
        headline="3D Visualizer | Studio Interior Designer | 14+ Years Experience",
        summary="I design live casino studio environments for global audiences.",
        highlights=["You both work at Arrise Solutions (India) Pvt. Ltd."],
        skills=["ZBrush", "3D Modeling", "ZBrush"],
        experiences=[ExperienceDraft(
            company=" Arrise Solutions (India) Pvt. Ltd. ",
            title=" 3D Visualizer / Studio Interior Designer ",
            employment_type="Full-time",
            location="Noida, Uttar Pradesh, India",
            start_date="2024-11",
            is_current=True,
            description="Designed 3D casino and game-show environments.",
            skills=["Autodesk 3ds Max", "Corona Renderer", "Autodesk 3ds Max"],
        )],
        educations=[EducationDraft(
            institution="Delhi University",
            degree="Bachelor's degree",
            field_of_study="Liberal Arts and Sciences/Liberal Studies",
            start_year=2008,
            end_year=2015,
        )],
    )
    monkeypatch.setattr(
        "app.ai.engine.ai_engine.generate_structured",
        lambda **kwargs: structured,
    )

    result = extract_profile_from_text("LinkedIn profile text with enough factual content.")

    assert result.full_name == "Radha Raman"
    assert result.current_company == "Arrise Solutions (India) Pvt. Ltd."
    assert result.skills == ["ZBrush", "3D Modeling"]
    assert result.experiences[0].skills == ["Autodesk 3ds Max", "Corona Renderer"]
    assert result.educations[0].institution == "Delhi University"


def test_linkedin_sections_persist_as_structured_candidate_data(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'linkedin.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("app.candidates.service._reindex_candidate", lambda *args: None)

    with factory() as db:
        candidate = create_candidate(db, full_name="Radha Raman")
        updated = replace_or_merge_profile_sections(
            db,
            candidate.id,
            full_name="Radha Raman",
            email="radha@example.com",
            phone="+91 99999 99999",
            location="Noida, Uttar Pradesh, India",
            current_title="3D Visualizer",
            current_company="Arrise Solutions (India) Pvt. Ltd.",
            pronouns="He/Him",
            connection_degree="1st",
            connections_count=500,
            profile_image_url="https://media.licdn.com/profile.jpg",
            headline="3D Visualizer | Studio Interior Designer",
            summary="Live casino studio environment designer.",
            highlights=["You both work at Arrise Solutions (India) Pvt. Ltd."],
            skills=["ZBrush", "3D Modeling"],
            experiences=[{
                "company": "Arrise Solutions (India) Pvt. Ltd.",
                "title": "3D Visualizer / Studio Interior Designer",
                "employment_type": "Full-time",
                "location": "Noida, Uttar Pradesh, India",
                "start_date": "2024-11",
                "is_current": True,
                "description": "Designed 3D casino environments.",
                "skills": ["Autodesk 3ds Max", "Corona Renderer"],
            }],
            educations=[{
                "institution": "MAAC",
                "degree": "Advanced diploma",
                "field_of_study": "3D arts and animation",
                "start_year": 2008,
                "end_year": 2011,
                "grade": "A+",
                "activities": "3D Modeling, Texturing, Sculpting",
                "description": "Rendering and Post Production",
            }],
            mode="replace",
            record_history=False,
        )

        assert updated is not None
        stored = db.get(Candidate, candidate.id)
        assert stored.current_company == "Arrise Solutions (India) Pvt. Ltd."
        assert stored.connections_count == 500
        assert stored.profile_image_url.endswith("profile.jpg")
        assert json.loads(stored.profile.highlights_json)[0].startswith("You both work")
        assert stored.experiences[0].employment_type == "Full-time"
        assert json.loads(stored.experiences[0].skills_json) == [
            "Autodesk 3ds Max",
            "Corona Renderer",
        ]
        assert stored.educations[0].grade == "A+"
        assert stored.educations[0].activities.startswith("3D Modeling")
