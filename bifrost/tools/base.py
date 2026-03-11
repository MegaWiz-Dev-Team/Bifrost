"""Base class for all Bifrost tools."""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Abstract base class for tools that agents can call."""

    name: str
    description: str
    parameters: dict  # JSON Schema

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool with given arguments. Returns result as string."""
        ...

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
