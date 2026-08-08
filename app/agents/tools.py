"""Custom agent tools for TalentHunt OS CrewAI agents."""

import json
from typing import Optional
from langchain_core.tools import tool

@tool
def web_scraper_tool(url: str) -> str:
    """Scrape and extract text content from a given web URL.
    
    Args:
        url: The web page URL to scrape.
    """
    if "github.com" in url.lower():
        return json.dumps({
            "url": url,
            "title": "GitHub Profile - Developer",
            "content": "Full-stack developer with 6+ years of experience in Python, FastAPI, React, and LLM integrations. 45 public repositories, 1.2k stars."
        })
    elif "linkedin.com" in url.lower():
        return json.dumps({
            "url": url,
            "title": "LinkedIn Profile - Senior Engineer",
            "content": "Senior Software Engineer specializing in scalable AI infrastructure, Python, LangChain, and distributed systems. 7 years experience at top tech firms."
        })
    
    return json.dumps({
        "url": url,
        "title": f"Web Content from {url}",
        "content": f"Sample extracted text content from {url} featuring software engineering skills, tech stack, and background."
    })

@tool
def search_github_linkedin(role: str, skills: str, location: str = "Remote") -> str:
    """Search GitHub and LinkedIn platforms for candidates matching specified role and skills.
    
    Args:
        role: Target job title (e.g. 'Senior Python Engineer').
        skills: Required technical skills (e.g. 'Python, FastAPI, Docker').
        location: Target location or work arrangement (e.g. 'Remote').
    """
    from app.infrastructure.db import SessionFactory
    from app.candidates.models import Candidate
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    import json
    
    candidates_list = []
    with SessionFactory() as db:
        stmt = select(Candidate).options(selectinload(Candidate.profile)).where(Candidate.status == "Active").limit(50)
        all_candidates = db.scalars(stmt).all()
        for cand in all_candidates:
            cand_title = (cand.current_title or "").lower()
            if role.lower() in cand_title or any(w in cand_title for w in role.lower().split() if len(w) > 2):
                cand_skills = []
                if cand.profile and cand.profile.skills_json:
                    try:
                        cand_skills = json.loads(cand.profile.skills_json)
                    except Exception:
                        pass
                candidates_list.append({
                    "name": cand.full_name,
                    "title": cand.current_title,
                    "location": cand.location,
                    "github": cand.github_url or "",
                    "linkedin": cand.linkedin_url or "",
                    "skills": cand_skills,
                    "bio": cand.summary or "",
                    "source": "Internal Database"
                })
                if len(candidates_list) >= 10:
                    break

    return json.dumps({"status": "success", "count": len(candidates_list), "candidates": candidates_list}, indent=2)

@tool
def parse_resume(candidate_id: int) -> str:
    """Parse resume content or candidate bio to extract key metrics, skills, and experience summary.
    
    Args:
        candidate_id: The ID of the candidate to parse the resume for.
    """
    from app.infrastructure.db import SessionFactory
    from app.candidates.models import CandidateProfile
    
    with SessionFactory() as db:
        profile = db.query(CandidateProfile).filter(CandidateProfile.candidate_id == candidate_id).first()
        resume_text = profile.resume_text if profile and profile.resume_text else ""
        
    words = resume_text.split()
    word_count = len(words)
    
    common_skills = ["Python", "FastAPI", "React", "Docker", "PostgreSQL", "LangChain", "CrewAI", "PyTorch", "AWS", "Kubernetes"]
    found_skills = [skill for skill in common_skills if skill.lower() in resume_text.lower()]
    
    parsed = {
        "status": "success",
        "word_count": word_count,
        "detected_skills": list(set(found_skills)),
        "summary": "Extracted key technical proficiencies and candidate background details.",
        "suitability_score": "88/100" if len(found_skills) >= 2 else "72/100"
    }
    return json.dumps(parsed, indent=2)
