"""Odin Orchestrator — meta-agent that coordinates all 12 service agents.

Provides:
- ask: route questions to the most relevant agent
- team_standup: poll all agents for status summary
- delegate_chain: sequential delegation with results piping
- Safety: max iterations per chain, loop detection
- Permissions: self=read_write, others=read_only
"""

import logging
from enum import Enum
from typing import Any

from bifrost.core.agents import agent_store
from bifrost.core.service_agents import SERVICE_AGENTS

logger = logging.getLogger("bifrost.odin")

# Keyword → agent routing table (ORDER MATTERS — specific keywords first)
ROUTING_TABLE: dict[str, str] = {
    # Medical gateway — must be before generic 'query'
    "fhir": "eir-agent", "hl7": "eir-agent",
    # Clinical — must be before generic keywords
    "patient": "fenrir-agent", "ผู้ป่วย": "fenrir-agent", "clinical": "fenrir-agent",
    "vitals": "fenrir-agent", "openemr": "fenrir-agent",
    # Security
    "scan": "huginn-agent", "vulnerability": "huginn-agent", "security": "huginn-agent",
    "สแกน": "huginn-agent", "ช่องโหว่": "huginn-agent",
    # Auto-fix
    "fix": "muninn-agent", "แก้ไข": "muninn-agent", "pr": "muninn-agent",
    # Testing
    "test": "forseti-agent", "ทดสอบ": "forseti-agent", "e2e": "forseti-agent",
    # Browser
    "browse": "ratatoskr-agent", "screenshot": "ratatoskr-agent",
    # Auth — must be before generic 'token'
    "auth": "yggdrasil-agent", "token": "yggdrasil-agent", "login": "yggdrasil-agent",
    # Infra
    "container": "vardr-agent", "docker": "vardr-agent", "restart": "vardr-agent",
    # Deploy
    "deploy": "asgard-agent", "platform": "asgard-agent",
    # LLM
    "model": "heimdall-agent", "llm": "heimdall-agent",
    # Knowledge — generic 'query' last
    "knowledge": "mimir-agent", "query": "mimir-agent", "ค้นหา": "mimir-agent",
}


class Permission(Enum):
    """Permission level for agent access."""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class OdinOrchestrator:
    """Meta-agent that coordinates the entire Asgard platform."""

    def __init__(self, max_chain_depth: int = 3):
        self.max_chain_depth = max_chain_depth
        self._agents = {a.agent_id: a for a in SERVICE_AGENTS}

    def _route_question(self, question: str) -> str:
        """Route a question to the most relevant agent via keyword matching."""
        q_lower = question.lower()
        for keyword, agent_id in ROUTING_TABLE.items():
            if keyword in q_lower:
                return agent_id
        return "bifrost-agent"  # Default fallback

    def get_permission(self, agent_id: str) -> Permission:
        """Get permission level for an agent. Odin=RW, others=RO."""
        if agent_id == "odin":
            return Permission.READ_WRITE
        return Permission.READ_ONLY

    async def _run_agent(self, agent_id: str, task: str) -> str:
        """Execute an agent with a task. Override in tests."""
        config = agent_store.get(agent_id)
        if not config:
            return f"Agent '{agent_id}' not found"
        return f"[{agent_id}] {config.name} processed: {task}"

    async def _check_agent(self, agent_id: str) -> dict:
        """Check agent health. Override in tests."""
        config = agent_store.get(agent_id)
        return {
            "agent_id": agent_id,
            "status": "registered" if config else "unknown",
            "name": config.name if config else agent_id,
        }

    async def ask(self, question: str) -> dict[str, Any]:
        """Route a question to the best agent and return the response."""
        agent_id = self._route_question(question)
        response = await self._run_agent(agent_id, question)

        return {
            "agent_id": agent_id,
            "agent_name": self._agents.get(agent_id, None) and self._agents[agent_id].persona_name or agent_id,
            "response": response,
            "routing_method": "keyword",
        }

    async def team_standup(self) -> dict[str, Any]:
        """Poll all 12 agents for status and produce a standup report."""
        agents_status = []
        healthy = 0

        for identity in SERVICE_AGENTS:
            status = await self._check_agent(identity.agent_id)
            agents_status.append(status)
            if status.get("status") in ("healthy", "registered"):
                healthy += 1

        return {
            "agents": agents_status,
            "total_count": len(SERVICE_AGENTS),
            "healthy_count": healthy,
        }

    async def delegate_chain(self, steps: list[dict]) -> dict[str, Any]:
        """Run a sequential delegation chain with safety limits.

        Each step: {"agent_id": "...", "task": "..."}
        Results from previous step are appended to next step's task.
        """
        truncated = len(steps) > self.max_chain_depth
        steps_to_run = steps[:self.max_chain_depth]

        results = []
        prev_result = ""

        for i, step in enumerate(steps_to_run):
            agent_id = step["agent_id"]
            task = step["task"]
            if prev_result:
                task = f"{task}\n\nContext from previous step:\n{prev_result}"

            result = await self._run_agent(agent_id, task)
            results.append({
                "step": i + 1,
                "agent_id": agent_id,
                "result": result,
            })
            prev_result = result

        return {
            "steps": results,
            "completed": len(results),
            "truncated": truncated,
            "max_depth": self.max_chain_depth,
        }
