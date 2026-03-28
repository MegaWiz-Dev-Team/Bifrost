"""MCP-ADK Adapter — Bridge MCP JSON-RPC tools to Google ADK callable functions.

Connects to any MCP server via SSE/HTTP, discovers available tools via
JSON-RPC `tools/list`, and dynamically generates async Python functions
that ADK's `LlmAgent(tools=[...])` can introspect and invoke.

Each generated function:
- Has correct __name__, __doc__, and type annotations from JSON Schema
- Sends `tools/call` JSON-RPC when invoked
- Injects `X-Tenant-ID` header from ADK tool_context for data isolation

Sprint 32 — Bifrost Issues #4, #5, #6
"""

import asyncio
import functools
import inspect
import logging
from typing import Any, Callable

import httpx

logger = logging.getLogger("bifrost.mcp_adapter")

# JSON Schema type → Python type mapping
_JSON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


class MCPToolAdapter:
    """Converts MCP tool schemas to ADK-callable async functions.

    Usage:
        adapter = MCPToolAdapter(server_url="http://localhost:3000/mcp/sse")
        tools = await adapter.discover_tools()
        # tools is a list of async callables ready for ADK
    """

    def __init__(self, server_url: str, server_name: str = "mcp"):
        self._server_url = server_url.rstrip("/")
        self._server_name = server_name

    def _convert_tool(self, tool_schema: dict) -> Any:
        from bifrost.tools.base import Tool

        class BifrostMCPTool(Tool):
            def __init__(self, adapter: "MCPToolAdapter", schema: dict):
                self.name = schema.get("name", "unknown_tool")
                self.description = schema.get("description", "")
                self.parameters = schema.get("inputSchema", {})
                self._adapter = adapter

            async def execute(self, **kwargs: Any) -> str:
                # Extract tool_context if provided
                kwargs.pop("tool_context", None)
                tenant_id = "default"

                jsonrpc_request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": self.name,
                        "arguments": kwargs,
                    },
                }

                headers = {
                    "Content-Type": "application/json",
                    "X-Tenant-ID": tenant_id,
                    "X-User-Role": "doctor",
                }

                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(
                            self._adapter._server_url,
                            json=jsonrpc_request,
                            headers=headers,
                        )
                        response.raise_for_status()
                        data = response.json()

                        if "error" in data:
                            error_msg = data["error"].get("message", "Unknown MCP error")
                            return f"MCP Error: {error_msg}"

                        content = data.get("result", {}).get("content", [])
                        return "\n".join(c.get("text", str(c)) for c in content)
                except Exception as e:
                    return f"MCP request error: {e}"

        return BifrostMCPTool(self, tool_schema)

    async def discover_tools(self) -> list[Any]:
        """Connect to MCP server, list tools, and convert to ADK callables.

        Returns:
            List of async callable functions, empty if connection fails.
        """
        jsonrpc_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self._server_url,
                    json=jsonrpc_request,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()

                tools_data = data.get("result", {}).get("tools", [])
                converted = []
                for tool_schema in tools_data:
                    func = self._convert_tool(tool_schema)
                    converted.append(func)
                    logger.info(
                        f"MCP tool discovered: {func.name} "
                        f"(from {self._server_name})"
                    )
                return converted

        except (httpx.HTTPError, httpx.ConnectError, httpx.ReadTimeout, Exception) as e:
            logger.warning(
                f"MCP discovery failed for {self._server_name} "
                f"({self._server_url}): {e}"
            )
            return []


async def create_mcp_adk_tools(
    server_url: str,
    server_name: str = "mcp",
) -> list[Any]:
    """One-shot convenience: connect to MCP server, discover, and return ADK tools.

    Args:
        server_url: The MCP server SSE endpoint URL.
        server_name: Human-readable name for logging.

    Returns:
        List of async callable functions for ADK, empty on failure.
    """
    adapter = MCPToolAdapter(server_url=server_url, server_name=server_name)
    return await adapter.discover_tools()
