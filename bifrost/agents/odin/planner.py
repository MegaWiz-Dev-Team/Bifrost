"""Odin Planner — LLM-based task decomposition.

Analyzes user requests and decomposes them into structured sub-tasks
with assigned agent types and dependency ordering.
"""

from __future__ import annotations

import json
import logging

from bifrost.agents.odin.models import SubTask, TaskPlan

logger = logging.getLogger("bifrost.odin.planner")

DECOMPOSITION_PROMPT = """You are a task planner for a multi-agent AI system called Odin.
Given a user request, decompose it into sub-tasks that can be handled by specialized agents.

Available agent types:
- "general": General-purpose assistant for simple Q&A and conversations
- "researcher": Information gathering, knowledge search, cross-referencing sources
- "coder": Writing, analyzing, and debugging code
- "medical": Medical information, clinical workflows (HIPAA-compliant)
- "devops": Deployment, infrastructure, security scanning, monitoring

Rules:
- Maximum 6 sub-tasks per request
- Each sub-task should be atomic and actionable
- Use dependency ordering when tasks must be sequential
- For simple questions, use a single "general" sub-task
- Output ONLY a JSON array, no other text

Output format:
[
  {{"id": "t1", "description": "...", "agent_type": "...", "depends_on": []}},
  {{"id": "t2", "description": "...", "agent_type": "...", "depends_on": ["t1"]}}
]

User request: {request}"""


class OdinPlanner:
    """LLM-based task decomposition planner.

    Takes a user request and produces a TaskPlan with ordered sub-tasks.
    Falls back to a single general sub-task if decomposition fails.
    """

    def __init__(self, heimdall, model: str | None = None):
        self.heimdall = heimdall
        self.model = model

    async def decompose(self, request: str) -> TaskPlan:
        """Decompose a user request into a TaskPlan with sub-tasks.

        Args:
            request: Natural language user request.

        Returns:
            TaskPlan with ordered sub-tasks.
        """
        try:
            prompt = DECOMPOSITION_PROMPT.format(request=request)

            response = await self.heimdall.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.2,  # Low temp for structured output
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "[]")
            sub_tasks = self._parse_plan(content, request)

            return TaskPlan(
                original_request=request,
                sub_tasks=sub_tasks,
            )

        except Exception as e:
            logger.warning(f"Task decomposition failed: {e}")
            return self._fallback_plan(request)

    def _parse_plan(self, content: str, request: str) -> list[SubTask]:
        """Parse LLM output into a list of SubTask objects."""
        try:
            # Extract JSON array from response
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                data = json.loads(content[start:end])
            else:
                data = json.loads(content)

            if not isinstance(data, list) or len(data) == 0:
                return self._fallback_plan(request).sub_tasks

            sub_tasks = []
            for i, item in enumerate(data[:6]):  # Max 6 sub-tasks
                sub_tasks.append(SubTask(
                    id=item.get("id", f"t{i+1}"),
                    description=item.get("description", request),
                    agent_type=item.get("agent_type", "general"),
                    depends_on=item.get("depends_on", []),
                ))

            return sub_tasks

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Plan parsing failed: {e}")
            return self._fallback_plan(request).sub_tasks

    def _fallback_plan(self, request: str) -> TaskPlan:
        """Create a fallback plan with a single general sub-task."""
        return TaskPlan(
            original_request=request,
            sub_tasks=[
                SubTask(
                    id="t1",
                    description=request,
                    agent_type="general",
                ),
            ],
        )
