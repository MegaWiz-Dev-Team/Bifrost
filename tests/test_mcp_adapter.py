"""Tests for bifrost.core.mcp_adapter — MCP JSON-RPC → ADK callable bridge.

TDD Red Phase: All tests written before implementation.
Sprint 32 — Bifrost Issues #4, #5, #6
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ──────────────────────────────────────────────────────────────
# Sample MCP tools/list response fixtures
# ──────────────────────────────────────────────────────────────

SAMPLE_MCP_TOOLS_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "tools": [
            {
                "name": "search_knowledge",
                "description": "Search the knowledge base using hybrid RAG",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query in natural language",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results to return (default: 5)",
                        },
                        "mode": {
                            "type": "string",
                            "description": "Search mode: vector, tree, or hybrid",
                            "enum": ["vector", "tree", "hybrid"],
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "list_sources",
                "description": "List all knowledge sources",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "get_document_chunk",
                "description": "Get a specific document chunk by ID",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {
                            "type": "integer",
                            "description": "The chunk ID to retrieve",
                        },
                    },
                    "required": ["chunk_id"],
                },
            },
        ]
    },
}

SAMPLE_MCP_TOOL_CALL_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 2,
    "result": {
        "content": [
            {
                "type": "text",
                "text": "[1] (score: 0.95) [doc1.pdf]\nRelevant knowledge chunk text here.",
            }
        ]
    },
}


# ──────────────────────────────────────────────────────────────
# Test: Schema conversion to ADK callable
# ──────────────────────────────────────────────────────────────


class TestMCPToolSchemaConversion:
    """Test converting MCP tool JSON Schema to ADK-callable functions."""

    def test_convert_creates_callable_with_correct_name(self):
        """Generated function should have __name__ matching the MCP tool name."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://localhost:3000/mcp/sse")
        tool_schema = SAMPLE_MCP_TOOLS_RESPONSE["result"]["tools"][0]

        func = adapter._convert_tool(tool_schema)

        assert callable(func)
        assert func.__name__ == "search_knowledge"

    def test_convert_creates_callable_with_correct_docstring(self):
        """Generated function's docstring should match MCP tool description."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://localhost:3000/mcp/sse")
        tool_schema = SAMPLE_MCP_TOOLS_RESPONSE["result"]["tools"][0]

        func = adapter._convert_tool(tool_schema)

        assert func.__doc__ == "Search the knowledge base using hybrid RAG"

    def test_convert_creates_callable_with_annotations(self):
        """Generated function should have type annotations from JSON Schema."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://localhost:3000/mcp/sse")
        tool_schema = SAMPLE_MCP_TOOLS_RESPONSE["result"]["tools"][0]

        func = adapter._convert_tool(tool_schema)

        annotations = func.__annotations__
        # query is required string
        assert "query" in annotations
        assert annotations["query"] == str
        # limit is optional integer
        assert "limit" in annotations
        # mode is optional string
        assert "mode" in annotations

    def test_convert_tool_with_no_parameters(self):
        """Tool with empty properties should still create a valid callable."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://localhost:3000/mcp/sse")
        tool_schema = SAMPLE_MCP_TOOLS_RESPONSE["result"]["tools"][1]  # list_sources

        func = adapter._convert_tool(tool_schema)

        assert callable(func)
        assert func.__name__ == "list_sources"

    def test_convert_preserves_integer_type(self):
        """Integer types in JSON Schema should map to Python int."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://localhost:3000/mcp/sse")
        tool_schema = SAMPLE_MCP_TOOLS_RESPONSE["result"]["tools"][2]  # get_document_chunk

        func = adapter._convert_tool(tool_schema)

        assert func.__annotations__.get("chunk_id") == int


# ──────────────────────────────────────────────────────────────
# Test: Auto-discover tools from MCP server
# ──────────────────────────────────────────────────────────────


