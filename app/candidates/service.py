"""Standard CRUD and management service for Candidate database.

This module provides service functions to manage Candidate entities, including
creation, retrieval, updating, deletion, and related sub-entities like tags, notes,
experiences, and educations. It handles database transactions and integrates
with a vector search index for candidate matching.
"""

import json
import logging
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, or_
from sqlalchemy.exc import SQLAlchemyError

from app.candidates.models import (
    Candidate,
    CandidateProfile,
    CandidateTag,
    CandidateExperience,
    CandidateEducation,
    CandidateNote,
)

logger = logging.getLogger("talenthunt.candidates.service")


def create_candidate(
    db: Session,
    full_name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    location: Optional[str] = None,
    current_title: Optional[str] = None,
    current_company: Optional[str] = None,
    experience_years: Optional[float] = None,
    linkedin_url: Optional[str] = None,
    github_url: Optional[str] = None,
    portfolio_url: Optional[str] = None,
    status: str = "Active",
    headline: Optional[str] = None,
    summary: Optional[str] = None,
    resume_text: Optional[str] = None,
    skills: Optional[List[str]] = None,
    languages: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    ai_evaluation: Optional[str] = None,
) -> Optional[Candidate]:
    """Create a new Candidate and associated CandidateProfile.

    Args:
        db (Session): The SQLAlchemy database session.
        full_name (str): The full name of the candidate.
        email (Optional[str], optional): Email address. Defaults to None.
        phone (Optional[str], optional): Phone number. Defaults to None.
        location (Optional[str], optional): Geographic location. Defaults to None.
        current_title (Optional[str], optional): Current job title. Defaults to None.
        current_company (Optional[str], optional): Current company. Defaults to None.
        experience_years (Optional[float], optional): Years of experience. Defaults to None.
        linkedin_url (Optional[str], optional): LinkedIn profile URL. Defaults to None.
        github_url (Optional[str], optional): GitHub profile URL. Defaults to None.
        portfolio_url (Optional[str], optional): Portfolio website URL. Defaults to None.
        status (str, optional): Candidate status. Defaults to "Active".
        headline (Optional[str], optional): Professional headline. Defaults to None.
        summary (Optional[str], optional): Professional summary. Defaults to None.
        resume_text (Optional[str], optional): Full text of the resume. Defaults to None.
        skills (Optional[List[str]], optional): List of skills. Defaults to None.
        languages (Optional[List[str]], optional): List of spoken languages. Defaults to None.
        tags (Optional[List[str]], optional): List of tags to associate. Defaults to None.
        ai_evaluation (Optional[str], optional): AI generated evaluation. Defaults to None.

    Returns:
        Optional[Candidate]: The created Candidate object, or None if creation fails.
    """
    try:
        from sqlalchemy import func
        stmt = select(Candidate).where(func.lower(Candidate.full_name) == full_name.strip().lower()).with_for_update()
        existing = db.scalars(stmt).all()
        for ec in existing:
            # Identity Resolution Chaos check ("John Smith" problem)
            if linkedin_url and ec.linkedin_url and linkedin_url.strip().lower() != ec.linkedin_url.strip().lower():
                continue
            if github_url and ec.github_url and github_url.strip().lower() != ec.github_url.strip().lower():
                continue
                
            is_match = False
            if current_company and ec.current_company and current_company.lower() in ec.current_company.lower():
                is_match = True
            elif location and ec.location and location.lower() in ec.location.lower():
                is_match = True
            elif not current_company and not ec.current_company:
                is_match = True
                
            if is_match:
                # Enrich existing profile
                if current_title and not ec.current_title:
                    ec.current_title = current_title
                if experience_years and (not ec.experience_years or ec.experience_years < experience_years):
                    ec.experience_years = experience_years
                if skills and ec.profile:
                    try:
                        import json
                        old_skills = json.loads(ec.profile.skills_json) if ec.profile.skills_json else []
                        merged_skills = list(set(old_skills + skills))
                        ec.profile.skills_json = json.dumps(merged_skills)
                    except Exception:
                        pass
                db.commit()
                db.refresh(ec)
                return ec
    except Exception as e:
        logger.error(f"Error checking duplicates for {full_name}: {e}")

    try:
        candidate = Candidate(
            full_name=full_name,
            email=email,
            phone=phone,
            location=location,
            current_title=current_title,
            current_company=current_company,
            experience_years=experience_years,
            linkedin_url=linkedin_url,
            github_url=github_url,
            portfolio_url=portfolio_url,
            status=status,
        )
        db.add(candidate)
        db.flush()

        try:
            skills_json = json.dumps(skills) if skills else json.dumps([])
            languages_json = json.dumps(languages) if languages else json.dumps(["English"])
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize JSON for candidate {full_name}: {e}")
            skills_json = "[]"
            languages_json = '["English"]'

        profile = CandidateProfile(
            candidate_id=candidate.id,
            headline=headline or (f"{current_title} at {current_company}" if current_title and current_company else current_title),
            summary=summary,
            resume_text=resume_text,
            skills_json=skills_json,
            languages_json=languages_json,
            ai_evaluation=ai_evaluation,
            chroma_doc_id=f"cand_{candidate.id}",
        )
        db.add(profile)

        if tags:
            for tag_name in tags:
                tag = CandidateTag(candidate_id=candidate.id, tag_name=tag_name, color="#00d4aa")
                db.add(tag)

        db.commit()
        db.refresh(candidate)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error while creating candidate {full_name}: {e}")
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error while creating candidate {full_name}: {e}")
        return None

    # Sync candidate to vector index
    try:
        from app.candidates.search import candidate_search_index
        candidate_search_index.index_candidate(
            candidate_id=candidate.id,
            full_name=candidate.full_name,
            title=candidate.current_title or "",
            skills=skills or [],
            summary=summary or "",
            resume_text=resume_text or "",
            location=candidate.location or "",
        )
    except ImportError as e:
        logger.error(f"Failed to import search index: {e}")
    except Exception as e:
        logger.warning(f"Vector search indexing failed for candidate {candidate.id}: {e}")

    return candidate


