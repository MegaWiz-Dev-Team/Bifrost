"""Plan-and-Execute strategy — decompose complex tasks into sub-steps.

Instead of a single ReAct loop, this strategy:
1. Plans: LLM creates a step-by-step plan
2. Executes: Each step is executed individually  
3. Revises: Plan can be adjusted based on intermediate results
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from bifrost.clients.heimdall import HeimdallClient
from bifrost.tools.registry import ToolRegistry
from bifrost.core.executor import AgentExecutor, ExecutionResult

logger = logging.getLogger("bifrost.planner")


PLANNER_PROMPT = """You are a task planner. Given a complex user request, break it down into clear, sequential sub-tasks.

Output a JSON array of steps, each with:
- "step": step number
- "task": clear description of what to do
- "depends_on": list of step numbers this depends on (empty if independent)

Rules:
- Keep steps atomic and actionable
- Order steps logically (dependencies first)
- Maximum 8 steps
- Output ONLY the JSON array, no other text

User request: {user_input}"""


REVISION_PROMPT = """You are revising a plan based on execution results so far.

Original plan:
{original_plan}

Completed steps and their results:
{completed_steps}

Remaining steps:
{remaining_steps}

Based on the results so far, should the remaining steps be modified? 
Output the revised remaining steps as a JSON array (same format as original).
If no changes needed, output the remaining steps as-is.
Output ONLY the JSON array."""


@dataclass
class PlanStep:
    """A single step in an execution plan."""
    step: int
    task: str
    depends_on: list[int] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed
    result: str = ""

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "task": self.task,
            "depends_on": self.depends_on,
            "status": self.status,
            "result": self.result[:500] if self.result else "",
        }


@dataclass
class PlanResult:
    """Result of a plan-and-execute run."""
    output: str
    steps: list[PlanStep]
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    revised: bool = False

    def to_dict(self) -> dict:
        return {
            "output": self.output,
            "steps": [s.to_dict() for s in self.steps],
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "revised": self.revised,
        }


class PlanAndExecute:
    """Plan-and-Execute strategy for complex tasks."""

    def __init__(
        self,
        heimdall: HeimdallClient,
        tool_registry: ToolRegistry,
        max_iterations: int = 10,
        max_execution_time: int = 300,
        revise_after: int = 3,
    ):
        self.heimdall = heimdall
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.max_execution_time = max_execution_time
        self.revise_after = revise_after

    async def _create_plan(self, user_input: str, model: str | None = None) -> list[PlanStep]:
        """Use LLM to create a plan."""
        prompt = PLANNER_PROMPT.format(user_input=user_input)

        response = await self.heimdall.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.3,  # Low temp for structured planning
        )

        content = response.get("choices", [{}])[0].get("message", {}).get("content", "[]")

        try:
            # Extract JSON from response
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                steps_data = json.loads(content[start:end])
            else:
                steps_data = json.loads(content)

            return [
                PlanStep(
                    step=s.get("step", i + 1),
                    task=s.get("task", ""),
                    depends_on=s.get("depends_on", []),
                )
                for i, s in enumerate(steps_data)
            ]
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Plan parsing failed: {e}")
            # Fallback: single step
            return [PlanStep(step=1, task=user_input)]

    async def _execute_step(
        self, step: PlanStep, context: str, model: str | None = None
    ) -> str:
        """Execute a single plan step using the ReAct executor."""
        executor = AgentExecutor(
            heimdall=self.heimdall,
            tool_registry=self.tool_registry,
            max_iterations=self.max_iterations,
            max_execution_time=self.max_execution_time,
        )

        system_prompt = (
            "You are executing one step of a larger plan. "
            "Complete ONLY the assigned step. Be precise and thorough.\n\n"
            f"Context from previous steps:\n{context}"
        )

        result = await executor.execute(
            system_prompt=system_prompt,
            user_input=step.task,
            model=model,
        )

        return result.output

    async def _revise_plan(
        self, original_steps: list[PlanStep], completed: list[PlanStep],
        remaining: list[PlanStep], model: str | None = None
    ) -> list[PlanStep]:
        """Revise remaining plan steps based on results so far."""
        prompt = REVISION_PROMPT.format(
            original_plan=json.dumps([s.to_dict() for s in original_steps], indent=2),
            completed_steps=json.dumps(
                [{"step": s.step, "task": s.task, "result": s.result[:300]} for s in completed],
                indent=2,
            ),
            remaining_steps=json.dumps([s.to_dict() for s in remaining], indent=2),
        )

        response = await self.heimdall.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.3,
        )

        content = response.get("choices", [{}])[0].get("message", {}).get("content", "[]")

        try:
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                steps_data = json.loads(content[start:end])
            else:
                steps_data = json.loads(content)

            return [
                PlanStep(
                    step=s.get("step", i + 1),
                    task=s.get("task", ""),
                    depends_on=s.get("depends_on", []),
                )
                for i, s in enumerate(steps_data)
            ]
        except (json.JSONDecodeError, KeyError):
            return remaining  # Keep original if revision fails

    async def execute(
        self, user_input: str, model: str | None = None,
        system_prompt: str = "",
    ) -> PlanResult:
        """Plan and execute a complex task."""
        # Phase 1: Plan
        logger.info("Planning...")
        steps = await self._create_plan(user_input, model)
        original_steps = list(steps)
        logger.info(f"Plan created with {len(steps)} steps")

        # Phase 2: Execute
        context = ""
        completed = []
        revised = False

        for i, step in enumerate(steps):
            step.status = "running"
            logger.info(f"Executing step {step.step}: {step.task[:80]}")

            try:
                result = await self._execute_step(step, context, model)
                step.result = result
                step.status = "completed"
                completed.append(step)
                context += f"\n[Step {step.step}] {step.task}\nResult: {result[:500]}\n"
            except Exception as e:
                step.result = f"Error: {e}"
                step.status = "failed"
                logger.warning(f"Step {step.step} failed: {e}")

            # Phase 3: Revise (after N steps)
            if (
                len(completed) == self.revise_after
                and i < len(steps) - 1
                and not revised
            ):
                remaining = [s for s in steps[i + 1:] if s.status == "pending"]
                if remaining:
                    logger.info("Revising plan...")
                    revised_steps = await self._revise_plan(
                        original_steps, completed, remaining, model
                    )
                    # Replace remaining steps
                    steps = steps[:i + 1] + revised_steps
                    revised = True

        # Compile final output
        outputs = [s.result for s in steps if s.status == "completed" and s.result]
        final_output = "\n\n".join(outputs) if outputs else "Plan execution completed with no output."

        return PlanResult(
            output=final_output,
            steps=steps,
            total_steps=len(steps),
            completed_steps=sum(1 for s in steps if s.status == "completed"),
            failed_steps=sum(1 for s in steps if s.status == "failed"),
            revised=revised,
        )
