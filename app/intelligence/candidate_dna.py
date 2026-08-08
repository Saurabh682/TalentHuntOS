"""Candidate DNA fingerprinting and similarity matching logic for TalentHunt OS."""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.candidates.models import Candidate, CandidateProfile, CandidateExperience
from app.candidates.search import candidate_search_index

logger = logging.getLogger("talenthunt.intelligence.candidate_dna")


@dataclass
class CandidateDNA:
    """Normalized DNA fingerprint for candidate similarity and career pattern matching.

    Attributes:
        candidate_id (int): The unique identifier of the candidate.
        full_name (str): The full name of the candidate.
        normalized_skills (List[str]): A list of normalized skills.
        skill_embedding (List[float]): A numerical vector embedding of skills and text.
        total_experience_years (float): Total years of professional experience.
        avg_job_tenure_years (float): Average tenure per job in years.
        tenure_stability_score (float): Score indicating stability (0.0=hopper, 1.0=stable).
        seniority_index (float): Score indicating seniority level (0.0=entry, 1.0=exec).
        career_trajectory_score (float): Score indicating career growth rate.
        culture_signals (Dict[str, float]): Scores mapping to cultural attributes.
        domain_expertise (Dict[str, float]): Scores mapping to domain categories.
        fingerprint_hash (str): A unique string hash identifying this DNA signature.
        created_at (str): ISO formatted creation timestamp.
    """
    candidate_id: int
    full_name: str
    normalized_skills: List[str] = field(default_factory=list)
    skill_embedding: List[float] = field(default_factory=list)
    total_experience_years: float = 0.0
    avg_job_tenure_years: float = 0.0
    tenure_stability_score: float = 0.5  # 0.0 (job hopper) to 1.0 (highly stable)
    seniority_index: float = 0.5  # 0.0 (entry) to 1.0 (executive)
    career_trajectory_score: float = 0.5  # 0.0 (flat) to 1.0 (rapid promotion/growth)
    culture_signals: Dict[str, float] = field(default_factory=dict)
    domain_expertise: Dict[str, float] = field(default_factory=dict)
    fingerprint_hash: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize CandidateDNA to a dictionary.

        Returns:
            Dict[str, Any]: The dictionary representation of the CandidateDNA.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateDNA":
        """Deserialize CandidateDNA from a dictionary.

        Args:
            data (Dict[str, Any]): Dictionary containing CandidateDNA attributes.

        Returns:
            CandidateDNA: An instance of CandidateDNA.
        """
        return cls(**data)


def _compute_text_hash(text: str) -> str:
    """Generate SHA256 hash for raw text fingerprinting.

    Args:
        text (str): The raw text to hash.

    Returns:
        str: A 16-character hexadecimal hash string.
    """
    try:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    except Exception as e:
        logger.error(f"Error computing text hash: {e}")
        return ""


def _simple_text_embedding(text: str, dim: int = 64) -> List[float]:
    """Fallback hash-based vector embedding if FastEmbed/LM is unavailable.

    Args:
        text (str): The text to embed.
        dim (int, optional): The dimensionality of the embedding. Defaults to 64.

    Returns:
        List[float]: A normalized vector representing the text.
    """
    vec = [0.0] * dim
    try:
        words = text.lower().split()
        if not words:
            return vec
        for word in words:
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            val = ((h >> 8) % 100) / 100.0 - 0.5
            vec[idx] += val

        magnitude = math.sqrt(sum(x * x for x in vec))
        if magnitude > 0:
            vec = [x / magnitude for x in vec]
    except Exception as e:
        logger.error(f"Error generating simple text embedding: {e}")
        
    return vec


def _calculate_seniority_index(title: Optional[str], experience_years: float) -> float:
    """Calculate normalized seniority index from title and years of experience.

    Args:
        title (Optional[str]): The job title of the candidate.
        experience_years (float): The total years of experience.

    Returns:
        float: The seniority index ranging from 0.1 to 1.0.
    """
    title_lower = (title or "").lower()

    score = 0.3  # Default mid-junior
    if any(term in title_lower for term in ["vp", "vice president", "c-level", "chief", "cto", "cio", "director", "head of"]):
        score = 0.95
    elif any(term in title_lower for term in ["principal", "staff", "architect", "lead", "manager"]):
        score = 0.8
    elif any(term in title_lower for term in ["senior", "sr", "lead"]):
        score = 0.65
    elif any(term in title_lower for term in ["mid", "intermediate"]):
        score = 0.45
    elif any(term in title_lower for term in ["junior", "jr", "associate", "intern", "trainee"]):
        score = 0.2

    exp_boost = min(experience_years / 15.0, 0.3)
    return round(min(1.0, max(0.1, (score * 0.7) + exp_boost)), 2)