class TestAutoDiscoverTools:
    """Test connecting to MCP server and discovering tools."""

    @pytest.mark.asyncio
    async def test_discover_returns_correct_number_of_tools(self):
        """Should discover all tools reported by the MCP server."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://mock:3000/mcp/sse")

        # Mock the HTTP call to tools/list
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_MCP_TOOLS_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = client_instance

            tools = await adapter.discover_tools()

        assert len(tools) == 3

    @pytest.mark.asyncio
    async def test_discover_tools_are_all_callable(self):
        """All discovered tools should be async callable functions."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://mock:3000/mcp/sse")

        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_MCP_TOOLS_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = client_instance

            tools = await adapter.discover_tools()

        for tool in tools:
            assert callable(tool)
            assert asyncio.iscoroutinefunction(tool)

    @pytest.mark.asyncio
    async def test_discover_tool_names_match(self):
        """Discovered tool function names should match MCP tool names."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://mock:3000/mcp/sse")

        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_MCP_TOOLS_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = client_instance

            tools = await adapter.discover_tools()

        tool_names = {t.__name__ for t in tools}
        assert tool_names == {"search_knowledge", "list_sources", "get_document_chunk"}


# ──────────────────────────────────────────────────────────────
# Test: Tool call sends correct JSON-RPC
# ──────────────────────────────────────────────────────────────


class TestToolCallJsonRpc:
    """Test that calling a generated tool sends correct JSON-RPC to MCP."""

    @pytest.mark.asyncio
    async def test_tool_call_sends_jsonrpc_with_arguments(self):
        """Calling a tool function should POST JSON-RPC tools/call with args."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://mock:3000/mcp/sse")
        tool_schema = SAMPLE_MCP_TOOLS_RESPONSE["result"]["tools"][0]
        func = adapter._convert_tool(tool_schema)

        # Mock the HTTP client for the actual tool call
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_MCP_TOOL_CALL_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = client_instance

            result = await func(query="what is diabetes?", limit=3)

        # Verify the JSON-RPC request
        call_args = client_instance.post.call_args
        request_body = call_args[1].get("json") or call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["json"]
        assert request_body["method"] == "tools/call"
        assert request_body["params"]["name"] == "search_knowledge"
        assert request_body["params"]["arguments"] == {"query": "what is diabetes?", "limit": 3}

    @pytest.mark.asyncio
    async def test_tool_call_returns_text_content(self):
        """Tool call result should extract text from MCP content array."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://mock:3000/mcp/sse")
        tool_schema = SAMPLE_MCP_TOOLS_RESPONSE["result"]["tools"][0]
        func = adapter._convert_tool(tool_schema)

        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_MCP_TOOL_CALL_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = client_instance

            result = await func(query="test")

        assert "Relevant knowledge chunk text here" in result

    @pytest.mark.asyncio
    async def test_tool_call_handles_mcp_error(self):
        """When MCP returns an error, the tool should return error message."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://mock:3000/mcp/sse")
        tool_schema = SAMPLE_MCP_TOOLS_RESPONSE["result"]["tools"][0]
        func = adapter._convert_tool(tool_schema)

        error_response = {
            "jsonrpc": "2.0",
            "id": 2,
            "error": {"code": -32603, "message": "Internal error: DB connection failed"},
        }
        mock_response = MagicMock()
        mock_response.json.return_value = error_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = client_instance

            result = await func(query="test")

        assert "error" in result.lower() or "Error" in result


# ──────────────────────────────────────────────────────────────
# Test: Tenant ID injection
# ──────────────────────────────────────────────────────────────


