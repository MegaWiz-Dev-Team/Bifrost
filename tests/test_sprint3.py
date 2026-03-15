"""Tests for Sprint 3 — Agent Router, Tracing, A2A protocol, Delegate tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from bifrost.core.router import AgentRouter, AgentRoute
from bifrost.core.tracing import TraceRecord, TraceStore
from bifrost.core.agents import AgentConfig, AgentStore
from bifrost.tools.delegate import DelegateTool
from bifrost.api.a2a import A2AMessage, A2ATask, TaskState, build_agent_card


# === Agent Router Tests ===

class TestAgentRoute:
    def test_matches_pattern(self):
        route = AgentRoute(pattern=r"medical|health|symptom", target_agent_id="doc-agent")
        assert route.matches("What are the symptoms of flu?") is True
        assert route.matches("Calculate 2+3") is False

    def test_case_insensitive(self):
        route = AgentRoute(pattern=r"help", target_agent_id="helper")
        assert route.matches("HELP me") is True
        assert route.matches("Help") is True

    def test_to_dict_from_dict(self):
        route = AgentRoute(pattern="test", target_agent_id="t1", priority=5, description="Test route")
        data = route.to_dict()
        restored = AgentRoute.from_dict(data)
        assert restored.pattern == "test"
        assert restored.priority == 5

    def test_invalid_regex(self):
        route = AgentRoute(pattern="[invalid", target_agent_id="x")
        assert route.matches("anything") is False


class TestAgentRouter:
    def test_route_matching(self):
        router = AgentRouter()
        router.add_route(AgentRoute(pattern=r"medical|health", target_agent_id="doc-agent", priority=10))
        router.add_route(AgentRoute(pattern=r"code|program", target_agent_id="code-agent", priority=5))

        assert router.route("I have a health question") == "doc-agent"
        assert router.route("Write a program") == "code-agent"

    def test_default_fallback(self):
        router = AgentRouter()
        assert router.route("random question") == "default"

    def test_custom_default(self):
        router = AgentRouter()
        router.set_default("general")
        assert router.route("anything") == "general"

    def test_priority_ordering(self):
        router = AgentRouter()
        router.add_route(AgentRoute(pattern=".*", target_agent_id="low", priority=1))
        router.add_route(AgentRoute(pattern=".*", target_agent_id="high", priority=10))
        # High priority should match first
        assert router.route("test") == "high"

    def test_remove_route(self):
        router = AgentRouter()
        router.add_route(AgentRoute(pattern="test", target_agent_id="t"))
        assert len(router) == 1
        assert router.remove_route("test") is True
        assert len(router) == 0

    def test_list_routes(self):
        router = AgentRouter()
        router.add_route(AgentRoute(pattern="a", target_agent_id="1"))
        router.add_route(AgentRoute(pattern="b", target_agent_id="2"))
        assert len(router.list_routes()) == 2


# === Delegate Tool Tests ===

class TestDelegateTool:
    def test_schema(self):
        tool = DelegateTool(executor_factory=AsyncMock())
        assert tool.name == "delegate_to_agent"
        assert "agent_id" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_execute_delegates(self):
        factory = AsyncMock(return_value="I found the answer!")
        tool = DelegateTool(executor_factory=factory)
        result = await tool.execute(agent_id="doc-agent", task="Find symptoms of flu")
        factory.assert_called_once_with("doc-agent", "Find symptoms of flu")
        assert "I found the answer!" in result

    @pytest.mark.asyncio
    async def test_missing_args(self):
        tool = DelegateTool(executor_factory=AsyncMock())
        result = await tool.execute()
        assert "Error" in result or "required" in result

    @pytest.mark.asyncio
    async def test_delegation_error(self):
        factory = AsyncMock(side_effect=Exception("Agent not found"))
        tool = DelegateTool(executor_factory=factory)
        result = await tool.execute(agent_id="nonexistent", task="do something")
        assert "error" in result.lower()


# === Tracing Tests ===

class TestTraceRecord:
    def test_auto_timestamp(self):
        record = TraceRecord(
            session_id="s1", agent_id="a1", step=1,
            type="tool_call", content="test",
        )
        assert record.timestamp != ""
        assert "T" in record.timestamp


class TestTraceStore:
    @pytest.mark.asyncio
    async def test_save_and_get(self):
        store = TraceStore()
        store._initialized = False

        # Patch get_db to use in-memory SQLite
        import aiosqlite
        db = await aiosqlite.connect(":memory:")
        from bifrost.db.connection import SCHEMA_SQL
        await db.executescript(SCHEMA_SQL)
        await db.commit()

        with patch("bifrost.core.tracing.get_db", return_value=db):
            # Need a session first
            await db.execute(
                "INSERT INTO sessions (id, agent_id) VALUES (?, ?)",
                ("test-session", "test-agent"),
            )
            await db.commit()

            record = TraceRecord(
                session_id="test-session", agent_id="test-agent",
                step=1, type="tool_call", content="Called calculate",
                tool_name="calculate", tool_args={"expression": "2+3"},
                duration_ms=15.5,
            )
            record_id = await store.save(record)
            assert record_id is not None

            traces = await store.get_by_session("test-session")
            assert len(traces) == 1
            assert traces[0]["tool_name"] == "calculate"

            summary = await store.get_summary("test-session")
            assert summary["total_steps"] == 1
            assert summary["tool_calls"] == 1

        await db.close()


# === A2A Protocol Tests ===

class TestA2AModels:
    def test_task_state_enum(self):
        assert TaskState.SUBMITTED == "submitted"
        assert TaskState.COMPLETED == "completed"

    def test_a2a_message(self):
        msg = A2AMessage(role="user", parts=[{"type": "text", "text": "Hello"}])
        assert msg.role == "user"
        assert msg.parts[0]["text"] == "Hello"

    def test_a2a_task(self):
        task = A2ATask(id="t1", state=TaskState.WORKING)
        assert task.state == TaskState.WORKING

    def test_build_agent_card(self):
        card = build_agent_card("http://localhost:8100")
        assert card["name"] == "Bifrost Agent Runtime"
        assert card["protocol"] == "a2a"
        assert card["capabilities"]["streaming"] is True
        assert "skills" in card


class TestA2AEndpoints:
    @pytest.fixture
    def client(self):
        with patch("bifrost.config.settings") as mock_settings:
            mock_settings.heimdall_url = "http://localhost:8080"
            mock_settings.heimdall_api_key = ""
            mock_settings.bifrost_host = "0.0.0.0"
            mock_settings.bifrost_port = 8100
            mock_settings.database_path = ":memory:"
            mock_settings.max_iterations = 10
            mock_settings.max_execution_time = 120
            mock_settings.default_model = "qwen3.5"
            mock_settings.log_level = "WARNING"
            mock_settings.mimir_url = "http://localhost:3000"
            mock_settings.mimir_api_key = ""
            mock_settings.mimir_tenant_id = "default"
            mock_settings.auth_enabled = False
            mock_settings.yggdrasil_issuer = ""
            mock_settings.jwt_audience = ""

            from bifrost.main import app
            with TestClient(app) as c:
                yield c

    def test_agent_card(self, client):
        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200
        data = response.json()
        assert data["protocol"] == "a2a"
        assert "skills" in data

    def test_list_tasks_empty(self, client):
        response = client.get("/a2a/tasks")
        assert response.status_code == 200

    def test_get_unknown_task(self, client):
        response = client.get("/a2a/tasks/nonexistent")
        assert response.status_code == 404

    def test_trace_endpoint(self, client):
        response = client.get("/v1/traces/nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    def test_list_agents(self, client):
        response = client.get("/v1/agents")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1  # At least the default agent
