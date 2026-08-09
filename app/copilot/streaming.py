"""Streaming response engine for piping AI Copilot tokens to NiceGUI."""

from __future__ import annotations

import asyncio
import logging
import queue
import random
import threading
from typing import AsyncGenerator, Optional

from app.ai.engine import ai_engine
from app.copilot.conversation import conversation_manager

logger = logging.getLogger("talenthunt.copilot.streaming")

# Hard caps so a runaway model cannot flood the NiceGUI WebSocket ("Connection lost").
MAX_STREAM_CHARS = 6000
REPEAT_WINDOW = 180
REPEAT_HITS_BEFORE_STOP = 4

TOOL_HUMAN_MAPPINGS = {
    "batch_search_the_web": "🔍 Searching LinkedIn, GitHub & web portfolios in parallel...",
    "search_the_web": "🔍 Searching the web for candidates...",
    "source_talent_for_hunt": "🎯 Sourcing LinkedIn/Naukri people into this hunt...",
    "add_candidate_to_database": "💾 Saving candidate profiles to your Talent Hunt pipeline...",
    "verify_candidate_match": "🧠 Agentic Critic: Verifying candidate match against job requirements...",
    "search_candidates": "📂 Querying internal talent database...",
    "message_candidate": "✉️ Drafting personalized candidate outreach message...",
    "start_talent_hunt": "🚀 Launching Virtual Recruiting Agency background thread...",
    "remove_candidates_from_hunt": "🗑️ Removing candidates from the hunt pipeline...",
    "consult_sourcing_playbook": "📘 Checking the sourcing playbook...",
}

PRO_TIPS = [
    "💡 Pro Tip: Select a specific Hunt from the top dropdown to automatically isolate candidate memories for that role!",
    "💡 Pro Tip: Click the mic icon in the chat bar to dictate candidate search queries hands-free!",
    "💡 Pro Tip: The Agentic Critic double-checks every candidate against your JD criteria before saving.",
    "💡 Pro Tip: Click 'Pipeline Kanban' on any campaign card to visually drag & drop candidates through stages.",
    "💡 Pro Tip: You can edit campaign titles, target roles, and skills directly using the pencil icon on Hunt cards.",
    "💡 Pro Tip: Copilot remembers previous inputs! Use Up/Down arrow keys in the chat box to cycle your message history.",
]


def _looks_like_repetition_loop(text: str) -> bool:
    """Detect stuck token loops that balloon response size and drop the UI socket."""
    if len(text) < REPEAT_WINDOW * 2:
        return False
    tail = text[-REPEAT_WINDOW:]
    hay = text[-min(len(text), 2500) :]
    return hay.count(tail) >= REPEAT_HITS_BEFORE_STOP


def _build_active_hunt_context(session_id: str) -> str:
    if not session_id.startswith("hunt_"):
        return ""
    try:
        hunt_id_str = session_id.split("_")[1]
        if not hunt_id_str.isdigit():
            return ""
        hunt_id = int(hunt_id_str)
        from app.infrastructure.db import SessionFactory
        from app.hunts.service import get_hunt

        with SessionFactory() as db:
            hunt = get_hunt(db, hunt_id)
            if not hunt:
                return ""
            skills = ""
            industry = ""
            exp = "any"
            if hunt.search_config:
                sc = hunt.search_config
                if sc.required_skills:
                    skills = sc.required_skills
                if sc.industry:
                    industry = sc.industry
                emin, emax = sc.experience_years_min, sc.experience_years_max
                if emin is not None and emax is not None:
                    exp = f"{emin}-{emax} years"
                elif emin is not None:
                    exp = f"{emin}+ years"
                elif emax is not None:
                    exp = f"up to {emax} years"
            return (
                f"CURRENT ACTIVE HUNT CONTEXT (Database ID: {hunt.id}):\n"
                f"- Title: {hunt.title}\n"
                f"- Target Role: {hunt.target_role or 'N/A'}\n"
                f"- Location: {hunt.location or 'N/A'}\n"
                f"- Experience band (HARD): {exp}\n"
                f"- Industry: {industry or 'N/A'}\n"
                f"- Salary: {hunt.salary_range or 'N/A'}\n"
                f"- Required Skills: {skills or 'N/A'}\n\n"
                "CRITICAL CONSTRAINTS (do not drift across this session):\n"
                f"1) Always pass hunt_id='{hunt.id}' when adding/sourcing/removing candidates.\n"
                f"2) Never invent years of experience or skills not evidenced on a profile.\n"
                f"3) Stay inside experience band '{exp}' and role '{hunt.target_role or hunt.title}'.\n"
                "4) When they ask to find/look for/source N talents or search LinkedIn, call "
                f"`source_talent_for_hunt` with hunt_id='{hunt.id}' and target_count=N.\n"
                f"5) For remove/clear: remove_candidates_from_hunt(hunt_id='{hunt.id}', confirm=true) then re-source.\n"
                "6) Never present candidates from unrelated professions (e.g. animators on a sales hunt).\n"
                "7) Prefer read_profile_page before trusting a LinkedIn URL."
            )
    except Exception as e:
        logger.warning("Failed to fetch active hunt DB context: %s", e)
        return ""