def _calculate_tenure_and_trajectory(experiences: List[CandidateExperience]) -> Tuple[float, float, float]:
    """Calculate avg job tenure, stability score, and career trajectory score.

    Args:
        experiences (List[CandidateExperience]): A list of candidate experiences.

    Returns:
        Tuple[float, float, float]: A tuple containing average tenure, stability score, 
            and career trajectory score.
    """
    if not experiences:
        return 0.0, 0.5, 0.5

    tenures: List[float] = []
    titles: List[str] = []

    for exp in experiences:
        if exp.title:
            titles.append(exp.title.lower())
        dur = 2.0
        if exp.start_date:
            try:
                start_year = int(exp.start_date[:4])
                end_year = int(exp.end_date[:4]) if exp.end_date and exp.end_date.lower() != "present" else datetime.now().year
                dur = max(0.5, float(end_year - start_year))
            except (ValueError, TypeError) as e:
                logger.debug(f"Date parsing error for tenure calculation: {e}")
                dur = 2.0
            except Exception as e:
                logger.error(f"Unexpected error calculating tenure: {e}")
                dur = 2.0
        tenures.append(dur)

    avg_tenure = sum(tenures) / len(tenures) if tenures else 2.0

    if avg_tenure >= 3.0:
        stability = 0.9
    elif avg_tenure >= 2.0:
        stability = 0.75
    elif avg_tenure >= 1.0:
        stability = 0.5
    else:
        stability = 0.25

    seniority_levels = ["intern", "junior", "engineer", "developer", "senior", "lead", "principal", "staff", "manager", "director", "head", "vp"]
    progression_steps = 0
    
    try:
        if len(titles) >= 2:
            earliest_title = titles[-1]
            latest_title = titles[0]

            earliest_idx = next((i for i, s in enumerate(seniority_levels) if s in earliest_title), 2)
            latest_idx = next((i for i, s in enumerate(seniority_levels) if s in latest_title), 2)

            progression_steps = latest_idx - earliest_idx
    except Exception as e:
        logger.error(f"Error calculating career trajectory: {e}")

    trajectory = 0.5 + (progression_steps * 0.15)
    trajectory = round(min(1.0, max(0.1, trajectory)), 2)

    return round(avg_tenure, 1), round(stability, 2), round(trajectory, 2)


def _extract_culture_signals(candidate: Candidate, profile: Optional[CandidateProfile]) -> Dict[str, float]:
    """Extract culture and work style signals (0.0 to 1.0 scores).

    Args:
        candidate (Candidate): The candidate model instance.
        profile (Optional[CandidateProfile]): The candidate's profile instance.

    Returns:
        Dict[str, float]: A dictionary mapping culture signal names to scores.
    """
    signals = {
        "open_source_contributor": 0.0,
        "thought_leadership": 0.0,
        "startup_agility": 0.0,
        "enterprise_scale": 0.0,
        "team_collaboration": 0.7,
    }

    if candidate.github_url:
        signals["open_source_contributor"] = 0.85

    if candidate.portfolio_url or candidate.linkedin_url:
        signals["thought_leadership"] = 0.65

    summary_text = f"{(profile.summary or '') if profile else ''} {(profile.resume_text or '') if profile else ''}"
    summary_lower = summary_text.lower()

    if any(w in summary_lower for w in ["startup", "agile", "0 to 1", "mvp", "fast-paced", "scrum"]):
        signals["startup_agility"] = 0.85

    if any(w in summary_lower for w in ["enterprise", "scale", "million users", "distributed", "microservices"]):
        signals["enterprise_scale"] = 0.85

    if any(w in summary_lower for w in ["led team", "mentored", "cross-functional", "collaborated"]):
        signals["team_collaboration"] = 0.9

    return signals


