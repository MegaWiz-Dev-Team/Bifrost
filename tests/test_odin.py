"""Sprint 3 TDD — Odin Orchestrator.

Tests: routing, standup, delegation chain, loop safety, permissions, API endpoints.

Run: cd /Users/mimir/Developer/Bifrost && python -m pytest tests/test_odin.py -v
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ═══════════════════════════════════════════
# 1. Odin Core
# ═══════════════════════════════════════════


@pytest.mark.asyncio
async def test_odin_ask_routes_to_agent():
    """Odin.ask routes question to the most relevant agent."""
    from bifrost.core.odin import OdinOrchestrator

    odin = OdinOrchestrator()

    # Mock the agent executor to return a canned response
    async def mock_run(agent_id, task):
        return f"[{agent_id}] handled: {task}"

    odin._run_agent = mock_run

    result = await odin.ask("สแกนช่องโหว่ระบบให้หน่อย")

    assert result is not None
    assert "agent_id" in result
    assert "response" in result
    assert isinstance(result["response"], str)


@pytest.mark.asyncio
async def test_odin_team_standup():
    """Odin.team_standup polls all agents and summarizes."""
    from bifrost.core.odin import OdinOrchestrator

    odin = OdinOrchestrator()

    # Mock health checks to return mixed status
    async def mock_check(agent_id):
        if agent_id in ("mimir-agent", "bifrost-agent"):
            return {"agent_id": agent_id, "status": "healthy"}
        return {"agent_id": agent_id, "status": "unreachable"}

    odin._check_agent = mock_check

    report = await odin.team_standup()

    assert "agents" in report
    assert len(report["agents"]) > 0
    assert "healthy_count" in report
    assert "total_count" in report


@pytest.mark.asyncio
async def test_odin_delegate_chain():
    """Odin.delegate_chain runs sequential delegation with results piping."""
    from bifrost.core.odin import OdinOrchestrator

    odin = OdinOrchestrator()

    results = []
    async def mock_run(agent_id, task):
        result = f"[{agent_id}] done: {task}"
        results.append(result)
        return result

    odin._run_agent = mock_run

    chain = [
        {"agent_id": "huginn-agent", "task": "Scan for vulnerabilities"},
        {"agent_id": "muninn-agent", "task": "Fix findings from previous step"},
        {"agent_id": "forseti-agent", "task": "Test the fixes"},
    ]

    chain_result = await odin.delegate_chain(chain)

    assert len(chain_result["steps"]) == 3
    assert chain_result["completed"] == 3
    assert all("done" in r for r in results)


@pytest.mark.asyncio
async def test_odin_loop_safety():
    """Odin enforces max 3 iterations per chain to prevent infinite loops."""
    from bifrost.core.odin import OdinOrchestrator

    odin = OdinOrchestrator(max_chain_depth=3)

    async def mock_run(agent_id, task):
        return "ok"

    odin._run_agent = mock_run

    # 5-step chain should be truncated to 3
    long_chain = [
        {"agent_id": f"agent-{i}", "task": f"Step {i}"}
        for i in range(5)
    ]

    result = await odin.delegate_chain(long_chain)
    assert result["completed"] <= 3
    assert result.get("truncated") is True


def test_odin_permission_boundary():
    """Odin permission model: self=read_write, others=read_only."""
    from bifrost.core.odin import OdinOrchestrator, Permission

    odin = OdinOrchestrator()

    # Self-agent has read_write
    assert odin.get_permission("odin") == Permission.READ_WRITE

    # Other agents are read_only
    assert odin.get_permission("fenrir-agent") == Permission.READ_ONLY
    assert odin.get_permission("huginn-agent") == Permission.READ_ONLY


# ═══════════════════════════════════════════
# 2. Odin API
# ═══════════════════════════════════════════


@pytest.mark.asyncio
async def test_odin_api_ask():
    """POST /v1/odin/ask routes and returns response."""
    from bifrost.config import settings
    settings.auth_enabled = False

    from httpx import ASGITransport, AsyncClient
    from bifrost.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/odin/ask", json={
            "question": "Fenrir คืออะไร",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data


@pytest.mark.asyncio
async def test_odin_api_standup():
    """POST /v1/odin/standup returns team report."""
    from bifrost.config import settings
    settings.auth_enabled = False

    from httpx import ASGITransport, AsyncClient
    from bifrost.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/odin/standup")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "total_count" in data
