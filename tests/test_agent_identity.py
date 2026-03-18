"""🌈 Bifrost — TDD Tests for AgentIdentity.

Tests identity model, system prompt builder, store persistence, and CRUD API.

Run: cd /Users/mimir/Developer/Bifrost && python -m pytest tests/test_agent_identity.py -v
"""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from bifrost.core.agents import AgentConfig, AgentStore


# ═══════════════════════════════════════════
# 1. AgentIdentity Model
# ═══════════════════════════════════════════


def test_identity_model_defaults():
    """AgentIdentity with minimal fields should have sensible defaults."""
    from bifrost.core.identity import AgentIdentity

    identity = AgentIdentity(
        agent_id="nurse-ai",
        persona_name="Nurse AI",
        persona_role="Medical Assistant",
    )
    assert identity.agent_id == "nurse-ai"
    assert identity.persona_name == "Nurse AI"
    assert identity.persona_role == "Medical Assistant"
    assert identity.persona_description == ""
    assert identity.language == "th"
    assert identity.tone == "professional"
    assert identity.capabilities == []
    assert identity.constraints == []
    assert identity.knowledge_domains == []
    assert identity.version == 1


def test_identity_model_full():
    """AgentIdentity with all fields populated."""
    from bifrost.core.identity import AgentIdentity

    identity = AgentIdentity(
        agent_id="specialist-ai",
        persona_name="Dr. AI",
        persona_role="Cardiologist AI",
        persona_description="Expert in cardiovascular medicine",
        language="th",
        tone="empathetic",
        capabilities=["diagnose_symptoms", "prescribe_medication", "interpret_ecg"],
        constraints=[
            "Never diagnose without sufficient data",
            "Always recommend in-person consultation for critical cases",
        ],
        knowledge_domains=["cardiology", "pharmacology", "ecg_interpretation"],
        model="mlx-community/Qwen3.5-9B-MLX-4bit",
        temperature=0.3,
        tools=["fhir_search", "eir_gateway"],
        max_iterations=15,
        version=2,
    )
    assert identity.agent_id == "specialist-ai"
    assert len(identity.capabilities) == 3
    assert len(identity.constraints) == 2
    assert len(identity.knowledge_domains) == 3
    assert identity.temperature == 0.3
    assert identity.version == 2


def test_identity_persona_required():
    """AgentIdentity must have agent_id, persona_name, persona_role."""
    from bifrost.core.identity import AgentIdentity

    with pytest.raises(Exception):
        AgentIdentity()  # type: ignore

    with pytest.raises(Exception):
        AgentIdentity(agent_id="x")  # type: ignore


# ═══════════════════════════════════════════
# 2. SystemPromptBuilder
# ═══════════════════════════════════════════


def test_prompt_builder_basic():
    """Builder produces prompt with persona section."""
    from bifrost.core.identity import AgentIdentity, SystemPromptBuilder

    identity = AgentIdentity(
        agent_id="nurse-ai",
        persona_name="Nurse AI",
        persona_role="Medical Assistant",
    )
    prompt = SystemPromptBuilder.build(identity)

    assert "Nurse AI" in prompt
    assert "Medical Assistant" in prompt
    assert isinstance(prompt, str)
    assert len(prompt) > 20


def test_prompt_builder_with_constraints():
    """Builder includes constraints section."""
    from bifrost.core.identity import AgentIdentity, SystemPromptBuilder

    identity = AgentIdentity(
        agent_id="safe-ai",
        persona_name="Safe AI",
        persona_role="General Assistant",
        constraints=["Never share personal data", "Always cite sources"],
    )
    prompt = SystemPromptBuilder.build(identity)

    assert "Never share personal data" in prompt
    assert "Always cite sources" in prompt


def test_prompt_builder_bilingual():
    """Builder generates Thai instructions for language='th'."""
    from bifrost.core.identity import AgentIdentity, SystemPromptBuilder

    identity = AgentIdentity(
        agent_id="thai-ai",
        persona_name="ผู้ช่วย AI",
        persona_role="ผู้ช่วยทั่วไป",
        language="th",
    )
    prompt = SystemPromptBuilder.build(identity)

    # Should contain Thai instruction
    assert "ภาษาไทย" in prompt or "Thai" in prompt


