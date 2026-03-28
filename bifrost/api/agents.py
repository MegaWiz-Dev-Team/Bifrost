"""Agent execution endpoints."""

import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator
from sse_starlette.sse import EventSourceResponse

from bifrost.clients.heimdall import HeimdallClient
from bifrost.config import settings
from bifrost.core.executor import AgentExecutor
from bifrost.core.agents import agent_store
from bifrost.memory.session import SessionManager
from bifrost.tools.registry import registry

router = APIRouter(prefix="/v1/agents", tags=["agents"])

# Shared instances
_heimdall = HeimdallClient()
_session_mgr = SessionManager()


class RunRequest(BaseModel):
    """Request body for agent execution.

    Accepts two formats:
    1. Classic: {"input": "hello"}
    2. OpenAI-compatible: {"messages": [{"role": "user", "content": "hello"}]}
    """
    input: str | None = None
    message: str | None = None
    messages: list[dict] | None = None
    session_id: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    temperature: float = 0.7

    @model_validator(mode="after")
    def extract_input_from_messages(self):
        """Extract input from messages array or message field if input not provided."""
        if self.input is None:
            if self.message:
                self.input = self.message
            elif self.messages:
                # Find last user message
                for msg in reversed(self.messages):
                    if msg.get("role") == "user" and msg.get("content"):
                        self.input = msg["content"]
                        break
        if not self.input:
            raise ValueError("Either 'input', 'message', or 'messages' with a user message is required")
        return self


@router.get("")
async def list_agents():
    """List all configured agents."""
    agents_list = agent_store.list_agents()
    return {
        "agents": [a.to_dict() for a in agents_list],
        "total": len(agents_list),
    }


@router.post("/{agent_id}/run")
async def run_agent(agent_id: str, request: RunRequest):
    """Execute an agent (non-streaming). Returns full result."""
    # Look up agent config
    agent_config = agent_store.get(agent_id)
    system_prompt = request.system_prompt or (
        agent_config.system_prompt if agent_config else
        "You are a helpful AI assistant. Respond in the same language as the user."
    )
    model = request.model or (agent_config.model if agent_config else None)
    temperature = request.temperature or (agent_config.temperature if agent_config else 0.7)

    # Get or create session
    session_id = request.session_id
    history = []
    if session_id:
        session = await _session_mgr.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
        history = await _session_mgr.get_history(session_id)
    else:
        session_id = await _session_mgr.create_session(agent_id)

    # Save user message
    await _session_mgr.add_message(session_id, "user", request.input)

    # Execute ReAct loop
    executor = AgentExecutor(
        heimdall=_heimdall,
        tool_registry=registry,
        max_iterations=settings.max_iterations,
        max_execution_time=settings.max_execution_time,
    )

    result = await executor.execute(
        system_prompt=system_prompt,
        user_input=request.input,
        model=model,
        temperature=temperature,
        history=history,
    )

    # Save assistant response
    await _session_mgr.add_message(session_id, "assistant", result.output)

    return {
        "output": result.output,
        "session_id": session_id,
        "agent_id": agent_id,
        "trace": [
            {
                "step": s.step,
                "type": s.type,
                "content": s.content,
                "tool_name": s.tool_name,
                "tool_args": s.tool_args,
                "duration_ms": round(s.duration_ms, 2),
            }
            for s in result.trace
        ],
        "total_iterations": result.total_iterations,
        "total_duration_ms": round(result.total_duration_ms, 2),
    }


@router.post("/{agent_id}/stream")
async def stream_agent(agent_id: str, request: RunRequest):
    """Execute an agent with SSE streaming."""
    agent_config = agent_store.get(agent_id)
    system_prompt = request.system_prompt or (
        agent_config.system_prompt if agent_config else
        "You are a helpful AI assistant. Respond in the same language as the user."
    )
    model = request.model or (agent_config.model if agent_config else None)
    temperature = request.temperature or (agent_config.temperature if agent_config else 0.7)

    session_id = request.session_id
    history = []
    if session_id:
        session = await _session_mgr.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
        history = await _session_mgr.get_history(session_id)
    else:
        session_id = await _session_mgr.create_session(agent_id)

    await _session_mgr.add_message(session_id, "user", request.input)

    executor = AgentExecutor(
        heimdall=_heimdall,
        tool_registry=registry,
        max_iterations=settings.max_iterations,
        max_execution_time=settings.max_execution_time,
    )

    async def event_generator():
        final_output = ""
        async for event in executor.execute_stream(
            system_prompt=system_prompt,
            user_input=request.input,
            model=model,
            temperature=temperature,
            history=history,
        ):
            if event["event"] == "done":
                data = json.loads(event["data"])
                final_output = data.get("output", "")
            yield event

        # Save final response
        if final_output:
            await _session_mgr.add_message(session_id, "assistant", final_output)

    return EventSourceResponse(event_generator())


# ── CRUD Endpoints ──


@router.post("")
async def create_agent(identity_data: dict):
    """Create a new agent from AgentIdentity data."""
    from bifrost.core.identity import AgentIdentity, identity_to_config

    identity = AgentIdentity(**identity_data)
    config = identity_to_config(identity)
    agent_store.add(config)

    return {
        "agent_id": identity.agent_id,
        "persona_name": identity.persona_name,
        "persona_role": identity.persona_role,
        "system_prompt": config.system_prompt,
        "status": "created",
    }


@router.put("/{agent_id}")
async def update_agent(agent_id: str, identity_data: dict):
    """Update an existing agent with new identity data."""
    from bifrost.core.identity import AgentIdentity, identity_to_config

    identity_data["agent_id"] = agent_id
    identity = AgentIdentity(**identity_data)
    config = identity_to_config(identity)
    agent_store.add(config)

    return {
        "agent_id": agent_id,
        "persona_name": identity.persona_name,
        "persona_role": identity.persona_role,
        "status": "updated",
    }


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete an agent by ID."""
    removed = agent_store.remove(agent_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return {"agent_id": agent_id, "status": "deleted"}


@router.get("/{agent_id}/prompt")
async def get_agent_prompt(agent_id: str):
    """Get the system prompt for an agent."""
    config = agent_store.get(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return {
        "agent_id": agent_id,
        "system_prompt": config.system_prompt,
    }


@router.get("/{agent_id}/introduce")
async def introduce_agent(agent_id: str):
    """Get an agent's self-introduction."""
    config = agent_store.get(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    role = config.metadata.get("persona_role", "AI Assistant")
    lang = config.metadata.get("language", "th")

    if lang == "th":
        intro = (
            f"สวัสดีครับ ผมชื่อ {config.name} "
            f"ทำหน้าที่เป็น {role} "
            f"ใน Asgard AI Platform"
        )
    else:
        intro = (
            f"Hello, I'm {config.name}, "
            f"serving as {role} "
            f"in the Asgard AI Platform."
        )

    return {
        "agent_id": agent_id,
        "name": config.name,
        "introduction": intro,
    }
