"""Tests for MCP Sidecar wiring into Bifrost agents.

Sprint 33 Phase 4 — Verify the Yggdrasil and Eir MCP sidecars
are properly configured and connected via the MCPToolAdapter.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ─── Config Tests ─────────────────────────────────────────────────────────

class TestMCPSidecarConfig:
    """Verify sidecar URLs are configurable."""

    def test_yggdrasil_mcp_url_default(self):
        from bifrost.config import Settings
        s = Settings(
            _env_file=None,
            yggdrasil_mcp_url="http://localhost:8090/rpc",
        )
        assert s.yggdrasil_mcp_url == "http://localhost:8090/rpc"
        assert s.yggdrasil_mcp_enabled is True

    def test_eir_mcp_url_default(self):
        from bifrost.config import Settings
        s = Settings(
            _env_file=None,
            eir_mcp_url="http://localhost:8091/rpc",
        )
        assert s.eir_mcp_url == "http://localhost:8091/rpc"
        assert s.eir_mcp_enabled is True

    def test_sidecar_can_be_disabled(self):
        from bifrost.config import Settings
        s = Settings(
            _env_file=None,
            yggdrasil_mcp_enabled=False,
            eir_mcp_enabled=False,
        )
        assert s.yggdrasil_mcp_enabled is False
        assert s.eir_mcp_enabled is False


# ─── MCP Adapter Discovery Tests ──────────────────────────────────────────

class TestMCPSidecarDiscovery:
    """Test that MCPToolAdapter correctly discovers sidecar tools."""

    @pytest.mark.asyncio
    async def test_discover_yggdrasil_tools(self):
        """MCPToolAdapter should discover validate_token and get_user_roles."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        # Mock the HTTP response from yggdrasil-mcp sidecar
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {
                        "name": "validate_token",
                        "description": "Validate a JWT token",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "token": {"type": "string"}
                            },
                            "required": ["token"],
                        },
                    },
                    {
                        "name": "get_user_roles",
                        "description": "Get user roles",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "user_id": {"type": "string"}
                            },
                            "required": ["user_id"],
                        },
                    },
                ]
            },
        }

        adapter = MCPToolAdapter(
            server_url="http://localhost:8090/rpc",
            server_name="yggdrasil-mcp",
        )

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            tools = await adapter.discover_tools()

        assert len(tools) == 2
        tool_names = [t.__name__ for t in tools]
        assert "validate_token" in tool_names
        assert "get_user_roles" in tool_names

        # Verify tool annotations
        vt = next(t for t in tools if t.__name__ == "validate_token")
        assert "token" in vt.__annotations__
        assert vt.__annotations__["token"] == str

    @pytest.mark.asyncio
    async def test_discover_eir_tools(self):
        """MCPToolAdapter should discover get_patient_medical_history and book_appointment."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {
                        "name": "get_patient_medical_history",
                        "description": "Get patient medical history via FHIR",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "patient_id": {"type": "string"}
                            },
                            "required": ["patient_id"],
                        },
                    },
                    {
                        "name": "book_appointment",
                        "description": "Book a FHIR appointment",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "patient_id": {"type": "string"},
                                "practitioner_id": {"type": "string"},
                                "start": {"type": "string"},
                                "end": {"type": "string"},
                            },
                            "required": ["patient_id", "practitioner_id", "start", "end"],
                        },
                    },
                ]
            },
        }

        adapter = MCPToolAdapter(
            server_url="http://localhost:8091/rpc",
            server_name="eir-mcp",
        )

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            tools = await adapter.discover_tools()

        assert len(tools) == 2
        tool_names = [t.__name__ for t in tools]
        assert "get_patient_medical_history" in tool_names
        assert "book_appointment" in tool_names

    @pytest.mark.asyncio
    async def test_sidecar_unreachable_returns_empty(self):
        """When sidecar is down, discovery should return empty list gracefully."""
        from bifrost.core.mcp_adapter import MCPToolAdapter
        import httpx

        adapter = MCPToolAdapter(
            server_url="http://localhost:99999/rpc",
            server_name="dead-sidecar",
        )

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            tools = await adapter.discover_tools()

        assert tools == []


# ─── Agent Tool Injection Tests ───────────────────────────────────────────

class TestAgentToolInjection:
    """Verify MCP tools can be injected into ADK agents."""

    def test_eir_agent_set_mcp_tools(self):
        """Eir agent should accept injected MCP tools."""
        try:
            from bifrost.agents.eir.agent import set_mcp_tools, create_agent

            mock_tools = [lambda: "tool1", lambda: "tool2"]
            set_mcp_tools(mock_tools)
            agent = create_agent()
            assert agent.name == "Eir"
            # Tools should be in the agent
        except ImportError:
            pytest.skip("google-adk not installed")

    def test_yggdrasil_agent_set_mcp_tools(self):
        """Yggdrasil agent should accept injected MCP tools."""
        try:
            from bifrost.agents.yggdrasil.agent import set_mcp_tools, create_agent

            mock_tools = [lambda: "validate", lambda: "roles"]
            set_mcp_tools(mock_tools)
            agent = create_agent()
            assert agent.name == "Yggdrasil"
        except ImportError:
            pytest.skip("google-adk not installed")
