"""Odin API routes — multi-agent orchestration endpoints.

Sprint 36 endpoints:
- POST /v1/odin/orchestrate — full orchestration pipeline
- POST /v1/odin/plan — decomposition preview only
- GET  /v1/odin/agent-types — list available sub-agent types
- POST /v1/odin/ask — legacy routing (Sprint 3 compat)
- POST /v1/odin/standup — legacy team standup (Sprint 3 compat)
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from bifrost.agents.odin.coordinator import OdinCoordinator
from bifrost.agents.odin.planner import OdinPlanner
from bifrost.agents.odin.registry import SubAgentRegistry
from bifrost.core.odin import OdinOrchestrator

logger = logging.getLogger("bifrost.api.odin")
router = APIRouter(prefix="/v1/odin", tags=["odin"])


# ─── Request/Response Models ───

class OrchestrateRequest(BaseModel):
    request: str = Field(..., description="User request to orchestrate")
    model: str | None = Field(None, description="Optional model override")
    tenant_id: str = Field("default", description="Tenant identifier")


class PlanRequest(BaseModel):
    request: str = Field(..., description="User request to decompose")


class AskRequest(BaseModel):
    question: str = Field(..., description="Question to route")


# ─── Sprint 36 Endpoints ───


@router.post("/orchestrate")
async def orchestrate(req: OrchestrateRequest):
    """Full multi-agent orchestration: decompose → spawn → synthesize."""
    try:
        from bifrost.clients.heimdall import HeimdallClient
        from bifrost.tools.registry import registry as tool_registry
        from bifrost.config import settings

        heimdall = HeimdallClient(
            base_url=settings.heimdall_url,
            api_key=settings.heimdall_api_key,
        )

        coordinator = OdinCoordinator(
            heimdall=heimdall,
            tool_registry=tool_registry,
            tenant_id=req.tenant_id,
            model=req.model,
        )

        result = await coordinator.execute(req.request)
        return result.to_dict()

    except Exception as e:
        logger.error(f"Orchestration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plan")
async def plan(req: PlanRequest):
    """Decompose a request into sub-tasks (preview only, no execution)."""
    try:
        from bifrost.clients.heimdall import HeimdallClient
        from bifrost.config import settings

        heimdall = HeimdallClient(
            base_url=settings.heimdall_url,
            api_key=settings.heimdall_api_key,
        )

        planner = OdinPlanner(heimdall=heimdall)
        task_plan = await planner.decompose(req.request)
        return task_plan.to_dict()

    except Exception as e:
        logger.error(f"Planning failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent-types")
async def agent_types():
    """List available sub-agent types."""
    registry = SubAgentRegistry()
    return {
        "types": [t.to_dict() for t in registry.list_types()],
        "count": len(registry),
    }


# ─── Legacy Endpoints (Sprint 3 Compat) ───


@router.post("/ask")
async def ask(req: AskRequest):
    """Route a question to the most relevant agent (legacy)."""
    odin = OdinOrchestrator()
    result = await odin.ask(req.question)
    return result


@router.post("/standup")
async def standup():
    """Team standup: poll all agents and report status (legacy)."""
    odin = OdinOrchestrator()
    result = await odin.team_standup()
    return result