class TestTenantIdInjection:
    """Test dynamic X-Tenant-ID injection via ADK session context."""

    @pytest.mark.asyncio
    async def test_tenant_id_injected_from_tool_context(self):
        """When tool_context has tenant_id, it should be sent as X-Tenant-ID header."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://mock:3000/mcp/sse")
        tool_schema = SAMPLE_MCP_TOOLS_RESPONSE["result"]["tools"][0]
        func = adapter._convert_tool(tool_schema)

        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_MCP_TOOL_CALL_RESPONSE
        mock_response.raise_for_status = MagicMock()

        # Simulate ADK tool_context with tenant_id
        mock_tool_context = MagicMock()
        mock_tool_context.state = {"tenant_id": "megacare-clinic-01"}

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = client_instance

            result = await func(query="test", tool_context=mock_tool_context)

        # Verify X-Tenant-ID header was sent
        call_kwargs = client_instance.post.call_args[1]
        headers = call_kwargs.get("headers", {})
        assert headers.get("X-Tenant-ID") == "megacare-clinic-01"

    @pytest.mark.asyncio
    async def test_tenant_id_defaults_when_no_context(self):
        """When no tool_context is provided, X-Tenant-ID should default to 'default'."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://mock:3000/mcp/sse")
        tool_schema = SAMPLE_MCP_TOOLS_RESPONSE["result"]["tools"][1]  # list_sources
        func = adapter._convert_tool(tool_schema)

        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_MCP_TOOL_CALL_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = client_instance

            result = await func()

        call_kwargs = client_instance.post.call_args[1]
        headers = call_kwargs.get("headers", {})
        assert headers.get("X-Tenant-ID") == "default"

    @pytest.mark.asyncio
    async def test_tenant_id_defaults_when_state_missing_key(self):
        """When tool_context.state exists but has no tenant_id, should default."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://mock:3000/mcp/sse")
        tool_schema = SAMPLE_MCP_TOOLS_RESPONSE["result"]["tools"][0]
        func = adapter._convert_tool(tool_schema)

        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_MCP_TOOL_CALL_RESPONSE
        mock_response.raise_for_status = MagicMock()

        mock_tool_context = MagicMock()
        mock_tool_context.state = {"user_name": "admin"}  # no tenant_id

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = client_instance

            result = await func(query="test", tool_context=mock_tool_context)

        call_kwargs = client_instance.post.call_args[1]
        headers = call_kwargs.get("headers", {})
        assert headers.get("X-Tenant-ID") == "default"


# ──────────────────────────────────────────────────────────────
# Test: Connection failure graceful handling
# ──────────────────────────────────────────────────────────────


class TestConnectionFailure:
    """Test graceful handling when MCP server is unreachable."""

    @pytest.mark.asyncio
    async def test_discover_returns_empty_on_connection_error(self):
        """When MCP server is unreachable, discover_tools() should return empty list."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://unreachable:9999/mcp/sse")

        import httpx

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.side_effect = httpx.ConnectError("Connection refused")
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = client_instance

            tools = await adapter.discover_tools()

        assert tools == []

    @pytest.mark.asyncio
    async def test_discover_returns_empty_on_timeout(self):
        """When MCP server times out, discover_tools() should return empty list."""
        from bifrost.core.mcp_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(server_url="http://slow:3000/mcp/sse")

        import httpx

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.side_effect = httpx.ReadTimeout("Timed out")
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = client_instance

            tools = await adapter.discover_tools()

        assert tools == []


# ──────────────────────────────────────────────────────────────
# Test: create_mcp_adk_tools convenience function
# ──────────────────────────────────────────────────────────────


class TestCreateMcpAdkTools:
    """Test the one-shot convenience function."""

    @pytest.mark.asyncio
    async def test_create_mcp_adk_tools_returns_callables(self):
        """create_mcp_adk_tools() should return list of async callables."""
        from bifrost.core.mcp_adapter import create_mcp_adk_tools

        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_MCP_TOOLS_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = client_instance

            tools = await create_mcp_adk_tools("http://mock:3000/mcp/sse", "mimir")

        assert len(tools) == 3
        assert all(callable(t) for t in tools)

    @pytest.mark.asyncio
    async def test_create_mcp_adk_tools_returns_empty_on_failure(self):
        """create_mcp_adk_tools() should return empty list on connection failure."""
        from bifrost.core.mcp_adapter import create_mcp_adk_tools

        import httpx

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.side_effect = httpx.ConnectError("refused")
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = client_instance

            tools = await create_mcp_adk_tools("http://dead:3000/mcp/sse", "test")

        assert tools == []