def test_prompt_builder_with_knowledge():
    """Builder includes knowledge domains."""
    from bifrost.core.identity import AgentIdentity, SystemPromptBuilder

    identity = AgentIdentity(
        agent_id="med-ai",
        persona_name="Med AI",
        persona_role="Medical AI",
        knowledge_domains=["cardiology", "pharmacology"],
    )
    prompt = SystemPromptBuilder.build(identity)

    assert "cardiology" in prompt
    assert "pharmacology" in prompt


# ═══════════════════════════════════════════
# 3. Store Persistence
# ═══════════════════════════════════════════


def test_store_crud():
    """AgentStore basic add/get/list/remove."""
    store = AgentStore()

    config = AgentConfig(id="test-1", name="Test", system_prompt="Hello")
    store.add(config)

    assert store.get("test-1") is not None
    assert len(store.list_agents()) == 1
    assert store.remove("test-1") is True
    assert store.get("test-1") is None


def test_store_save_load_file():
    """AgentStore saves to and loads from JSON file."""
    store = AgentStore()
    config = AgentConfig(id="persist-1", name="Persist Test", system_prompt="Persistent")
    store.add(config)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        tmppath = f.name

    try:
        store.save_to_file(tmppath)

        # Load into new store
        store2 = AgentStore()
        store2.load_from_file(tmppath)

        loaded = store2.get("persist-1")
        assert loaded is not None
        assert loaded.name == "Persist Test"
        assert loaded.system_prompt == "Persistent"
    finally:
        os.unlink(tmppath)


def test_store_identity_to_config():
    """AgentIdentity can be converted to AgentConfig with built prompt."""
    from bifrost.core.identity import AgentIdentity, identity_to_config

    identity = AgentIdentity(
        agent_id="convert-test",
        persona_name="Convert AI",
        persona_role="Tester",
        capabilities=["testing"],
        model="test-model",
        temperature=0.5,
    )

    config = identity_to_config(identity)
    assert isinstance(config, AgentConfig)
    assert config.id == "convert-test"
    assert config.name == "Convert AI"
    assert "Convert AI" in config.system_prompt
    assert "testing" in config.system_prompt
    assert config.model == "test-model"
    assert config.temperature == 0.5


# ═══════════════════════════════════════════
# 4. API Endpoints
# ═══════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_create_agent():
    """POST /v1/agents creates a new agent from identity."""
    from bifrost.config import settings
    settings.auth_enabled = False

    from httpx import ASGITransport, AsyncClient
    from bifrost.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/agents", json={
            "agent_id": "api-test-agent",
            "persona_name": "API Test",
            "persona_role": "Tester",
            "capabilities": ["testing"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "api-test-agent"
        assert "system_prompt" in data


@pytest.mark.asyncio
async def test_api_update_agent():
    """PUT /v1/agents/{id} updates an existing agent."""
    from bifrost.config import settings
    settings.auth_enabled = False

    from httpx import ASGITransport, AsyncClient
    from bifrost.main import app
    from bifrost.core.agents import agent_store, AgentConfig

    # Pre-create agent
    agent_store.add(AgentConfig(id="update-test", name="Old", system_prompt="old"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put("/v1/agents/update-test", json={
            "agent_id": "update-test",
            "persona_name": "Updated AI",
            "persona_role": "Updated Role",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["persona_name"] == "Updated AI"


@pytest.mark.asyncio
async def test_api_delete_agent():
    """DELETE /v1/agents/{id} removes an agent."""
    from bifrost.config import settings
    settings.auth_enabled = False

    from httpx import ASGITransport, AsyncClient
    from bifrost.main import app
    from bifrost.core.agents import agent_store, AgentConfig

    agent_store.add(AgentConfig(id="delete-test", name="Delete", system_prompt="bye"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/v1/agents/delete-test")
        assert resp.status_code == 200

        # Confirm removed
        resp2 = await client.get("/v1/agents")
        agents = resp2.json().get("agents", [])
        ids = [a["id"] for a in agents]
        assert "delete-test" not in ids


@pytest.mark.asyncio
async def test_api_preview_prompt():
    """GET /v1/agents/{id}/prompt returns the built system prompt."""
    from bifrost.config import settings
    settings.auth_enabled = False

    from httpx import ASGITransport, AsyncClient
    from bifrost.main import app
    from bifrost.core.agents import agent_store, AgentConfig

    agent_store.add(AgentConfig(id="prompt-test", name="Prompt", system_prompt="I am Prompt"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/agents/prompt-test/prompt")
        assert resp.status_code == 200
        data = resp.json()
        assert "system_prompt" in data
        assert len(data["system_prompt"]) > 0