def get_candidate(db: Session, candidate_id: int) -> Optional[Candidate]:
    """Retrieve a single Candidate by ID.

    Args:
        db (Session): The SQLAlchemy database session.
        candidate_id (int): The ID of the candidate to retrieve.

    Returns:
        Optional[Candidate]: The retrieved Candidate object, or None if not found or on error.
    """
    try:
        stmt = select(Candidate).options(
            selectinload(Candidate.profile),
            selectinload(Candidate.tags),
            selectinload(Candidate.experiences),
            selectinload(Candidate.educations),
            selectinload(Candidate.notes)
        ).where(Candidate.id == candidate_id)
        return db.scalars(stmt).first()
    except SQLAlchemyError as e:
        logger.error(f"Database error while retrieving candidate {candidate_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while retrieving candidate {candidate_id}: {e}")
        return None


def list_candidates(
    db: Session,
    search: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Candidate]:
    """List candidates with optional keyword search and status filter.

    Args:
        db (Session): The SQLAlchemy database session.
        search (Optional[str], optional): Search keyword. Defaults to None.
        status (Optional[str], optional): Filter by status. Defaults to None.
        skip (int, optional): Number of records to skip. Defaults to 0.
        limit (int, optional): Maximum number of records to return. Defaults to 100.

    Returns:
        List[Candidate]: A list of matched Candidate objects.
    """
    try:
        stmt = select(Candidate).options(
            selectinload(Candidate.profile),
            selectinload(Candidate.tags)
        )

        if status and status != "All":
            stmt = stmt.where(Candidate.status == status)

        if search:
            search_term = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    Candidate.full_name.ilike(search_term),
                    Candidate.current_title.ilike(search_term),
                    Candidate.current_company.ilike(search_term),
                    Candidate.location.ilike(search_term),
                    Candidate.email.ilike(search_term),
                )
            )

        stmt = stmt.order_by(Candidate.created_at.desc()).offset(skip).limit(limit)
        return list(db.scalars(stmt).all())
    except SQLAlchemyError as e:
        logger.error(f"Database error while listing candidates (search='{search}', status='{status}'): {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error while listing candidates: {e}")
        return []


