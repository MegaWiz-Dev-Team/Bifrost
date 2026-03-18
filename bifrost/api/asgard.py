"""Asgard API — REST endpoints for the ADK orchestrator."""

import logging
import uuid
from fastapi import APIRouter
from pydantic import BaseModel

try:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
except ImportError:
    Runner = None
    InMemorySessionService = None

from bifrost.core.service_agents import asgard_root_agent, SERVICE_AGENTS

logger = logging.getLogger("bifrost.api.asgard")

router = APIRouter(prefix="/v1/asgard", tags=["asgard"])

if Runner and asgard_root_agent:
    session_service = InMemorySessionService()
    runner = Runner(agent=asgard_root_agent, session_service=session_service)
else:
    runner = None

class AskRequest(BaseModel):
    """Request body for Asgard ask."""
    question: str
    session_id: str | None = None

@router.post("/ask")
async def asgard_ask(req: AskRequest):
    """Route a question to the ADK orchestrator."""
    if not runner:
        return {"error": "ADK framework not available or google-adk not installed."}

    session_id = req.session_id or str(uuid.uuid4())
    user_id = "default_bifrost_user"

    try:
        response_text = ""
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=req.question):
            if hasattr(event, "is_final_response") and callable(event.is_final_response) and event.is_final_response():
                try:
                    response_text = event.content.parts[0].text
                except (AttributeError, IndexError):
                    response_text = str(event.content) if hasattr(event, "content") else str(event)
        
        output_text = response_text
    except Exception as e:
        logger.error(f"ADK Run Error: {e}")
        output_text = f"Error evaluating with ADK: {e}"

    return {
        "agent_id": "asgard-agent",
        "agent_name": asgard_root_agent.name,
        "response": output_text,
        "routing_method": "google-adk",
        "session_id": session_id
    }

@router.post("/standup")
async def asgard_standup():
    """Run team standup."""
    if not asgard_root_agent:
        return {"error": "ADK framework not available."}
        
    return {
        "agents": [{"agent_id": a.agent_id, "name": a.persona_name} for a in SERVICE_AGENTS],
        "total_count": len(SERVICE_AGENTS),
        "orchestrator": asgard_root_agent.name
    }

