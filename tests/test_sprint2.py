"""Tests for Sprint 2 — MCP client, Mimir tools, Webhook tools, Agent config."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bifrost.clients.mcp import MCPServerConfig, MCPClient, MCPTool, MCPManager
from bifrost.core.mcp_adapter import MCPToolAdapter
from bifrost.tools.webhook import WebhookTool
from bifrost.core.agents import AgentConfig, AgentStore


# === MCP Client Tests ===

class TestMCPServerConfig:
    def test_stdio_config(self):
        cfg = MCPServerConfig(name="test", transport="stdio", command="echo")
        assert cfg.transport == "stdio"
        assert cfg.command == "echo"

    def test_sse_config(self):
        cfg = MCPServerConfig(name="test-sse", transport="sse", url="http://localhost:3001")
        assert cfg.transport == "sse"
        assert cfg.url == "http://localhost:3001"


class TestMCPTool:
    def test_creates_valid_tool(self):
        mock_server = MagicMock()
        tool = MCPTool(
            name="remote_tool",
            description="A tool from MCP server",
            parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
            server=mock_server,
        )
        assert tool.name == "remote_tool"
        assert tool.description == "A tool from MCP server"

    def test_openai_schema(self):
        mock_server = MagicMock()
        tool = MCPTool(name="test", description="test desc", parameters={"type": "object", "properties": {}}, server=mock_server)
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "test"

    @pytest.mark.asyncio
    async def test_execute_calls_server(self):
        mock_server = AsyncMock()
        mock_server.call_tool = AsyncMock(return_value="result from MCP")
        tool = MCPTool(name="test", description="test", parameters={}, server=mock_server)
        result = await tool.execute(x=42)
        mock_server.call_tool.assert_called_once_with("test", {"x": 42})
        assert result == "result from MCP"


class TestMCPManager:
    def test_initial_state(self):
        mgr = MCPManager()
        assert mgr.servers == []

    def test_get_unknown_client(self):
        mgr = MCPManager()
        assert mgr.get_client("nonexistent") is None


class TestMCPAdapterToolCreation:
    """Test MCP adapter creates equivalent tools to legacy mimir classes."""

    def test_search_knowledge_tool_created(self):
        """Adapter should create a search_knowledge callable from MCP schema."""
        adapter = MCPToolAdapter(server_url="http://localhost:3000/mcp/sse")
        schema = {
            "name": "search_knowledge",
            "description": "Search knowledge base",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
        func = adapter._convert_tool(schema)
        assert func.__name__ == "search_knowledge"
        assert callable(func)

    def test_list_sources_tool_created(self):
        """Adapter should create a list_sources callable from MCP schema."""
        adapter = MCPToolAdapter(server_url="http://localhost:3000/mcp/sse")
        schema = {
            "name": "list_sources",
            "description": "List sources",
            "inputSchema": {"type": "object", "properties": {}},
        }
        func = adapter._convert_tool(schema)
        assert func.__name__ == "list_sources"

    def test_get_document_tool_created(self):
        """Adapter should create get_document_chunk callable from MCP schema."""
        adapter = MCPToolAdapter(server_url="http://localhost:3000/mcp/sse")
        schema = {
            "name": "get_document_chunk",
            "description": "Get document chunk",
            "inputSchema": {
                "type": "object",
                "properties": {"chunk_id": {"type": "integer"}},
                "required": ["chunk_id"],
            },
        }
        func = adapter._convert_tool(schema)
        assert func.__name__ == "get_document_chunk"
        assert func.__annotations__.get("chunk_id") == int


# === Webhook Tool Tests ===

class TestWebhookTool:
    def test_creates_tool(self):
        tool = WebhookTool(
            name="notify_slack",
            description="Send message to Slack",
            url="https://hooks.slack.com/services/xxx",
            method="POST",
        )
        assert tool.name == "notify_slack"
        assert tool.method == "POST"

    def test_openai_schema(self):
        tool = WebhookTool(name="test", description="test", url="http://example.com")
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"

    def test_to_dict_from_dict(self):
        tool = WebhookTool(
            name="test_hook",
            description="Test webhook",
            url="http://example.com/hook",
            method="POST",
            headers={"X-Key": "abc"},
            body_template={"message": "{{data}}"},
        )
        data = tool.to_dict()
        restored = WebhookTool.from_dict(data)
        assert restored.name == "test_hook"
        assert restored.url == "http://example.com/hook"
        assert restored.method == "POST"

    @pytest.mark.asyncio
    async def test_execute_http_error(self):
        tool = WebhookTool(name="test", description="test", url="http://invalid-host:999")
        result = await tool.execute(data="hello")
        assert "error" in result.lower() or "Error" in result


# === Agent Config Tests ===

class TestAgentConfig:
    def test_create_config(self):
        cfg = AgentConfig(id="doc-agent", name="Document Agent", system_prompt="You are a doc helper")
        assert cfg.id == "doc-agent"
        assert cfg.temperature == 0.7

    def test_to_dict_from_dict(self):
        cfg = AgentConfig(
            id="test", name="Test Agent",
            system_prompt="You are helpful", model="qwen3.5",
            temperature=0.5, tools=["calculate", "search_knowledge"],
        )
        data = cfg.to_dict()
        restored = AgentConfig.from_dict(data)
        assert restored.id == "test"
        assert restored.model == "qwen3.5"
        assert restored.tools == ["calculate", "search_knowledge"]


class TestAgentStore:
    def test_add_and_get(self):
        store = AgentStore()
        cfg = AgentConfig(id="test", name="Test", system_prompt="Hello")
        store.add(cfg)
        assert store.get("test") is cfg

    def test_list_agents(self):
        store = AgentStore()
        store.add(AgentConfig(id="a1", name="A1", system_prompt=""))
        store.add(AgentConfig(id="a2", name="A2", system_prompt=""))
        assert len(store.list_agents()) == 2

    def test_remove(self):
        store = AgentStore()
        store.add(AgentConfig(id="x", name="X", system_prompt=""))
        assert store.remove("x") is True
        assert store.get("x") is None

    def test_contains_and_len(self):
        store = AgentStore()
        assert len(store) == 0
        store.add(AgentConfig(id="a", name="A", system_prompt=""))
        assert "a" in store
        assert len(store) == 1

    def test_get_unknown(self):
        store = AgentStore()
        assert store.get("nope") is None
