"""Self-Awareness Tools — agents that know who they are.

Provides tools for agents to introspect their own identity,
check their own health, and introduce themselves.
"""

import json
import logging

import httpx

from bifrost.core.agents import agent_store
from bifrost.tools.base import Tool

logger = logging.getLogger("bifrost.tools.self_awareness")


class SelfIntroduceTool(Tool):
    """Tool that returns the agent's self-introduction."""

    name = "self_introduce"
    description = "Introduce yourself — returns your identity, role, and capabilities."
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "The agent's own ID",
            },
        },
        "required": ["agent_id"],
    }

    async def execute(self, agent_id: str = "", **kwargs) -> str:
        """Generate self-introduction from stored config."""
        config = agent_store.get(agent_id)
        if not config:
            return f"I don't know who '{agent_id}' is."

        role = config.metadata.get("persona_role", "AI Assistant")
        lang = config.metadata.get("language", "en")

        if lang == "th":
            return (
                f"สวัสดีครับ ผมชื่อ {config.name} "
                f"ทำหน้าที่เป็น {role} "
                f"ใน Asgard AI Platform"
            )
        return (
            f"Hello, I'm {config.name}, "
            f"serving as {role} "
            f"in the Asgard AI Platform."
        )


class HealthCheckTool(Tool):
    """Tool that checks the health of a service."""

    name = "health_check"
    description = "Check if a service is healthy by hitting its health endpoint."
    parameters = {
        "type": "object",
        "properties": {
            "service_url": {
                "type": "string",
                "description": "The service health endpoint URL",
            },
        },
        "required": ["service_url"],
    }

    async def execute(self, service_url: str = "", **kwargs) -> str:
        """HTTP GET the health endpoint."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(service_url)
                if resp.status_code == 200:
                    return f"Healthy (OK 200) — {service_url}"
                return f"Unhealthy (HTTP {resp.status_code}) — {service_url}"
        except httpx.ConnectError:
            return f"Unhealthy (connection refused) — {service_url}"
        except Exception as e:
            return f"Unhealthy (error: {e}) — {service_url}"


class WhoAmITool(Tool):
    """Tool that returns the agent's identity card."""

    name = "who_am_i"
    description = "Returns your identity card with name, role, capabilities, and version."
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "The agent's own ID",
            },
        },
        "required": ["agent_id"],
    }

    async def execute(self, agent_id: str = "", **kwargs) -> str:
        """Return identity card as formatted string."""
        config = agent_store.get(agent_id)
        if not config:
            return f"Unknown agent: {agent_id}"

        card = {
            "agent_id": config.id,
            "name": config.name,
            "role": config.metadata.get("persona_role", "Unknown"),
            "language": config.metadata.get("language", "en"),
            "version": config.metadata.get("identity_version", 1),
            "tools": config.tools,
        }
        return json.dumps(card, ensure_ascii=False, indent=2)
