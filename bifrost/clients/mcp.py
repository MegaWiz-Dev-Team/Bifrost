"""MCP (Model Context Protocol) client — connect to MCP tool servers.

Supports stdio and SSE transports. Discovers tools from MCP servers
and auto-registers them in Bifrost's ToolRegistry.
"""

import json
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from bifrost.tools.base import Tool

logger = logging.getLogger("bifrost.mcp")


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server connection."""
    name: str
    transport: str  # "stdio" or "sse"
    # stdio
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # sse
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class MCPTool(Tool):
    """A tool discovered from an MCP server."""

    def __init__(self, name: str, description: str, parameters: dict, server: "MCPClient"):
        self.name = name
        self.description = description
        self.parameters = parameters
        self._server = server

    async def execute(self, **kwargs: Any) -> str:
        return await self._server.call_tool(self.name, kwargs)


class MCPClient:
    """Client for connecting to a single MCP server."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._request_id = 0
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Establish connection to the MCP server."""
        if self.config.transport == "stdio":
            await self._connect_stdio()
        elif self.config.transport == "sse":
            await self._connect_sse()
        else:
            raise ValueError(f"Unknown transport: {self.config.transport}")

    async def _connect_stdio(self) -> None:
        """Connect via stdio (spawn subprocess)."""
        if not self.config.command:
            raise ValueError("stdio transport requires 'command'")

        self._process = await asyncio.create_subprocess_exec(
            self.config.command, *self.config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**dict(__import__("os").environ), **self.config.env} if self.config.env else None,
        )

        # Send initialize request
        response = await self._send_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "bifrost", "version": "0.1.0"},
        })

        if response and "result" in response:
            # Send initialized notification
            await self._send_notification("notifications/initialized", {})
            self._connected = True
            logger.info(f"MCP stdio connected: {self.config.name}")

    async def _connect_sse(self) -> None:
        """Connect via SSE (HTTP)."""
        if not self.config.url:
            raise ValueError("SSE transport requires 'url'")

        self._http_client = httpx.AsyncClient(
            base_url=self.config.url,
            headers=self.config.headers,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        self._connected = True
        logger.info(f"MCP SSE connected: {self.config.name} → {self.config.url}")

    async def _send_jsonrpc(self, method: str, params: dict) -> dict | None:
        """Send a JSON-RPC request via stdio."""
        if not self._process or not self._process.stdin or not self._process.stdout:
            return None

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        message = json.dumps(request)
        self._process.stdin.write(f"{message}\n".encode())
        await self._process.stdin.drain()

        # Read response
        try:
            line = await asyncio.wait_for(self._process.stdout.readline(), timeout=30.0)
            if line:
                return json.loads(line.decode().strip())
        except asyncio.TimeoutError:
            logger.warning(f"MCP request timeout: {method}")
        except json.JSONDecodeError:
            pass
        return None

    async def _send_notification(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or not self._process.stdin:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        message = json.dumps(notification)
        self._process.stdin.write(f"{message}\n".encode())
        await self._process.stdin.drain()

    async def list_tools(self) -> list[dict]:
        """Discover available tools from the MCP server."""
        if self.config.transport == "stdio":
            response = await self._send_jsonrpc("tools/list", {})
            if response and "result" in response:
                return response["result"].get("tools", [])
        elif self.config.transport == "sse" and self._http_client:
            try:
                resp = await self._http_client.post("/mcp", json={
                    "jsonrpc": "2.0", "id": 1,
                    "method": "tools/list", "params": {},
                })
                data = resp.json()
                return data.get("result", {}).get("tools", [])
            except httpx.HTTPError as e:
                logger.warning(f"MCP list_tools failed: {e}")
        return []

    async def call_tool(self, name: str, arguments: dict) -> str:
        """Execute a tool on the MCP server."""
        if self.config.transport == "stdio":
            response = await self._send_jsonrpc("tools/call", {
                "name": name, "arguments": arguments,
            })
            if response and "result" in response:
                content = response["result"].get("content", [])
                return "\n".join(c.get("text", str(c)) for c in content)
            elif response and "error" in response:
                return f"MCP Error: {response['error'].get('message', 'Unknown')}"
        elif self.config.transport == "sse" and self._http_client:
            try:
                resp = await self._http_client.post("/mcp", json={
                    "jsonrpc": "2.0", "id": 1,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                })
                data = resp.json()
                if "result" in data:
                    content = data["result"].get("content", [])
                    return "\n".join(c.get("text", str(c)) for c in content)
                elif "error" in data:
                    return f"MCP Error: {data['error'].get('message', 'Unknown')}"
            except httpx.HTTPError as e:
                return f"MCP request failed: {e}"
        return "MCP Error: not connected"

    async def discover_and_register(self, registry) -> int:
        """Discover tools from MCP server and register them in Bifrost.

        Returns the number of tools registered.
        """
        tools = await self.list_tools()
        count = 0
        for tool_def in tools:
            mcp_tool = MCPTool(
                name=tool_def.get("name", ""),
                description=tool_def.get("description", ""),
                parameters=tool_def.get("inputSchema", {"type": "object", "properties": {}}),
                server=self,
            )
            registry.register(mcp_tool)
            count += 1
            logger.info(f"MCP tool registered: {mcp_tool.name} (from {self.config.name})")
        return count

    async def disconnect(self) -> None:
        """Close the connection."""
        if self._process:
            self._process.terminate()
            await self._process.wait()
            self._process = None
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._connected = False


class MCPManager:
    """Manages multiple MCP server connections."""

    def __init__(self):
        self._clients: dict[str, MCPClient] = {}

    async def add_server(self, config: MCPServerConfig) -> MCPClient:
        """Add and connect to an MCP server."""
        client = MCPClient(config)
        await client.connect()
        self._clients[config.name] = client
        return client

    def get_client(self, name: str) -> MCPClient | None:
        return self._clients.get(name)

    async def discover_all(self, registry) -> int:
        """Discover and register tools from all connected MCP servers."""
        total = 0
        for client in self._clients.values():
            if client.is_connected:
                count = await client.discover_and_register(registry)
                total += count
        return total

    async def disconnect_all(self) -> None:
        """Disconnect all MCP servers."""
        for client in self._clients.values():
            await client.disconnect()
        self._clients.clear()

    @property
    def servers(self) -> list[str]:
        return list(self._clients.keys())
