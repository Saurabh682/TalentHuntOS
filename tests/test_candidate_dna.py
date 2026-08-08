import pytest
from unittest.mock import MagicMock
from app.intelligence.candidate_dna import (
    CandidateDNA,
    _compute_text_hash,
    _simple_text_embedding,
    _calculate_seniority_index,
    _calculate_tenure_and_trajectory,
    _extract_culture_signals,
    _extract_domain_expertise,
    generate_candidate_dna,
    _cosine_similarity,
    calculate_dna_similarity,
    find_similar_candidates,
)

@pytest.fixture
def mock_candidate():
    candidate = MagicMock()
    candidate.id = 1
    candidate.full_name = "Jane Doe"
    candidate.github_url = "https://github.com/janedoe"
    candidate.linkedin_url = "https://linkedin.com/in/janedoe"
    candidate.portfolio_url = None
    candidate.current_title = "Senior Software Engineer"
    candidate.current_company = "Tech Corp"
    candidate.experience_years = 5.0
    
    exp1 = MagicMock()
    exp1.title = "Senior Software Engineer"
    exp1.start_date = "2020-01-01"
    exp1.end_date = "Present"
    
    exp2 = MagicMock()
    exp2.title = "Software Engineer"
    exp2.start_date = "2018-01-01"
    exp2.end_date = "2020-01-01"

    candidate.experiences = [exp1, exp2]
    
    profile = MagicMock()
    profile.skills_json = '["python", "java", "aws"]'
    profile.headline = "Backend Developer"
    profile.summary = "Experienced in startup agile environments building microservices."
    profile.resume_text = "Led team to build microservices on AWS."
    candidate.profile = profile

    return candidate

def test_candidate_dna_dataclass():
    dna = CandidateDNA(candidate_id=1, full_name="John Doe", normalized_skills=["python"])
    dna_dict = dna.to_dict()
    assert dna_dict["candidate_id"] == 1
    assert dna_dict["full_name"] == "John Doe"
    assert dna_dict["normalized_skills"] == ["python"]
    
    dna_from_dict = CandidateDNA.from_dict(dna_dict)
    assert dna_from_dict.candidate_id == 1
    assert dna_from_dict.full_name == "John Doe"

def test_compute_text_hash():
    h1 = _compute_text_hash("test string")
    h2 = _compute_text_hash("test string")
    assert h1 == h2
    assert len(h1) == 16

def test_simple_text_embedding():
    vec = _simple_text_embedding("python java aws", dim=64)
    assert len(vec) == 64
    assert sum(v * v for v in vec) == pytest.approx(1.0, 0.01)

def test_calculate_seniority_index():
    assert _calculate_seniority_index("VP of Engineering", 10.0) >= 0.9
    assert _calculate_seniority_index("Junior Developer", 1.0) < 0.4
    assert _calculate_seniority_index("Senior Software Engineer", 5.0) > 0.6

def test_calculate_tenure_and_trajectory(mock_candidate):
    avg_tenure, stability, trajectory = _calculate_tenure_and_trajectory(mock_candidate.experiences)
    assert avg_tenure > 0
    assert stability > 0
    assert trajectory > 0

def test_extract_culture_signals(mock_candidate):
    signals = _extract_culture_signals(mock_candidate, mock_candidate.profile)
    assert signals["open_source_contributor"] > 0
    assert signals["thought_leadership"] > 0
    assert signals["startup_agility"] > 0
    assert signals["team_collaboration"] > 0

def test_extract_domain_expertise():
    expertise = _extract_domain_expertise(["python", "aws"], "Backend dev using Python and AWS")
    assert expertise["backend"] > 0
    assert expertise["cloud_devops"] > 0
    assert expertise["frontend"] == 0

def test_generate_candidate_dna(mock_candidate):
    dna = generate_candidate_dna(mock_candidate)
    assert dna.candidate_id == 1
    assert dna.full_name == "Jane Doe"
    assert "python" in dna.normalized_skills
    assert len(dna.skill_embedding) > 0
    assert dna.total_experience_years == 5.0

def test_cosine_similarity():
    vec1 = [1.0, 0.0]
    vec2 = [1.0, 0.0]
    assert _cosine_similarity(vec1, vec2) == pytest.approx(1.0)
    
    vec3 = [0.0, 1.0]
    assert _cosine_similarity(vec1, vec3) == pytest.approx(0.0)

def test_calculate_dna_similarity():
    dna1 = CandidateDNA(
        candidate_id=1, full_name="A", normalized_skills=["python", "aws"],
        skill_embedding=[1.0, 0.0], seniority_index=0.5, career_trajectory_score=0.5,
        domain_expertise={"backend": 0.8}, tenure_stability_score=0.8
    )
    dna2 = CandidateDNA(
        candidate_id=2, full_name="B", normalized_skills=["python", "aws"],
        skill_embedding=[1.0, 0.0], seniority_index=0.5, career_trajectory_score=0.5,
        domain_expertise={"backend": 0.8}, tenure_stability_score=0.8
    )
    score = calculate_dna_similarity(dna1, dna2)
    # the vectors, skills, seniority, trajectory, domains, and culture are identical
    # The max score is 1.0
    assert score == pytest.approx(1.0, 0.01)

def test_find_similar_candidates(mock_candidate):
    mock_db = MagicMock()
    # first call is for target candidate, second is for all candidates
    mock_target = mock_candidate
    
    mock_cand_2 = MagicMock()
    mock_cand_2.id = 2
    mock_cand_2.full_name = "John Smith"
    mock_cand_2.current_title = "Senior Software Engineer"
    mock_cand_2.current_company = "Other Corp"
    mock_cand_2.location = "Remote"
    mock_cand_2.experience_years = 5.0
    mock_cand_2.experiences = []
    mock_cand_2.profile = MagicMock()
    mock_cand_2.profile.skills_json = '["python", "aws"]'
    mock_cand_2.profile.headline = "Backend Developer"
    mock_cand_2.profile.summary = "Experienced in startup agile environments building microservices."
    mock_cand_2.profile.resume_text = "Led team to build microservices on AWS."
    
    mock_db.scalars().first.return_value = mock_target
    mock_db.scalars().all.return_value = [mock_cand_2]
    
    results = find_similar_candidates(mock_db, 1, top_k=5, threshold=0.1)
    
    assert len(results) == 1
    assert results[0]["candidate_id"] == 2
    assert "similarity_score" in results[0]