def _extract_domain_expertise(skills: List[str], text_corpus: str) -> Dict[str, float]:
    """Categorize candidate domain expertise weights.

    Args:
        skills (List[str]): A list of candidate skills.
        text_corpus (str): The textual corpus related to the candidate.

    Returns:
        Dict[str, float]: A dictionary mapping domain categories to expertise scores.
    """
    domains = {
        "backend": ["python", "java", "node", "go", "fastapi", "django", "postgres", "sql", "redis"],
        "frontend": ["react", "vue", "angular", "typescript", "javascript", "tailwind", "css", "html", "nicegui"],
        "ai_ml": ["pytorch", "tensorflow", "scikit-learn", "langchain", "llm", "rag", "embeddings", "nlp", "ai"],
        "cloud_devops": ["aws", "docker", "kubernetes", "gcp", "azure", "ci/cd", "terraform", "linux"],
        "management": ["agile", "scrum", "product", "hiring", "roadmap", "leadership", "stakeholder"],
    }

    skills_lower = [s.lower() for s in skills]
    text_lower = text_corpus.lower()

    expertise: Dict[str, float] = {}
    for domain, keywords in domains.items():
        matches = sum(1 for kw in keywords if kw in skills_lower or kw in text_lower)
        score = round(min(1.0, matches / 3.0), 2)
        expertise[domain] = score

    return expertise


