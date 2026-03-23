"""Odin data models — SubTask, TaskPlan, SubAgentResult, OdinResult.

Structured types for the multi-agent orchestration pipeline.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class SubTask:
    """A single decomposed sub-task assigned to a sub-agent.

    Attributes:
        id: Unique identifier for this sub-task.
        description: Natural language description of what to do.
        agent_type: Type of sub-agent to handle this (general, researcher, coder, medical, devops).
        depends_on: List of sub-task IDs this task depends on.
        status: Current status (pending, running, completed, failed).
        result: Output from the sub-agent after execution.
        duration_ms: Execution duration in milliseconds.
    """
    id: str
    description: str
    agent_type: str
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"
    result: str = ""
    duration_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "agent_type": self.agent_type,
            "depends_on": self.depends_on,
            "status": self.status,
            "result": self.result[:500] if self.result else "",
            "duration_ms": self.duration_ms,
        }


@dataclass
class TaskPlan:
    """A decomposed execution plan with ordered sub-tasks.

    Attributes:
        original_request: The user's original request.
        sub_tasks: Ordered list of sub-tasks.
        created_at: Timestamp when the plan was created.
    """
    original_request: str
    sub_tasks: list[SubTask] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def sub_task_count(self) -> int:
        return len(self.sub_tasks)

    def to_dict(self) -> dict:
        return {
            "original_request": self.original_request,
            "sub_tasks": [t.to_dict() for t in self.sub_tasks],
            "sub_task_count": self.sub_task_count,
            "created_at": self.created_at,
        }


@dataclass
class SubAgentResult:
    """Result from a single sub-agent execution.

    Attributes:
        sub_task_id: ID of the sub-task this result belongs to.
        agent_type: Type of agent that produced this result.
        output: The agent's text output.
        success: Whether the execution succeeded.
        duration_ms: Execution duration in milliseconds.
        error: Error message if failed.
    """
    sub_task_id: str
    agent_type: str
    output: str = ""
    success: bool = True
    duration_ms: float = 0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "sub_task_id": self.sub_task_id,
            "agent_type": self.agent_type,
            "output": self.output[:500] if self.output else "",
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


@dataclass
class OdinResult:
    """Final result from the Odin orchestration pipeline.

    Attributes:
        output: Synthesized final answer.
        plan: The execution plan used.
        sub_results: Individual sub-agent results.
        total_duration_ms: Total orchestration time.
        agents_used: List of agent types involved.
    """
    output: str
    plan: TaskPlan
    sub_results: list[SubAgentResult] = field(default_factory=list)
    total_duration_ms: float = 0
    agents_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "output": self.output,
            "plan": self.plan.to_dict(),
            "sub_results": [r.to_dict() for r in self.sub_results],
            "total_duration_ms": self.total_duration_ms,
            "agents_used": self.agents_used,
        }