def update_candidate(db: Session, candidate_id: int, **kwargs: Any) -> Optional[Candidate]:
    """Update fields on a Candidate and Profile.

    Args:
        db (Session): The SQLAlchemy database session.
        candidate_id (int): The ID of the candidate to update.
        **kwargs (Any): Fields and values to update.

    Returns:
        Optional[Candidate]: The updated Candidate object, or None if not found or on error.
    """
    candidate = get_candidate(db, candidate_id)
    if not candidate:
        return None

    profile_fields = ["headline", "summary", "resume_text", "ai_evaluation", "languages", "languages_json"]

    try:
        for key, value in kwargs.items():
            if (key == "skills" or key in profile_fields) and not candidate.profile:
                prof = CandidateProfile(candidate_id=candidate.id)
                db.add(prof)
                db.flush()
                candidate.profile = prof

            if key == "skills":
                if isinstance(value, str):
                    value = [s.strip() for s in value.split(",") if s.strip()]
                try:
                    candidate.profile.skills_json = json.dumps(value if isinstance(value, list) else [])
                except (TypeError, ValueError) as e:
                    logger.error(f"Failed to serialize skills JSON for candidate {candidate_id}: {e}")
            elif key in profile_fields:
                setattr(candidate.profile, key, value)
            elif hasattr(candidate, key):
                setattr(candidate, key, value)

        db.commit()
        db.refresh(candidate)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error while updating candidate {candidate_id}: {e}")
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error while updating candidate {candidate_id}: {e}")
        return None

    # Reindex vector search
    try:
        from app.candidates.search import candidate_search_index
        skills_list = []
        if candidate.profile and candidate.profile.skills_json:
            try:
                skills_list = json.loads(candidate.profile.skills_json)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse skills JSON during reindex for candidate {candidate_id}: {e}")
                
        candidate_search_index.index_candidate(
            candidate_id=candidate.id,
            full_name=candidate.full_name,
            title=candidate.current_title or "",
            skills=skills_list,
            summary=candidate.profile.summary if candidate.profile else "",
            resume_text=candidate.profile.resume_text if candidate.profile else "",
            location=candidate.location or "",
        )
    except ImportError as e:
        logger.error(f"Failed to import search index: {e}")
    except Exception as e:
        logger.warning(f"Vector search re-indexing failed for candidate {candidate_id}: {e}")

    return candidate


def delete_candidate(db: Session, candidate_id: int) -> bool:
    """Delete candidate and remove from vector index.

    Args:
        db (Session): The SQLAlchemy database session.
        candidate_id (int): The ID of the candidate to delete.

    Returns:
        bool: True if deleted successfully, False otherwise.
    """
    candidate = get_candidate(db, candidate_id)
    if not candidate:
        return False

    try:
        from sqlalchemy import update, delete, select
        from app.hunts.models import HuntCandidate, HuntActivity
        from app.communications.models import Communication, CommunicationThread, OutreachEnrollment

        # Clean up pipeline records (HuntCandidate and their activities)
        hunt_cands = db.execute(select(HuntCandidate.id).where(HuntCandidate.candidate_id == candidate_id)).scalars().all()
        if hunt_cands:
            db.execute(delete(HuntActivity).where(HuntActivity.candidate_id.in_(hunt_cands)))
            db.execute(delete(HuntCandidate).where(HuntCandidate.candidate_id == candidate_id))

        # Clean up communications references
        db.execute(update(Communication).where(Communication.candidate_id == candidate_id).values(candidate_id=None))
        db.execute(update(CommunicationThread).where(CommunicationThread.candidate_id == candidate_id).values(candidate_id=None))
        db.execute(delete(OutreachEnrollment).where(OutreachEnrollment.candidate_id == candidate_id))

        db.delete(candidate)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error while deleting candidate {candidate_id}: {e}")
        return False
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error while deleting candidate {candidate_id}: {e}")
        return False

    try:
        from app.candidates.search import candidate_search_index
        candidate_search_index.delete_candidate(candidate_id)
    except ImportError as e:
        logger.error(f"Failed to import search index: {e}")
    except Exception as e:
        logger.warning(f"Failed to delete vector index for candidate {candidate_id}: {e}")

    return True


