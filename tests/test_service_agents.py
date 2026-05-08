"""Sprint 2 TDD — Self-Aware Agents + Prompt Routing.

Tests: 12 agent definitions, self-awareness tools, API intro, model routing, prompt cache.

Run: python -m pytest tests/test_service_agents.py -v
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ═══════════════════════════════════════════
# 1. 12 Service Agent Definitions
# ═══════════════════════════════════════════


def test_12_agents_defined():
    """SERVICE_AGENTS contains exactly 12 agent identity definitions."""
    from bifrost.core.service_agents import SERVICE_AGENTS

    assert len(SERVICE_AGENTS) == 12
    # Each should be an AgentIdentity
    for agent in SERVICE_AGENTS:
        assert hasattr(agent, "agent_id")
        assert hasattr(agent, "persona_name")
        assert hasattr(agent, "persona_role")


def test_agent_identities_valid():
    """All 12 agents have required fields and unique IDs."""
    from bifrost.core.service_agents import SERVICE_AGENTS

    ids = set()
    expected_services = {
        "mimir", "bifrost", "heimdall", "ratatoskr", "fenrir",
        "forseti", "huginn", "muninn", "eir", "vardr",
        "yggdrasil", "asgard",
    }

    for agent in SERVICE_AGENTS:
        assert agent.agent_id, f"Agent missing id: {agent}"
        assert agent.persona_name, f"Agent missing name: {agent.agent_id}"
        assert agent.persona_role, f"Agent missing role: {agent.agent_id}"
        assert len(agent.capabilities) > 0, f"Agent has no capabilities: {agent.agent_id}"
        ids.add(agent.agent_id)

    # Check uniqueness
    assert len(ids) == 12

    # All expected services present (strip "-agent" suffix)
    agent_bases = {aid.replace("-agent", "") for aid in ids}
    assert agent_bases == expected_services


def test_deploy_all_agents():
    """deploy_all_agents() registers all 12 into AgentStore."""
    from bifrost.core.service_agents import deploy_all_agents
    from bifrost.core.agents import AgentStore

    store = AgentStore()
    count = deploy_all_agents(store)

    assert count == 12
    assert len(store) == 12
    assert store.get("fenrir-agent") is not None
    assert store.get("heimdall-agent") is not None


# ═══════════════════════════════════════════
# 2. Self-Awareness Tools
# ═══════════════════════════════════════════


@pytest.mark.asyncio
async def test_self_introduce_tool():
    """SelfIntroduceTool returns agent's identity description."""
    from bifrost.tools.self_awareness import SelfIntroduceTool

    tool = SelfIntroduceTool()
    assert tool.name == "self_introduce"

    # Mock the store to have a fenrir agent
    from bifrost.core.agents import AgentConfig
    mock_store_get = MagicMock(return_value=AgentConfig(
        id="fenrir-agent",
        name="Fenrir",
        system_prompt="You are Fenrir.",
        metadata={"persona_role": "Browser Automation", "language": "th"},
    ))

    with patch("bifrost.tools.self_awareness.agent_store.get", mock_store_get):
        result = await tool.execute(agent_id="fenrir-agent")

    assert "Fenrir" in result
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_health_check_tool():
    """HealthCheckTool checks service health via HTTP."""
    from bifrost.tools.self_awareness import HealthCheckTool

    tool = HealthCheckTool()
    assert tool.name == "health_check"

    # Mock httpx to return 200
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("bifrost.tools.self_awareness.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        MockClient.return_value = mock_client

        result = await tool.execute(service_url="http://localhost:8200/health")

    assert "healthy" in result.lower() or "ok" in result.lower()


@pytest.mark.asyncio
async def test_who_am_i_tool():
    """WhoAmITool returns identity card."""
    from bifrost.tools.self_awareness import WhoAmITool

    tool = WhoAmITool()
    assert tool.name == "who_am_i"

    from bifrost.core.agents import AgentConfig
    mock_config = AgentConfig(
        id="bifrost-agent",
        name="Bifrost",
        system_prompt="You are Bifrost.",
        metadata={
            "persona_role": "Agent Orchestrator",
            "language": "th",
            "identity_version": 1,
        },
    )

    with patch("bifrost.tools.self_awareness.agent_store.get", return_value=mock_config):
        result = await tool.execute(agent_id="bifrost-agent")

    assert "bifrost-agent" in result.lower() or "Bifrost" in result


# ═══════════════════════════════════════════
# 3. API Introduce Endpoint
# ═══════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_introduce_endpoint():
    """GET /v1/agents/{id}/introduce returns self-introduction."""
    from bifrost.config import settings
    settings.auth_enabled = False

    from httpx import ASGITransport, AsyncClient
    from bifrost.main import app
    from bifrost.core.agents import agent_store, AgentConfig

    agent_store.add(AgentConfig(
        id="intro-test",
        name="Test Agent",
        system_prompt="I am a test agent.",
        metadata={"persona_role": "Tester"},
    ))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/agents/intro-test/introduce")
        assert resp.status_code == 200
        data = resp.json()
        assert "introduction" in data
        assert "Test Agent" in data["introduction"]


# ═══════════════════════════════════════════
# 4. Heimdall Prompt Routing + Cache
# ═══════════════════════════════════════════


def test_agent_model_routing():
    """model_for_agent returns agent-specific model config."""
    from bifrost.clients.heimdall import HeimdallClient

    client = HeimdallClient()

    # Configure model routing
    client.set_agent_model("fenrir-agent", "mlx-community/Qwen3.5-9B-MLX-4bit")
    client.set_agent_model("huginn-agent", "mlx-community/Qwen3.5-3B-MLX-4bit")

    assert client.model_for_agent("fenrir-agent") == "mlx-community/Qwen3.5-9B-MLX-4bit"
    assert client.model_for_agent("huginn-agent") == "mlx-community/Qwen3.5-3B-MLX-4bit"
    # Unknown agent falls back to default
    assert client.model_for_agent("unknown-agent") is not None


def test_prompt_cache_hit():
    """PromptCache returns cached prompt on hit."""
    from bifrost.clients.heimdall import PromptCache

    cache = PromptCache(max_size=100, ttl_seconds=300)
    cache.put("fenrir-agent", "You are Fenrir, a browser automation agent.")

    result = cache.get("fenrir-agent")
    assert result == "You are Fenrir, a browser automation agent."
    assert cache.hit_rate() > 0


def test_prompt_cache_miss():
    """PromptCache returns None on miss."""
    from bifrost.clients.heimdall import PromptCache

    cache = PromptCache(max_size=100, ttl_seconds=300)

    result = cache.get("nonexistent-agent")
    assert result is None
