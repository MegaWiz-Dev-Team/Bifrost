"""Agent configuration — define and manage agent configs."""

import json
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("bifrost.agents")


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    id: str
    name: str
    system_prompt: str
    model: str | None = None
    temperature: float = 0.7
    tools: list[str] = field(default_factory=list)  # tool names to enable
    max_iterations: int = 10
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "temperature": self.temperature,
            "tools": self.tools,
            "max_iterations": self.max_iterations,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentConfig":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", data.get("id", "")),
            system_prompt=data.get("system_prompt", "You are a helpful assistant."),
            model=data.get("model"),
            temperature=data.get("temperature", 0.7),
            tools=data.get("tools", []),
            max_iterations=data.get("max_iterations", 10),
            metadata=data.get("metadata", {}),
        )


class AgentStore:
    """Manages agent configurations. Supports local configs and Mimir sync."""

    def __init__(self):
        self._agents: dict[str, AgentConfig] = {}

    def add(self, config: AgentConfig) -> None:
        """Add or update an agent config."""
        self._agents[config.id] = config

    def get(self, agent_id: str) -> AgentConfig | None:
        """Get an agent config by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentConfig]:
        """List all configured agents."""
        return list(self._agents.values())

    def remove(self, agent_id: str) -> bool:
        """Remove an agent config."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False

    async def sync_from_mimir(self, mimir_url: str, api_key: str = "", tenant_id: str = "default") -> int:
        """Sync agent configs from Mimir's API.

        Returns the number of agents synced.
        """
        headers = {"X-Tenant-ID": tenant_id}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{mimir_url}/api/agents",
                    headers=headers,
                )
                response.raise_for_status()
                agents_data = response.json()

                count = 0
                for agent_data in agents_data:
                    config = AgentConfig(
                        id=str(agent_data.get("id", "")),
                        name=agent_data.get("name", ""),
                        system_prompt=agent_data.get("system_prompt", "You are a helpful assistant."),
                        model=agent_data.get("model"),
                        temperature=agent_data.get("temperature", 0.7),
                        tools=agent_data.get("tools", []),
                        max_iterations=agent_data.get("max_iterations", 10),
                        metadata={"source": "mimir", "mimir_id": agent_data.get("id")},
                    )
                    self._agents[config.id] = config
                    count += 1
                    logger.info(f"Agent synced from Mimir: {config.name} ({config.id})")

                return count

        except httpx.HTTPError as e:
            logger.warning(f"Failed to sync agents from Mimir: {e}")
            return 0

    def save_to_file(self, path: str) -> None:
        """Save all agent configs to a JSON file."""
        data = [config.to_dict() for config in self._agents.values()]
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {len(data)} agents to {path}")

    def load_from_file(self, path: str) -> int:
        """Load agent configs from a JSON file. Returns count loaded."""
        try:
            with open(path) as f:
                data = json.load(f)
            count = 0
            for item in data:
                config = AgentConfig.from_dict(item)
                self._agents[config.id] = config
                count += 1
            logger.info(f"Loaded {count} agents from {path}")
            return count
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load agents from {path}: {e}")
            return 0

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._agents


# Singleton
agent_store = AgentStore()
