"""LangGraph-based state machine router for user intent classification and workflow dispatch."""

import logging
from typing import Annotated, Dict, Any, List, Sequence, TypedDict

from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from app.copilot.tools import start_talent_hunt, search_candidates, message_candidate

logger = logging.getLogger("talenthunt.copilot.orchestrator")



class CopilotState(TypedDict):
    """State definition for LangGraph orchestrator."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    intent: str
    extracted_args: Dict[str, Any]
    response: str

def classify_intent_node(state: CopilotState) -> Dict[str, Any]:
    """Node: Classify user intent using LLM or heuristic mapping."""
    messages = state.get("messages", [])
    if not messages:
        return {"intent": "general_chat", "extracted_args": {}}

    last_user_msg = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_msg = str(msg.content)
            break

    lower_msg = last_user_msg.lower()
    
    if any(k in lower_msg for k in ["start hunt", "create hunt", "new hunt", "find candidate for"]):
        return {"intent": "start_hunt", "extracted_args": {"query": last_user_msg}}
    elif any(k in lower_msg for k in ["search candidate", "find candidate", "search pool", "lookup"]):
        return {"intent": "search_candidates", "extracted_args": {"query": last_user_msg}}
    elif any(k in lower_msg for k in ["message", "email candidate", "outreach", "contact"]):
        return {"intent": "message_candidate", "extracted_args": {"query": last_user_msg}}
    
    return {"intent": "general_chat", "extracted_args": {}}

def execute_action_node(state: CopilotState) -> Dict[str, Any]:
    """Node: Execute tool action based on intent."""
    intent = state.get("intent", "general_chat")
    args = state.get("extracted_args", {})
    query = args.get("query", "")

    if intent == "start_hunt":
        tool_out = start_talent_hunt.invoke({"job_title": query or "Software Engineer", "skills": "Python, AI"})
        return {"response": f"I've initiated a new talent hunt based on your request:\n```json\n{tool_out}\n```"}
    elif intent == "search_candidates":
        tool_out = search_candidates.invoke({"query": query or "Python Developer", "limit": 3})
        return {"response": f"Here are the matching candidates from our database:\n```json\n{tool_out}\n```"}
    elif intent == "message_candidate":
        tool_out = message_candidate.invoke({"candidate_id": "cand_101", "message": query})
        return {"response": f"Outreach action executed:\n```json\n{tool_out}\n```"}
    
    return {"response": ""}

def route_intent(state: CopilotState) -> str:
    """Conditional routing edge callback."""
    intent = state.get("intent", "general_chat")
    if intent in ["start_hunt", "search_candidates", "message_candidate"]:
        return "action"
    return "general"

def create_copilot_graph():
    """Construct and compile the LangGraph Copilot Orchestrator state graph."""
    workflow = StateGraph(CopilotState)
    
    workflow.add_node("classifier", classify_intent_node)
    workflow.add_node("action_executor", execute_action_node)

    workflow.set_entry_point("classifier")
    
    workflow.add_conditional_edges(
        "classifier",
        route_intent,
        {
            "action": "action_executor",
            "general": END
        }
    )
    workflow.add_edge("action_executor", END)
    
    return workflow.compile()

copilot_graph = create_copilot_graph()
