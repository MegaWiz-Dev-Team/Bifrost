"""Odin Orchestrator — backward-compatibility wrapper.

This module re-exports the OdinOrchestrator class from Sprint 3
with the same API surface (ask, team_standup, delegate_chain, get_permission).
Underneath, it delegates to the new Sprint 36 agents/odin/ module.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from bifrost.agents.odin.registry import SubAgentRegistry
from bifrost.core.service_agents import SERVICE_AGENTS

logger = logging.getLogger("bifrost.odin")


class Permission(Enum):
    """Permission levels for agent access."""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class OdinOrchestrator:
    """Legacy Odin orchestrator API (Sprint 3 compat).

    Provides: ask(), team_standup(), delegate_chain(), get_permission().
    """

    def __init__(self, max_chain_depth: int = 3):
        self.max_chain_depth = max_chain_depth
        self._registry = SubAgentRegistry()
        self._run_agent = self._default_run_agent
        self._check_agent = self._default_check_agent

        # All known agent IDs from service_agents
        self._agent_ids = [a.agent_id for a in SERVICE_AGENTS]

    async def _default_run_agent(self, agent_id: str, task: str) -> str:
        """Default agent runner (stub for testing)."""
        return f"[{agent_id}] completed: {task}"

    async def _default_check_agent(self, agent_id: str) -> dict:
        """Default health check (stub for testing)."""
        return {"agent_id": agent_id, "status": "healthy"}

    async def ask(self, question: str) -> dict:
        """Route a question to the most relevant agent.

        Returns dict with agent_id and response.
        """
        # Simple keyword routing for backward compat
        agent_id = self._route_question(question)
        response = await self._run_agent(agent_id, question)
        return {
            "agent_id": agent_id,
            "response": response,
        }

    def _route_question(self, question: str) -> str:
        """Simple keyword routing to find the best agent."""
        q_lower = question.lower()

        routing_map = {
            "huginn-agent": ["สแกน", "ช่องโหว่", "scan", "vulnerability", "security"],
            "mimir-agent": ["ค้นหา", "knowledge", "search", "ฐานความรู้"],
            "fenrir-agent": ["patient", "clinical", "ผู้ป่วย", "openemr"],
            "forseti-agent": ["test", "ทดสอบ", "qa"],
            "eir-agent": ["fhir", "medical record", "appointment"],
            "heimdall-agent": ["model", "llm", "gpu"],
            "muninn-agent": ["fix", "แก้ไข", "pr", "pull request"],
            "vardr-agent": ["container", "docker", "infrastructure"],
            "yggdrasil-agent": ["auth", "token", "login"],
            "ratatoskr-agent": ["browser", "scrape", "screenshot"],
        }

        for agent_id, keywords in routing_map.items():
            for keyword in keywords:
                if keyword in q_lower:
                    return agent_id

        return "bifrost-agent"  # Default

    async def team_standup(self) -> dict:
        """Poll all agents and return a team status report."""
        agents_report = []
        healthy_count = 0

        for agent_id in self._agent_ids:
            status = await self._check_agent(agent_id)
            agents_report.append(status)
            if status.get("status") == "healthy":
                healthy_count += 1

        return {
            "agents": agents_report,
            "healthy_count": healthy_count,
            "total_count": len(self._agent_ids),
        }

    async def delegate_chain(self, chain: list[dict]) -> dict:
        """Run a sequential delegation chain with results piping.

        Enforces max_chain_depth to prevent infinite loops.
        """
        truncated = len(chain) > self.max_chain_depth
        steps_to_run = chain[:self.max_chain_depth]

        steps_results = []
        context = ""

        for step in steps_to_run:
            agent_id = step.get("agent_id", "")
            task = step.get("task", "")
            if context:
                task = f"{task}\n\nContext from previous step:\n{context}"

            result = await self._run_agent(agent_id, task)
            steps_results.append({
                "agent_id": agent_id,
                "task": step.get("task", ""),
                "result": result,
            })
            context = result

        return {
            "steps": steps_results,
            "completed": len(steps_results),
            "truncated": truncated,
        }

    def get_permission(self, agent_id: str) -> Permission:
        """Get permission level for an agent.

        Odin itself has READ_WRITE, all others are READ_ONLY.
        """
        if agent_id == "odin":
            return Permission.READ_WRITE
        return Permission.READ_ONLY
