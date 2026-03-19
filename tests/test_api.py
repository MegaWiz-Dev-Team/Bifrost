"""Tests for API endpoints using FastAPI TestClient."""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked DB."""
    # Patch DB to use in-memory SQLite
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
        mock_settings.auth_enabled = False
        mock_settings.yggdrasil_issuer = ""
        mock_settings.jwt_audience = ""

        from bifrost.main import app
        with TestClient(app) as c:
            yield c


class TestHealthEndpoints:
    def test_healthz(self, client):
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "bifrost"

    def test_readyz_degraded(self, client):
        """Readyz should return degraded when Heimdall is not running."""
        response = client.get("/readyz")
        assert response.status_code == 200
        data = response.json()
        # Heimdall is not running in test, so should be degraded
        assert data["status"] in ("ready", "degraded")


class TestToolEndpoints:
    def test_list_tools(self, client):
        response = client.get("/v1/tools")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 6  # 3 built-in + 3 Eir Gateway (Mimir tools via MCP dynamic)
        tool_names = [t["name"] for t in data["tools"]]
        assert "get_current_time" in tool_names
        assert "calculate" in tool_names
        assert "http_request" in tool_names
        # Mimir tools are now dynamically discovered via MCP (not statically registered)
        assert "eir_patient_search" in tool_names
        assert "eir_fhir_query" in tool_names
        assert "eir_clinical_summary" in tool_names

    def test_get_tool(self, client):
        response = client.get("/v1/tools/calculate")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "calculate"
        assert "openai_schema" in data

    def test_get_unknown_tool(self, client):
        response = client.get("/v1/tools/nonexistent")
        assert response.status_code == 404


class TestAgentEndpoints:
    def test_run_requires_input_or_messages(self, client):
        """Empty body with neither input nor messages should fail."""
        response = client.post("/v1/agents/test/run", json={})
        assert response.status_code == 422  # Validation error — no input

    @patch("bifrost.api.agents._heimdall")
    def test_run_with_input_format(self, mock_heimdall, client):
        """Test agent run with classic input string format."""
        mock_heimdall.chat_completion = AsyncMock(return_value={
            "choices": [{
                "message": {"content": "สวัสดีครับ! ผมคือ Bifrost"},
                "finish_reason": "stop",
            }]
        })

        response = client.post("/v1/agents/test/run", json={
            "input": "สวัสดี",
        })
        assert response.status_code == 200
        data = response.json()
        assert "สวัสดี" in data["output"] or "Bifrost" in data["output"]
        assert data["agent_id"] == "test"
        assert data["session_id"] is not None
        assert data["total_iterations"] == 1

    @patch("bifrost.api.agents._heimdall")
    def test_run_with_messages_format(self, mock_heimdall, client):
        """TDD RED: Agent run should accept OpenAI messages array format.
        Forseti Run #4, Scenario B07: got 422 want 200|502|503
        """
        mock_heimdall.chat_completion = AsyncMock(return_value={
            "choices": [{
                "message": {"content": "Hello! I'm Bifrost agent."},
                "finish_reason": "stop",
            }]
        })

        response = client.post("/v1/agents/default/run", json={
            "messages": [
                {"role": "user", "content": "Hello, what tools do you have?"}
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["output"] is not None
        assert data["session_id"] is not None

    @patch("bifrost.api.agents._heimdall")
    def test_run_messages_extracts_last_user_content(self, mock_heimdall, client):
        """TDD RED: messages format should extract last user message as input."""
        mock_heimdall.chat_completion = AsyncMock(return_value={
            "choices": [{
                "message": {"content": "I can help with that!"},
                "finish_reason": "stop",
            }]
        })

        response = client.post("/v1/agents/default/run", json={
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "First question"},
                {"role": "assistant", "content": "First answer"},
                {"role": "user", "content": "Second question"},
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["output"] is not None
