"""Streaming response engine for piping AI Copilot tokens to NiceGUI."""

import asyncio
from typing import AsyncGenerator
from langchain_core.messages import SystemMessage, HumanMessage

from app.ai.engine import ai_engine
from app.copilot.prompts import COPILOT_SYSTEM_PROMPT
from app.copilot.conversation import conversation_manager
from app.copilot.orchestrator import copilot_graph

import random

TOOL_HUMAN_MAPPINGS = {
    "batch_search_the_web": "🔍 Searching LinkedIn, GitHub & web portfolios in parallel...",
    "search_the_web": "🔍 Searching the web for candidates...",
    "add_candidate_to_database": "💾 Saving candidate profiles to your Talent Hunt pipeline...",
    "verify_candidate_match": "🧠 Agentic Critic: Verifying candidate match against job requirements...",
    "search_candidates": "📂 Querying internal talent database...",
    "message_candidate": "✉️ Drafting personalized candidate outreach message...",
    "start_talent_hunt": "🚀 Launching Virtual Recruiting Agency background thread...",
}

PRO_TIPS = [
    "💡 Pro Tip: Select a specific Hunt from the top dropdown to automatically isolate candidate memories for that role!",
    "💡 Pro Tip: Click the mic icon in the chat bar to dictate candidate search queries hands-free!",
    "💡 Pro Tip: The Agentic Critic double-checks every candidate against your JD criteria before saving.",
    "💡 Pro Tip: Click 'Pipeline Kanban' on any campaign card to visually drag & drop candidates through stages.",
    "💡 Pro Tip: You can edit campaign titles, target roles, and skills directly using the pencil icon on Hunt cards.",
    "💡 Pro Tip: Copilot remembers previous inputs! Use Up/Down arrow keys in the chat box to cycle your message history."
]

async def stream_copilot_response(
    user_input: str,
    session_id: str = "default",
    provider: str | None = None,
    model: str | None = None
) -> AsyncGenerator[str, None]:
    """Async generator to stream Copilot responses chunk by chunk to the UI."""
    from langgraph.prebuilt import create_react_agent
    from app.copilot.tools import get_copilot_tools
    
    conversation_manager.add_user_message(user_input, session_id)
    accumulated = ""
    
    try:
        history = conversation_manager.get_langchain_messages(session_id)
        llm = ai_engine.get_llm(provider=provider, model=model)
        tools = get_copilot_tools()
        
        # Retrieve RAG Memory
        rag_context = ""
        try:
            from app.copilot.memory import memory_index
            rag_context = memory_index.search_history(session_id, user_input)
        except Exception as e:
            import logging
            logging.getLogger("talenthunt.copilot.streaming").warning(f"Failed to fetch RAG memory: {e}")

        # Task 3: Semantic Drift Prevention & Hunt Context
        active_hunt_context = ""
        if session_id.startswith("hunt_"):
            try:
                hunt_id_str = session_id.split("_")[1]
                if hunt_id_str.isdigit():
                    hunt_id = int(hunt_id_str)
                    from app.infrastructure.db import SessionFactory
                    from app.hunts.service import get_hunt
                    with SessionFactory() as db:
                        hunt = get_hunt(db, hunt_id)
                        if hunt:
                            skills = ""
                            if hunt.search_config and hunt.search_config.required_skills:
                                skills = hunt.search_config.required_skills
                            active_hunt_context = f"CURRENT ACTIVE HUNT CONTEXT (Database ID: {hunt.id}):\n- Title: {hunt.title}\n- Target Role: {hunt.target_role or 'N/A'}\n- Location: {hunt.location or 'N/A'}\n- Required Skills: {skills}\n\nCRITICAL INSTRUCTION: The user is currently viewing this specific Talent Hunt. When they ask to 'add candidates' or 'find candidates', they are referring to THIS role. DO NOT ask them for the role, skills, or location again. Just execute the search or addition using this context. Automatically pass hunt_id='{hunt.id}' to any tools that accept it."
            except Exception as e:
                import logging
                logging.getLogger("talenthunt.copilot.streaming").warning(f"Failed to fetch active hunt DB context: {e}")

        from app.copilot.prompts import get_copilot_prompt
        final_prompt = get_copilot_prompt(active_hunt_context if active_hunt_context else None)
        if rag_context:
            final_prompt += f"\n\n--- PAST CONVERSATION MEMORY ---\n{rag_context}\n--------------------------------\n(Use the above memory if relevant to the current user request)."

        agent = create_react_agent(llm, tools, prompt=final_prompt)
        config = {"recursion_limit": 100}

        async for event in agent.astream_events({"messages": history}, config=config, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if hasattr(chunk, "content") and chunk.content and isinstance(chunk.content, str):
                    accumulated += chunk.content
                    yield accumulated
            elif kind == "on_tool_start":
                tool_name = event["name"]
                friendly_action = TOOL_HUMAN_MAPPINGS.get(tool_name, f"⚡ Executing action ({tool_name})...")
                tip = random.choice(PRO_TIPS)
                
                if not accumulated.endswith("\n\n"):
                    if accumulated and not accumulated.endswith("\n"):
                        accumulated += "\n\n"
                    elif accumulated.endswith("\n") and not accumulated.endswith("\n\n"):
                        accumulated += "\n"
                
                accumulated += f"> {friendly_action}\n> _{tip}_\n\n"
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
