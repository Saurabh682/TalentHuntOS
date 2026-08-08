"""CrewAI Worker Agent Definitions for TalentHunt OS."""

import logging
from crewai import Agent
from app.ai.engine import ai_engine
from app.agents.tools import web_scraper_tool, search_github_linkedin, parse_resume

logger = logging.getLogger("talenthunt.agents.workers")

def get_agent_llm():
    """Helper to get configured LLM for CrewAI agents."""
    llm = None
    try:
        llm = ai_engine.get_llm()
    except Exception as e:
        logger.warning(f"Could not load custom AIEngine LLM for agent: {e}")
    if llm is None:
        raise RuntimeError("No LLM configured for CrewAI agent.")
    return llm

def create_sourcing_agent() -> Agent:
    """Create the Sourcing (Searcher) agent responsible for discovering candidate profiles."""
    return Agent(
        role="Talent Sourcing Specialist",
        goal="Discover high-quality software engineering candidates across GitHub, LinkedIn, and tech platforms.",
        backstory=(
            "You are an elite technical recruiter with a sharp eye for talent. You excel at scanning "
            "developer profiles on GitHub and LinkedIn, identifying strong technical skills, active repositories, "
            "and candidate potential matching job descriptions."
        ),
        tools=[search_github_linkedin, web_scraper_tool],
        verbose=True,
        memory=False,
        llm=get_agent_llm(),
    )

def create_screening_agent() -> Agent:
    """Create the Screening (Evaluator) agent responsible for candidate evaluation and scoring."""
    return Agent(
        role="Candidate Screening Specialist",
        goal="Evaluate sourced candidate profiles, analyze resume data, and score match suitability against position requirements.",
        backstory=(
            "You are a seasoned engineering manager and technical screener. You objectively assess "
            "candidate skill sets, work experience, open-source contributions, and technical alignment with job requirements."
        ),
        tools=[parse_resume, web_scraper_tool],
        verbose=True,
        memory=False,
        llm=get_agent_llm(),
    )

def create_outreach_agent() -> Agent:
    """Create the Outreach (Writer) agent responsible for generating personalized candidate messages."""
    return Agent(
        role="Talent Outreach Specialist",
        goal="Draft highly personalized, engaging outreach emails tailored to top-ranked candidates.",
        backstory=(
            "You are a recruitment communications expert. You excel at crafting irresistible, respectful, "
            "and hyper-personalized email messages that highlight specific candidate achievements and excite them about new roles."
        ),
        tools=[web_scraper_tool],
        verbose=True,
        memory=False,
        llm=get_agent_llm(),
    )
