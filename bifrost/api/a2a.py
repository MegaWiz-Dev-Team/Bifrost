"""A2A (Agent-to-Agent) Protocol support.

Implements Google's A2A protocol for inter-agent communication:
- Agent Card (/.well-known/agent.json)
- Task lifecycle (send, get status)
- Structured message exchange
"""

import uuid
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from bifrost.core.agents import agent_store

router = APIRouter(tags=["a2a"])


# === A2A Models ===

class TaskState(str, Enum):
    """A2A Task lifecycle states."""
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class A2AMessage(BaseModel):
    """A message in A2A format."""
    role: str  # "user" or "agent"
    parts: list[dict]  # [{"type": "text", "text": "..."}]


class A2ATask(BaseModel):
    """An A2A task with full lifecycle."""
    id: str
    state: TaskState = TaskState.SUBMITTED
    messages: list[A2AMessage] = []
    metadata: dict = {}
    created_at: str = ""
    updated_at: str = ""


# In-memory task store (for MVP)
_tasks: dict[str, A2ATask] = {}


# === Agent Card ===

def build_agent_card(base_url: str = "http://localhost:8100") -> dict:
    """Build the A2A Agent Card for Bifrost."""
    agents = agent_store.list_agents()
    skills = []
    for agent in agents:
        skills.append({
            "id": agent.id,
            "name": agent.name,
            "description": agent.system_prompt[:200] if agent.system_prompt else "",
            "tags": agent.tools,
        })

    return {
        "name": "Bifrost Agent Runtime",
        "description": "Self-hosted Agent Runtime Engine for the Asgard AI Platform. "
                      "Supports ReAct loop execution, tool calling, MCP integration, "
                      "and multi-agent collaboration.",
        "url": base_url,
        "version": "0.1.0",
        "protocol": "a2a",
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "skills": skills,
        "authentication": {
            "schemes": ["bearer"],
        },
    }


# === A2A Endpoints ===

@router.get("/.well-known/agent.json")
async def agent_card():
    """Return the A2A Agent Card."""
    from bifrost.config import settings
    base_url = f"http://{settings.bifrost_host}:{settings.bifrost_port}"
    return build_agent_card(base_url)


class SendTaskRequest(BaseModel):
    """Request to send a task to an agent."""
    message: A2AMessage
    agent_id: str = "default"
    metadata: dict = {}


@router.post("/a2a/tasks/send")
async def send_task(request: SendTaskRequest):
    """Send a task to an agent (A2A protocol).

    Creates a task, executes it, and returns the result.
    """
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    task = A2ATask(
        id=task_id,
        state=TaskState.WORKING,
        messages=[request.message],
        metadata={**request.metadata, "agent_id": request.agent_id},
        created_at=now,
        updated_at=now,
    )
    _tasks[task_id] = task

    # Extract text from message parts
    user_text = " ".join(
        p.get("text", "") for p in request.message.parts if p.get("type") == "text"
    )

    if not user_text:
        task.state = TaskState.FAILED
        task.updated_at = datetime.now(timezone.utc).isoformat()
        return {"task": task.model_dump()}

    # Execute via Bifrost agent
    try:
        from bifrost.clients.heimdall import HeimdallClient
        from bifrost.core.executor import AgentExecutor
        from bifrost.tools.registry import registry
        from bifrost.config import settings

        agent_config = agent_store.get(request.agent_id)
        system_prompt = agent_config.system_prompt if agent_config else "You are a helpful assistant."
        model = agent_config.model if agent_config else None

        executor = AgentExecutor(
            heimdall=HeimdallClient(),
            tool_registry=registry,
            max_iterations=settings.max_iterations,
            max_execution_time=settings.max_execution_time,
        )

        result = await executor.execute(
            system_prompt=system_prompt,
            user_input=user_text,
            model=model,
        )

        # Add agent response
        response_message = A2AMessage(
            role="agent",
            parts=[{"type": "text", "text": result.output}],
        )
        task.messages.append(response_message)
        task.state = TaskState.COMPLETED
        task.updated_at = datetime.now(timezone.utc).isoformat()

    except Exception as e:
        task.state = TaskState.FAILED
        task.messages.append(A2AMessage(
            role="agent",
            parts=[{"type": "text", "text": f"Error: {e}"}],
        ))
        task.updated_at = datetime.now(timezone.utc).isoformat()

    return {"task": task.model_dump()}


@router.get("/a2a/tasks/{task_id}")
async def get_task(task_id: str):
    """Get task status and messages."""
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return {"task": task.model_dump()}


@router.get("/a2a/tasks")
async def list_tasks(limit: int = 20):
    """List recent tasks."""
    tasks = sorted(_tasks.values(), key=lambda t: t.created_at, reverse=True)[:limit]
    return {
        "tasks": [t.model_dump() for t in tasks],
        "total": len(_tasks),
    }
