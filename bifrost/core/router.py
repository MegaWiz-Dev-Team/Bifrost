"""Agent Router — multi-agent delegation and handoff.

Routes user inputs to the most appropriate agent based on configured
routing rules. Supports pattern matching and agent-to-agent delegation.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("bifrost.router")


@dataclass
class AgentRoute:
    """A routing rule that maps patterns to target agents."""
    pattern: str  # regex pattern to match user input
    target_agent_id: str  # agent to route to
    priority: int = 0  # higher = checked first
    description: str = ""

    def matches(self, text: str) -> bool:
        """Check if the input text matches this route's pattern."""
        try:
            return bool(re.search(self.pattern, text, re.IGNORECASE))
        except re.error:
            return False

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "target_agent_id": self.target_agent_id,
            "priority": self.priority,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentRoute":
        return cls(
            pattern=data["pattern"],
            target_agent_id=data["target_agent_id"],
            priority=data.get("priority", 0),
            description=data.get("description", ""),
        )


class AgentRouter:
    """Routes inputs to the appropriate agent.

    Routing strategies:
    1. Pattern matching — regex against user input
    2. Default fallback — uses "default" agent if no match
    """

    def __init__(self):
        self._routes: list[AgentRoute] = []
        self._default_agent_id: str = "default"

    def add_route(self, route: AgentRoute) -> None:
        """Add a routing rule."""
        self._routes.append(route)
        # Keep sorted by priority (descending)
        self._routes.sort(key=lambda r: r.priority, reverse=True)

    def remove_route(self, pattern: str) -> bool:
        """Remove a route by pattern."""
        before = len(self._routes)
        self._routes = [r for r in self._routes if r.pattern != pattern]
        return len(self._routes) < before

    def set_default(self, agent_id: str) -> None:
        """Set the default fallback agent."""
        self._default_agent_id = agent_id

    def route(self, user_input: str) -> str:
        """Determine which agent should handle this input.

        Returns the target agent_id.
        """
        for rule in self._routes:
            if rule.matches(user_input):
                logger.info(f"Routed to '{rule.target_agent_id}' via pattern '{rule.pattern}'")
                return rule.target_agent_id

        logger.info(f"No route matched, using default: '{self._default_agent_id}'")
        return self._default_agent_id

    def list_routes(self) -> list[AgentRoute]:
        """List all configured routes."""
        return list(self._routes)

    @property
    def default_agent_id(self) -> str:
        return self._default_agent_id

    def __len__(self) -> int:
        return len(self._routes)


# Singleton
router = AgentRouter()