def add_candidate_tag(db: Session, candidate_id: int, tag_name: str, color: str = "#00d4aa") -> Optional[CandidateTag]:
    """Add a tag to a candidate.

    Args:
        db (Session): The SQLAlchemy database session.
        candidate_id (int): The ID of the candidate.
        tag_name (str): The text name of the tag.
        color (str, optional): The hex color code for the tag. Defaults to "#00d4aa".

    Returns:
        Optional[CandidateTag]: The created CandidateTag object, or None on error.
    """
    try:
        tag = CandidateTag(candidate_id=candidate_id, tag_name=tag_name.strip(), color=color)
        db.add(tag)
        db.commit()
        db.refresh(tag)
        return tag
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error while adding tag '{tag_name}' to candidate {candidate_id}: {e}")
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error while adding tag '{tag_name}' to candidate {candidate_id}: {e}")
        return None


def remove_candidate_tag(db: Session, candidate_id: int, tag_id: int) -> bool:
    """Remove a tag from a candidate.

    Args:
        db (Session): The SQLAlchemy database session.
        candidate_id (int): The ID of the candidate.
        tag_id (int): The ID of the tag to remove.

    Returns:
        bool: True if removed successfully, False otherwise.
    """
    try:
        stmt = select(CandidateTag).where(CandidateTag.id == tag_id, CandidateTag.candidate_id == candidate_id)
        tag = db.scalars(stmt).first()
        if not tag:
            return False
        db.delete(tag)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error while removing tag {tag_id} from candidate {candidate_id}: {e}")
        return False
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error while removing tag {tag_id} from candidate {candidate_id}: {e}")
        return False


def add_candidate_note(db: Session, candidate_id: int, content: str, author: str = "Recruiter") -> Optional[CandidateNote]:
    """Add a note or comment for a candidate.

    Args:
        db (Session): The SQLAlchemy database session.
        candidate_id (int): The ID of the candidate.
        content (str): The text content of the note.
        author (str, optional): The author of the note. Defaults to "Recruiter".

    Returns:
        Optional[CandidateNote]: The created CandidateNote object, or None on error.
    """
    try:
        note = CandidateNote(candidate_id=candidate_id, content=content.strip(), author=author)
        db.add(note)
        db.commit()
        db.refresh(note)
        return note
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error while adding note to candidate {candidate_id}: {e}")
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error while adding note to candidate {candidate_id}: {e}")
        return None


def add_candidate_experience(
    db: Session,
    candidate_id: int,
    company: str,
    title: str,
    location: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    is_current: bool = False,
    description: Optional[str] = None,
) -> Optional[CandidateExperience]:
    """Add an experience entry for a candidate.

    Args:
        db (Session): The SQLAlchemy database session.
        candidate_id (int): The ID of the candidate.
        company (str): The company name.
        title (str): The job title.
        location (Optional[str], optional): The job location. Defaults to None.
        start_date (Optional[str], optional): The start date. Defaults to None.
        end_date (Optional[str], optional): The end date. Defaults to None.
        is_current (bool, optional): Indicates if it's the current job. Defaults to False.
        description (Optional[str], optional): Description of responsibilities. Defaults to None.

    Returns:
        Optional[CandidateExperience]: The created CandidateExperience object, or None on error.
    """
    try:
        exp = CandidateExperience(
            candidate_id=candidate_id,
            company=company,
            title=title,
            location=location,
            start_date=start_date,
            end_date=end_date,
            is_current=is_current,
            description=description,
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)
        return exp
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error while adding experience for candidate {candidate_id}: {e}")
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error while adding experience for candidate {candidate_id}: {e}")
        return None


