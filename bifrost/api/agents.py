"""Agent execution endpoints."""

import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from bifrost.clients.heimdall import HeimdallClient
from bifrost.config import settings
from bifrost.core.executor import AgentExecutor
from bifrost.memory.session import SessionManager
from bifrost.tools.registry import registry

router = APIRouter(prefix="/v1/agents", tags=["agents"])

# Shared instances
_heimdall = HeimdallClient()
_session_mgr = SessionManager()

# Default system prompt for test agents
DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant powered by Bifrost.
You have access to tools that you can use to help answer questions.
Always think step by step. Use tools when appropriate.
Respond in the same language as the user."""


class RunRequest(BaseModel):
    """Request body for agent execution."""
    input: str
    session_id: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    temperature: float = 0.7


@router.post("/{agent_id}/run")
async def run_agent(agent_id: str, request: RunRequest):
    """Execute an agent (non-streaming). Returns full result."""
    system_prompt = request.system_prompt or DEFAULT_SYSTEM_PROMPT

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
        model=request.model,
        temperature=request.temperature,
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
    system_prompt = request.system_prompt or DEFAULT_SYSTEM_PROMPT

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
            model=request.model,
            temperature=request.temperature,
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
