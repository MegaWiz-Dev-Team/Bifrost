"""Odin API — REST endpoints for the meta-agent orchestrator."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from bifrost.core.odin import OdinOrchestrator

logger = logging.getLogger("bifrost.api.odin")

router = APIRouter(prefix="/v1/odin", tags=["odin"])

_odin = OdinOrchestrator()


class AskRequest(BaseModel):
    """Request body for Odin ask."""
    question: str


class DelegateStep(BaseModel):
    """A single step in a delegation chain."""
    agent_id: str
    task: str


class DelegateRequest(BaseModel):
    """Request body for delegation chain."""
    steps: list[DelegateStep]


@router.post("/ask")
async def odin_ask(req: AskRequest):
    """Route a question to the most relevant agent."""
    result = await _odin.ask(req.question)
    return result


@router.post("/standup")
async def odin_standup():
    """Run team standup — poll all agents for status."""
    report = await _odin.team_standup()
    return report


@router.post("/delegate")
async def odin_delegate(req: DelegateRequest):
    """Run a delegation chain across multiple agents."""
    steps = [{"agent_id": s.agent_id, "task": s.task} for s in req.steps]
    result = await _odin.delegate_chain(steps)
    return result
