"""CrewAI Workflow Orchestration for TalentHunt OS."""

import logging
import json
import asyncio
from typing import Dict, Any, Optional
from crewai import Task, Crew, Process

from app.agents.workers import create_sourcing_agent, create_screening_agent, create_outreach_agent

logger = logging.getLogger("talenthunt.agents.workflows")

def create_talent_hunt_crew(
    job_title: str,
    skills: str,
    location: str = "Remote"
) -> Crew:
    """Construct and configure the Talent Hunt CrewAI crew and tasks."""
    sourcing_agent = create_sourcing_agent()
    screening_agent = create_screening_agent()
    outreach_agent = create_outreach_agent()

    sourcing_task = Task(
        description=(
            f"Search for potential talent for the target job title '{job_title}' requiring skills: {skills} in '{location}'. "
            f"Use the search tools to discover candidate profiles from GitHub and LinkedIn. "
            f"Gather at least 3 relevant candidate profiles with their tech stacks, GitHub/LinkedIn links, and bios."
        ),
        expected_output=(
            "A structured list of at least 3 candidate profiles including Name, Title, Location, Skills, Profile Links, and Bio."
        ),
        agent=sourcing_agent,
    )

    screening_task = Task(
        description=(
            f"Evaluate and rank the candidates sourced in the previous task for the '{job_title}' role. "
            f"Use the resume parser tool to evaluate their skills ({skills}) and experience. "
            f"Assign match scores (0-100%) and highlight strengths and weaknesses for each candidate."
        ),
        expected_output=(
            "A detailed evaluation report ranking each candidate with match scores, pros, cons, and selection status."
        ),
        agent=screening_agent,
    )

    outreach_task = Task(
        description=(
            f"Draft tailored, compelling outreach email messages for the top-ranked candidates evaluated for '{job_title}'. "
            f"Each message must reference specific skills ({skills}) and candidate background highlights."
        ),
        expected_output=(
            "Personalized email outreach templates for the top candidates, complete with Subject Line and Body."
        ),
        agent=outreach_agent,
    )

    crew = Crew(
        agents=[sourcing_agent, screening_agent, outreach_agent],
        tasks=[sourcing_task, screening_task, outreach_task],
        process=Process.sequential,
        verbose=True,
    )

    return crew

def run_talent_hunt_workflow(job_title: str, skills: str, location: str = "Remote") -> str:
    """Synchronous execution of the Talent Hunt CrewAI workflow."""
    logger.info(f"Starting Talent Hunt Crew for {job_title} ({skills})")
    try:
        crew = create_talent_hunt_crew(job_title=job_title, skills=skills, location=location)
        result = crew.kickoff()
        return str(result)
    except Exception as e:
        logger.error(f"Error during Talent Hunt Crew execution: {e}", exc_info=True)
        return f"Talent hunt workflow encountered an error: {str(e)}"

async def run_talent_hunt_workflow_async(job_title: str, skills: str, location: str = "Remote") -> str:
    """Asynchronous execution wrapper for running Talent Hunt workflow without blocking."""
    return await asyncio.to_thread(run_talent_hunt_workflow, job_title, skills, location)