def _run_agent_worker(
    *,
    history,
    final_prompt: str,
    provider: Optional[str],
    model: Optional[str],
    out_q: queue.Queue,
    session_id: str = "default",
) -> None:
    """Own event loop + thread so sync tools never block NiceGUI's WebSocket."""
    from app.copilot.session_ctx import (
        resolve_hunt_id_from_session,
        set_active_hunt_id,
        set_active_session_id,
    )

    set_active_session_id(session_id)
    set_active_hunt_id(resolve_hunt_id_from_session(session_id))

    async def _consume() -> None:
        accumulated = ""
        try:
            from langgraph.prebuilt import create_react_agent
            from app.copilot.tools import get_copilot_tools

            llm = ai_engine.get_llm(provider=provider, model=model)
            tools = get_copilot_tools()
            agent = create_react_agent(llm, tools, prompt=final_prompt)
            config = {"recursion_limit": 40}

            async for event in agent.astream_events(
                {"messages": history}, config=config, version="v2"
            ):
                kind = event.get("event")
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    content = getattr(chunk, "content", None)
                    if content and isinstance(content, str):
                        accumulated += content
                        if len(accumulated) > MAX_STREAM_CHARS or _looks_like_repetition_loop(
                            accumulated
                        ):
                            accumulated = accumulated[:MAX_STREAM_CHARS].rstrip()
                            accumulated += "\n\n_(Response truncated to keep the UI responsive.)_"
                            out_q.put(accumulated)
                            break
                        out_q.put(accumulated)
                elif kind == "on_tool_start":
                    tool_name = event.get("name") or "tool"
                    friendly = TOOL_HUMAN_MAPPINGS.get(
                        tool_name, f"⚡ Executing action ({tool_name})..."
                    )
                    tip = random.choice(PRO_TIPS)
                    if not accumulated.endswith("\n\n"):
                        if accumulated and not accumulated.endswith("\n"):
                            accumulated += "\n\n"
                        elif accumulated.endswith("\n"):
                            accumulated += "\n"
                    accumulated += f"> {friendly}\n> _{tip}_\n\n"
                    if len(accumulated) > MAX_STREAM_CHARS:
                        accumulated = accumulated[:MAX_STREAM_CHARS].rstrip()
                        accumulated += "\n\n_(Response truncated to keep the UI responsive.)_"
                        out_q.put(accumulated)
                        break
                    out_q.put(accumulated)
        except Exception as exc:
            logger.exception("Copilot agent worker failed")
            msg = (
                f"I encountered an issue with the AI engine ({exc}). "
                "Please verify your API key in Settings or check your local server configuration."
            )
            accumulated = (accumulated + "\n\n" if accumulated else "") + msg
            out_q.put(accumulated)
        finally:
            out_q.put(None)

    try:
        asyncio.run(_consume())
    except Exception as exc:
        logger.exception("Copilot worker loop crashed: %s", exc)
        out_q.put(f"Copilot worker crashed: {exc}")
        out_q.put(None)
    finally:
        set_active_session_id(None)
        set_active_hunt_id(None)


async def stream_copilot_response(
    user_input: str,
    session_id: str = "default",
    provider: str | None = None,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    """Async generator to stream Copilot responses without blocking NiceGUI."""
    conversation_manager.add_user_message(user_input, session_id)
    accumulated = ""

    try:
        history = conversation_manager.get_langchain_messages(session_id)

        rag_context = ""
        try:
            from app.copilot.memory import memory_index

            rag_context = memory_index.search_history(session_id, user_input)
        except Exception as e:
            logger.warning("Failed to fetch RAG memory: %s", e)

        active_hunt_context = _build_active_hunt_context(session_id)
        from app.copilot.prompts import get_copilot_prompt

        final_prompt = get_copilot_prompt(active_hunt_context if active_hunt_context else None)
        if rag_context:
            final_prompt += (
                f"\n\n--- PAST CONVERSATION MEMORY ---\n{rag_context}\n"
                "--------------------------------\n"
                "(Use the above memory if relevant to the current user request)."
            )

        out_q: queue.Queue = queue.Queue()
        worker = threading.Thread(
            target=_run_agent_worker,
            kwargs={
                "history": history,
                "final_prompt": final_prompt,
                "provider": provider,
                "model": model,
                "out_q": out_q,
                "session_id": session_id,
            },
            daemon=True,
            name="copilot-agent",
        )
        worker.start()

        loop = asyncio.get_running_loop()
        while True:
            item = await loop.run_in_executor(None, out_q.get)
            if item is None:
                break
            accumulated = item
            yield accumulated

    except Exception as exc:
        fallback_msg = (
            f"I encountered an issue with the AI engine ({exc}). "
            "Please verify your API key in Settings or check your local server configuration."
        )
        accumulated += ("\n\n" if accumulated else "") + fallback_msg
        yield accumulated

    if accumulated:
        conversation_manager.add_assistant_message(accumulated, session_id)
