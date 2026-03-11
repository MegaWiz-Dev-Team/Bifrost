"""Delegate tool — allows an agent to delegate work to another agent.

This is the bridge between single-agent execution and multi-agent collaboration.
An agent can call this tool to hand off a sub-task to a different agent.
"""

from typing import Any
from bifrost.tools.base import Tool


class DelegateTool(Tool):
    """Delegate a task to another agent in the system."""

    name = "delegate_to_agent"
    description = (
        "Delegate a task to another specialized agent. "
        "Use this when the current task requires expertise from a different agent. "
        "Provide the agent_id and a clear task description."
    )
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "ID of the agent to delegate to",
            },
            "task": {
                "type": "string",
                "description": "Clear description of what the agent should do",
            },
        },
        "required": ["agent_id", "task"],
    }

    def __init__(self, executor_factory):
        """
        Args:
            executor_factory: async callable(agent_id, user_input) -> str
                A function that creates and runs an executor for the target agent.
        """
        self._executor_factory = executor_factory

    async def execute(self, **kwargs: Any) -> str:
        agent_id = kwargs.get("agent_id", "")
        task = kwargs.get("task", "")

        if not agent_id or not task:
            return "Error: both agent_id and task are required"

        try:
            result = await self._executor_factory(agent_id, task)
            return f"[Agent '{agent_id}' response]\n{result}"
        except Exception as e:
            return f"Delegation error: {e}"