def add_candidate_education(
    db: Session,
    candidate_id: int,
    institution: str,
    degree: Optional[str] = None,
    field_of_study: Optional[str] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> Optional[CandidateEducation]:
    """Add an education record for a candidate.

    Args:
        db (Session): The SQLAlchemy database session.
        candidate_id (int): The ID of the candidate.
        institution (str): The educational institution.
        degree (Optional[str], optional): The degree obtained. Defaults to None.
        field_of_study (Optional[str], optional): The field of study. Defaults to None.
        start_year (Optional[int], optional): The starting year. Defaults to None.
        end_year (Optional[int], optional): The ending year. Defaults to None.

    Returns:
        Optional[CandidateEducation]: The created CandidateEducation object, or None on error.
    """
    try:
        edu = CandidateEducation(
            candidate_id=candidate_id,
            institution=institution,
            degree=degree,
            field_of_study=field_of_study,
            start_year=start_year,
            end_year=end_year,
        )
        db.add(edu)
        db.commit()
        db.refresh(edu)
        return edu
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error while adding education for candidate {candidate_id}: {e}")
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error while adding education for candidate {candidate_id}: {e}")
        return None


def seed_demo_candidates_if_empty(db: Session) -> List[Candidate]:
    """No-op: Demo candidate seeding disabled as requested."""
    return []

    demo_candidates = [
        {
            "full_name": "Elena Rostova",
            "email": "elena.rostova@neuralstack.ai",
            "phone": "+1 (555) 234-5678",
            "location": "San Francisco, CA",
            "current_title": "Lead AI Engineer",
            "current_company": "NeuralStack AI",
            "experience_years": 6.5,
            "linkedin_url": "https://linkedin.com/in/elena-rostova",
            "github_url": "https://github.com/erostova",
            "status": "Active",
            "headline": "Lead AI Architect specializing in LLM RAG, PyTorch & Distributed Inference",
            "summary": "Accomplished AI Engineer with over 6 years of hands-on experience building production RAG systems, local GGUF quantizations, and agentic workflows. Spearheaded neural search pipelines handling millions of vector queries daily.",
            "resume_text": "Lead AI Engineer at NeuralStack AI (2022 - Present). Built multi-agent RAG pipelines using LangChain, ChromaDB, and FastEmbed. Reduced model latency by 40% using vLLM and llama.cpp. Senior Machine Learning Engineer at DataVibe (2019 - 2022). BS & MS in Computer Science from Stanford University.",
            "skills": ["Python", "PyTorch", "LangChain", "ChromaDB", "FastEmbed", "LlamaIndex", "CUDA", "FastAPI", "Docker"],
            "tags": ["AI Specialist", "Top Candidate", "High Priority"],
            "ai_evaluation": "Top tier 98th percentile candidate for Senior AI Architect roles. Excellent systems architecture and retrieval pipeline experience.",
            "experiences": [
                {
                    "company": "NeuralStack AI",
                    "title": "Lead AI Engineer",
                    "location": "San Francisco, CA",
                    "start_date": "2022-03",
                    "end_date": "Present",
                    "is_current": True,
                    "description": "Architected end-to-end vector search pipelines and multi-agent workflows. Managed a team of 5 ML engineers.",
                },
                {
                    "company": "DataVibe Inc",
                    "title": "Senior Machine Learning Engineer",
                    "location": "Palo Alto, CA",
                    "start_date": "2019-06",
                    "end_date": "2022-02",
                    "is_current": False,
                    "description": "Designed NLP classification models and recommendation algorithms in PyTorch.",
                },
            ],
            "educations": [
                {
                    "institution": "Stanford University",
                    "degree": "Master of Science",
                    "field_of_study": "Computer Science (AI Track)",
                    "start_year": 2017,
                    "end_year": 2019,
                }
            ],
            "notes": [
                "Screened on 2026-08-01: Exceptional verbal clarity and deep vector indexing knowledge. Ready to start in 3 weeks."
            ],
        },
        {
            "full_name": "David Chen",
            "email": "david.chen@datascale.io",
            "phone": "+1 (555) 876-5432",
            "location": "Seattle, WA",
            "current_title": "Senior Backend Architect",
            "current_company": "DataScale Inc",
            "experience_years": 8.0,
            "linkedin_url": "https://linkedin.com/in/dchen-backend",
            "github_url": "https://github.com/dchen-scale",
            "status": "Active",
            "headline": "High-Throughput Backend & Distributed Systems Specialist",
            "summary": "Seasoned backend engineer with 8 years scaling distributed systems in Python, Rust, and Go. Expertise in SQLAlchemy, PostgreSQL, Redis, and high-performance REST/gRPC API microservices.",
            "resume_text": "Senior Backend Architect at DataScale Inc (2021 - Present). Designed streaming data pipelines handling 100k events/sec. Tech Lead at CloudMatrix (2017 - 2021). Built SQLAlchemy 2.0 ORM layers and caching infrastructure.",
            "skills": ["Python", "SQLAlchemy", "FastAPI", "PostgreSQL", "Redis", "Rust", "Docker", "Kubernetes", "gRPC"],
            "tags": ["Backend Master", "System Design"],
            "ai_evaluation": "Strong candidate for Lead Backend or Infrastructure roles. Pragmatic engineering mindset with proven scalability track record.",
            "experiences": [
                {
                    "company": "DataScale Inc",
                    "title": "Senior Backend Architect",
                    "location": "Seattle, WA",
                    "start_date": "2021-01",
                    "end_date": "Present",
                    "is_current": True,
                    "description": "Led backend architecture overhaul migrating monolith to scalable async microservices.",
                }
            ],
            "educations": [
                {
                    "institution": "University of Washington",
                    "degree": "Bachelor of Science",
                    "field_of_study": "Software Engineering",
                    "start_year": 2013,
                    "end_year": 2017,
                }
            ],
            "notes": [
                "Had introductory call on 2026-07-28: Interested in remote roles with AI integration exposure."
            ],
        },
        {
            "full_name": "Sophia Martinez",
            "email": "sophia.m@opencognition.org",
            "phone": "+1 (555) 345-6789",
            "location": "Austin, TX",
            "current_title": "Staff AI Research Engineer",
            "current_company": "OpenCognition Labs",
            "experience_years": 7.0,
            "linkedin_url": "https://linkedin.com/in/sophia-martinez-ai",
            "github_url": "https://github.com/smartinez-labs",
            "status": "Active",
            "headline": "Staff AI Researcher in Autonomous Agents & LLM Fine-Tuning",
            "summary": "Published AI Researcher specializing in multi-agent orchestration, Hugging Face transformers, fine-tuning Llama/Gemma models, and evaluation benchmarks. Passionate about local open-source AI models.",
            "resume_text": "Staff AI Research Engineer at OpenCognition Labs (2021 - Present). Fine-tuned open-weights GGUF and Safetensors models. Published 3 papers on autonomous agent decision-making. ML Engineer at ResearchAI (2018 - 2021).",
            "skills": ["PyTorch", "Hugging Face", "LangGraph", "LlamaIndex", "Python", "Transformers", "GGUF", "CUDA"],
            "tags": ["Published Researcher", "AI Specialist", "Urgent"],
            "ai_evaluation": "Exceptional research & implementation capabilities. Ideal lead for cutting-edge AI product development.",
            "experiences": [
                {
                    "company": "OpenCognition Labs",
                    "title": "Staff AI Research Engineer",
                    "location": "Austin, TX",
                    "start_date": "2021-08",
                    "end_date": "Present",
                    "is_current": True,
                    "description": "Directing research in autonomous reasoning, tool-use agents, and LLM evaluation frameworks.",
                }
            ],
            "educations": [
                {
                    "institution": "UT Austin",
                    "degree": "Ph.D.",
                    "field_of_study": "Artificial Intelligence & Robotics",
                    "start_year": 2014,
                    "end_year": 2018,
                }
            ],
            "notes": [
                "Contacted via LinkedIn, very keen on joining an ambitious recruitment AI platform."
            ],
        },
        {
            "full_name": "Marcus Vance",
            "email": "marcus.v@uicraft.dev",
            "phone": "+1 (555) 901-2345",
            "location": "New York, NY",
            "current_title": "Senior Frontend & UI Engineer",
            "current_company": "UI Craft",
            "experience_years": 5.0,
            "linkedin_url": "https://linkedin.com/in/marcus-vance-ui",
            "github_url": "https://github.com/mvance-ui",
            "status": "Active",
            "headline": "Frontend Craftsman specializing in React, NiceGUI & Modern Web UX",
            "summary": "UI/UX engineer with 5 years creating responsive, accessible, and high-performance web applications. Skilled in React, TypeScript, Tailwind CSS, and Python NiceGUI dashboard interfaces.",
            "resume_text": "Senior Frontend Engineer at UI Craft (2021 - Present). Built design systems and interactive web apps. Frontend Developer at Pixel Perfect (2019 - 2021). Focused on dark-theme UI components and real-time state sync.",
            "skills": ["React", "TypeScript", "NiceGUI", "Tailwind CSS", "HTML5/CSS3", "JavaScript", "Python", "Figma"],
            "tags": ["Frontend Lead", "UI Design"],
            "ai_evaluation": "Great fit for Fullstack / Frontend leadership. Combines deep UX design sensitivity with solid Python component skills.",
            "experiences": [
                {
                    "company": "UI Craft",
                    "title": "Senior Frontend Engineer",
                    "location": "New York, NY",
                    "start_date": "2021-04",
                    "end_date": "Present",
                    "is_current": True,
                    "description": "Lead developer for enterprise design system and dashboard user interfaces.",
                }
            ],
            "educations": [
                {
                    "institution": "NYU Tandon School of Engineering",
                    "degree": "Bachelor of Science",
                    "field_of_study": "Computer Science",
                    "start_year": 2015,
                    "end_year": 2019,
                }
            ],
            "notes": [
                "Portfolio demonstrated stunning dashboard components and smooth state management."
            ],
        },
    ]

    created_list = []
    for cand_data in demo_candidates:
        try:
            cand = create_candidate(
                db,
                full_name=cand_data["full_name"],
                email=cand_data["email"],
                phone=cand_data["phone"],
                location=cand_data["location"],
                current_title=cand_data["current_title"],
                current_company=cand_data["current_company"],
                experience_years=cand_data["experience_years"],
                linkedin_url=cand_data["linkedin_url"],
                github_url=cand_data.get("github_url"),
                status=cand_data["status"],
                headline=cand_data["headline"],
                summary=cand_data["summary"],
                resume_text=cand_data["resume_text"],
                skills=cand_data["skills"],
                tags=cand_data["tags"],
                ai_evaluation=cand_data["ai_evaluation"],
            )
            
            if not cand:
                continue

            for exp in cand_data.get("experiences", []):
                add_candidate_experience(
                    db,
                    candidate_id=cand.id,
                    company=exp["company"],
                    title=exp["title"],
                    location=exp.get("location"),
                    start_date=exp.get("start_date"),
                    end_date=exp.get("end_date"),
                    is_current=exp.get("is_current", False),
                    description=exp.get("description"),
                )

            for edu in cand_data.get("educations", []):
                add_candidate_education(
                    db,
                    candidate_id=cand.id,
                    institution=edu["institution"],
                    degree=edu.get("degree"),
                    field_of_study=edu.get("field_of_study"),
                    start_year=edu.get("start_year"),
                    end_year=edu.get("end_year"),
                )

            for note_str in cand_data.get("notes", []):
                add_candidate_note(db, candidate_id=cand.id, content=note_str)

            created_list.append(cand)
        except Exception as e:
            logger.error(f"Failed to seed candidate {cand_data.get('full_name')}: {e}")

    return created_list