def generate_candidate_dna(candidate: Candidate) -> CandidateDNA:
    """Generate normalized DNA fingerprint for a candidate.

    Args:
        candidate (Candidate): The candidate for which to generate DNA.

    Returns:
        CandidateDNA: The generated DNA fingerprint.
    """
    profile = candidate.profile

    skills: List[str] = []
    if profile and profile.skills_json:
        try:
            skills = json.loads(profile.skills_json)
            if not isinstance(skills, list):
                skills = []
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for skills_json of candidate {candidate.id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading skills_json for candidate {candidate.id}: {e}")

    text_corpus = f"{candidate.full_name} {candidate.current_title or ''} {candidate.current_company or ''} {' '.join(skills)} "
    if profile:
        text_corpus += f"{profile.headline or ''} {profile.summary or ''} {profile.resume_text or ''}"

    embedding: List[float] = []
    try:
        if candidate_search_index._embedder:
            emb_gen = list(candidate_search_index._embedder.embed([text_corpus]))
            if emb_gen and len(emb_gen) > 0:
                embedding = emb_gen[0].tolist()
    except Exception as e:
        logger.warning(f"FastEmbed failed for DNA embedding: {e}")

    if not embedding:
        embedding = _simple_text_embedding(text_corpus, dim=64)

    exp_years = candidate.experience_years or 0.0
    avg_tenure, stability_score, trajectory_score = _calculate_tenure_and_trajectory(candidate.experiences)
    seniority = _calculate_seniority_index(candidate.current_title, exp_years)

    culture_signals = _extract_culture_signals(candidate, profile)
    domain_expertise = _extract_domain_expertise(skills, text_corpus)

    fp_hash = _compute_text_hash(text_corpus + f"_{exp_years}_{seniority}")

    return CandidateDNA(
        candidate_id=candidate.id,
        full_name=candidate.full_name,
        normalized_skills=skills,
        skill_embedding=embedding,
        total_experience_years=exp_years,
        avg_job_tenure_years=avg_tenure,
        tenure_stability_score=stability_score,
        seniority_index=seniority,
        career_trajectory_score=trajectory_score,
        culture_signals=culture_signals,
        domain_expertise=domain_expertise,
        fingerprint_hash=fp_hash,
    )


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two vector lists.

    Args:
        vec1 (List[float]): The first vector.
        vec2 (List[float]): The second vector.

    Returns:
        float: The cosine similarity score, bounded between 0.0 and 1.0.
    """
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
        
    try:
        dot = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = math.sqrt(sum(a * a for a in vec1))
        mag2 = math.sqrt(sum(b * b for b in vec2))
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return max(0.0, min(1.0, dot / (mag1 * mag2)))
    except Exception as e:
        logger.error(f"Error computing cosine similarity: {e}")
        return 0.0


def calculate_dna_similarity(dna1: CandidateDNA, dna2: CandidateDNA) -> float:
    """Calculate multi-dimensional DNA similarity score (0.0 to 1.0) between two candidate DNAs.

    Args:
        dna1 (CandidateDNA): The first candidate's DNA.
        dna2 (CandidateDNA): The second candidate's DNA.

    Returns:
        float: A composite similarity score from 0.0 to 1.0.
    """
    try:
        vec_sim = _cosine_similarity(dna1.skill_embedding, dna2.skill_embedding)

        s1 = set(s.lower() for s in dna1.normalized_skills)
        s2 = set(s.lower() for s in dna2.normalized_skills)
        jaccard_sim = len(s1.intersection(s2)) / len(s1.union(s2)) if s1.union(s2) else 0.0

        seniority_diff = abs(dna1.seniority_index - dna2.seniority_index)
        trajectory_diff = abs(dna1.career_trajectory_score - dna2.career_trajectory_score)
        seniority_sim = max(0.0, 1.0 - (seniority_diff + trajectory_diff) / 2.0)

        d_sims: List[float] = []
        all_domains = set(dna1.domain_expertise.keys()).union(set(dna2.domain_expertise.keys()))
        for dom in all_domains:
            val1 = dna1.domain_expertise.get(dom, 0.0)
            val2 = dna2.domain_expertise.get(dom, 0.0)
            d_sims.append(1.0 - abs(val1 - val2))
        domain_sim = sum(d_sims) / len(d_sims) if d_sims else 0.5

        stab_diff = abs(dna1.tenure_stability_score - dna2.tenure_stability_score)
        culture_sim = max(0.0, 1.0 - stab_diff)

        final_score = (vec_sim * 0.40) + (jaccard_sim * 0.20) + (seniority_sim * 0.15) + (domain_sim * 0.15) + (culture_sim * 0.10)
        return round(final_score, 4)
    except Exception as e:
        logger.error(f"Error calculating DNA similarity: {e}")
        return 0.0


def find_similar_candidates(
    db: Session,
    target_candidate_id: int,
    top_k: int = 5,
    threshold: float = 0.4,
) -> List[Dict[str, Any]]:
    """Find candidates in DB with highest DNA similarity to target candidate.

    Args:
        db (Session): The database session.
        target_candidate_id (int): The ID of the target candidate.
        top_k (int, optional): The maximum number of similar candidates to return. Defaults to 5.
        threshold (float, optional): The minimum similarity score to include in results. Defaults to 0.4.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries representing similar candidates.
    """
    try:
        stmt = select(Candidate).options(
            selectinload(Candidate.profile),
            selectinload(Candidate.experiences),
            selectinload(Candidate.educations)
        ).where(Candidate.id == target_candidate_id)
        target_cand = db.scalars(stmt).first()
        if not target_cand:
            logger.warning(f"Target candidate {target_candidate_id} not found.")
            return []

        target_dna = generate_candidate_dna(target_cand)

        all_cands_stmt = select(Candidate).options(
            selectinload(Candidate.profile),
            selectinload(Candidate.experiences),
            selectinload(Candidate.educations)
        ).where(Candidate.id != target_candidate_id, Candidate.status != "Archived")
        all_candidates = db.scalars(all_cands_stmt).all()

        results: List[Dict[str, Any]] = []
        for cand in all_candidates:
            cand_dna = generate_candidate_dna(cand)
            sim_score = calculate_dna_similarity(target_dna, cand_dna)
            if sim_score >= threshold:
                results.append({
                    "candidate_id": cand.id,
                    "full_name": cand.full_name,
                    "current_title": cand.current_title,
                    "current_company": cand.current_company,
                    "location": cand.location,
                    "similarity_score": sim_score,
                    "match_percentage": int(round(sim_score * 100)),
                    "common_skills": list(set(target_dna.normalized_skills).intersection(set(cand_dna.normalized_skills))),
                    "dna_fingerprint": cand_dna.to_dict(),
                })

        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results[:top_k]
    except SQLAlchemyError as e:
        logger.error(f"Database error finding similar candidates for ID {target_candidate_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in find_similar_candidates: {e}")
        return []
