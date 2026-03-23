"""Odin Coordinator — multi-agent orchestration engine.

The core of Odin: decompose → spawn → execute → synthesize.
Inspired by DeerFlow's Lead Agent and HiClaw's Manager pattern.

Features:
- Task decomposition via LLM planner
- Concurrent sub-agent execution (max 3 via semaphore)
- 15-minute timeout per sub-agent
- Result synthesis into coherent final answer
- Sprint 35 integration: memory, skills, context engineering
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from bifrost.agents.odin.models import SubTask, TaskPlan, SubAgentResult, OdinResult
from bifrost.agents.odin.registry import SubAgentRegistry
from bifrost.agents.odin.planner import OdinPlanner
from bifrost.core.executor import AgentExecutor

logger = logging.getLogger("bifrost.odin.coordinator")


SYNTHESIS_PROMPT = """You are Odin, the coordinator of a multi-agent AI system.
Multiple sub-agents have worked on parts of a user's request. Your job is to
synthesize their results into a single, coherent, and comprehensive final answer.

Original user request: {request}

Sub-agent results:
{results}

Instructions:
- Combine all successful results into one clear answer
- Note any failed tasks and their errors
- Do NOT just concatenate results — produce a coherent narrative
- Respond in the same language as the original request
- If all tasks failed, explain what went wrong and suggest alternatives"""


class OdinCoordinator:
    """Multi-agent orchestration coordinator.

    Decomposes user requests into sub-tasks, spawns specialized sub-agents,
    executes them concurrently (with limits), and synthesizes results.
    """

    def __init__(
        self,
        heimdall,
        tool_registry,
        max_concurrent: int = 3,
        sub_agent_timeout: float = 900,  # 15 minutes
        memory_store: Any = None,
        skills_loader: Any = None,
        all_skills: list | None = None,
        context_middleware: Any = None,
        tenant_id: str = "default",
        model: str | None = None,
        token_issuer: Any = None,
    ):
        self.heimdall = heimdall
        self.tool_registry = tool_registry
        self.max_concurrent = max_concurrent
        self.sub_agent_timeout = sub_agent_timeout
        self.memory_store = memory_store
        self.skills_loader = skills_loader
        self.all_skills = all_skills or []
        self.context_middleware = context_middleware
        self.tenant_id = tenant_id
        self.model = model
        self.token_issuer = token_issuer

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._registry = SubAgentRegistry()
        self._planner = OdinPlanner(heimdall=heimdall, model=model)

    async def execute(
        self,
        request: str,
        history: list[dict] | None = None,
        model: str | None = None,
    ) -> OdinResult:
        """Full orchestration pipeline: decompose → spawn → synthesize.

        Args:
            request: User's natural language request.
            history: Conversation history (for context).
            model: Optional model override.

        Returns:
            OdinResult with final output, plan, and sub-results.
        """
        start_time = time.monotonic()

        # 1. Apply context middleware to history if available
        if history and self.context_middleware:
            history = await self.context_middleware.process(history)

        # 2. Decompose request into sub-tasks
        plan = await self._planner.decompose(request)
        logger.info(f"Odin plan: {plan.sub_task_count} sub-tasks for: {request[:80]}")

        # 3. Execute sub-tasks respecting dependency ordering
        all_results: list[SubAgentResult] = []
        completed_ids: set[str] = set()

        # Group tasks by dependency level
        pending = list(plan.sub_tasks)
        while pending:
            # Find tasks whose dependencies are all met
            ready = [
                t for t in pending
                if all(dep in completed_ids for dep in t.depends_on)
            ]

            if not ready:
                # Break deadlock: force-run first pending task
                logger.warning("Dependency deadlock detected, forcing execution")
                ready = [pending[0]]

            # Execute ready batch concurrently
            batch_results = await self._execute_batch(ready)
            all_results.extend(batch_results)

            for task in ready:
                completed_ids.add(task.id)
                pending.remove(task)

        # 4. Synthesize results
        final_output = await self._synthesize(all_results, request)

        total_duration = (time.monotonic() - start_time) * 1000
        agents_used = list(set(r.agent_type for r in all_results))

        return OdinResult(
            output=final_output,
            plan=plan,
            sub_results=all_results,
            total_duration_ms=total_duration,
            agents_used=agents_used,
        )

    async def _execute_batch(self, tasks: list[SubTask]) -> list[SubAgentResult]:
        """Execute a batch of independent sub-tasks concurrently.

        Respects max_concurrent limit via semaphore.
        """
        coros = [self._execute_sub_agent(task) for task in tasks]
        return await asyncio.gather(*coros)

    async def _execute_sub_agent(self, task: SubTask) -> SubAgentResult:
        """Execute a single sub-agent for a sub-task.

        Enforces timeout and concurrency limits.
        """
        async with self._semaphore:
            start_time = time.monotonic()
            task.status = "running"

            try:
                result = await asyncio.wait_for(
                    self._run_agent(task),
                    timeout=self.sub_agent_timeout,
                )
                duration = (time.monotonic() - start_time) * 1000
                task.status = "completed"
                task.result = result
                task.duration_ms = duration

                return SubAgentResult(
                    sub_task_id=task.id,
                    agent_type=task.agent_type,
                    output=result,
                    success=True,
                    duration_ms=duration,
                )

            except asyncio.TimeoutError:
                duration = (time.monotonic() - start_time) * 1000
                task.status = "failed"
                task.duration_ms = duration
                error_msg = f"Timeout after {self.sub_agent_timeout}s"
                logger.warning(f"Sub-agent {task.id} ({task.agent_type}): {error_msg}")

                return SubAgentResult(
                    sub_task_id=task.id,
                    agent_type=task.agent_type,
                    output="",
                    success=False,
                    duration_ms=duration,
                    error=error_msg,
                )

            except Exception as e:
                duration = (time.monotonic() - start_time) * 1000
                task.status = "failed"
                task.duration_ms = duration
                error_msg = str(e)
                logger.warning(f"Sub-agent {task.id} ({task.agent_type}) error: {error_msg}")

                return SubAgentResult(
                    sub_task_id=task.id,
                    agent_type=task.agent_type,
                    output="",
                    success=False,
                    duration_ms=duration,
                    error=error_msg,
                )

    async def _run_agent(self, task: SubTask) -> str:
        """Run a sub-agent using the existing AgentExecutor.

        Builds the system prompt from the agent type registry,
        injects memory and skills from Sprint 35.
        """
        # Get agent type config (fallback to 'general' if unknown)
        agent_type = self._registry.get(task.agent_type)
        if not agent_type:
            logger.warning(f"Unknown agent type '{task.agent_type}', falling back to 'general'")
            agent_type = self._registry.get("general")

        system_prompt = agent_type.system_prompt

        # Sprint 36B: Credential isolation via scoped agent token
        sub_tool_registry = self.tool_registry
        if self.token_issuer:
            try:
                from bifrost.agents.odin.credential_proxy import CredentialProxy

                scoped_token = self.token_issuer.issue(
                    agent_id=f"{task.agent_type}-{task.id}",
                    tenant_id=self.tenant_id,
                    allowed_tools=agent_type.allowed_tools,
                    ttl=int(self.sub_agent_timeout),
                )
                # Validate token (self-check) and create filtered registry
                from bifrost.agents.odin.agent_token import AgentToken
                agent_token = AgentToken(
                    agent_id=f"{task.agent_type}-{task.id}",
                    tenant_id=self.tenant_id,
                    allowed_tools=agent_type.allowed_tools,
                    ttl_seconds=int(self.sub_agent_timeout),
                )
                proxy = CredentialProxy()
                sub_tool_registry = proxy.wrap_tool_registry(self.tool_registry, agent_token)
                logger.info(f"Credential isolation: {task.id} scoped to {len(agent_type.allowed_tools)} tools")
            except Exception as e:
                logger.warning(f"Credential isolation failed for {task.id}: {e}")

        # Sprint 35: Inject memory facts
        if self.memory_store:
            try:
                from bifrost.memory.store import MemoryStore
                facts = await self.memory_store.get_facts(self.tenant_id, limit=15)
                if facts:
                    memory_block = MemoryStore.format_memory_prompt(facts)
                    system_prompt = f"{system_prompt}\n\n{memory_block}"
            except Exception as e:
                logger.warning(f"Memory injection failed: {e}")

        # Sprint 35: Inject relevant skills
        if self.skills_loader and self.all_skills:
            try:
                relevant = self.skills_loader.get_relevant_skills(task.description, self.all_skills)
                if relevant:
                    skills_block = self.skills_loader.format_skills_prompt(relevant)
                    system_prompt = f"{system_prompt}\n\n{skills_block}"
            except Exception as e:
                logger.warning(f"Skills injection failed: {e}")

        # Execute via AgentExecutor
        executor = AgentExecutor(
            heimdall=self.heimdall,
            tool_registry=sub_tool_registry,
            max_iterations=10,
            max_execution_time=int(self.sub_agent_timeout),
        )

        result = await executor.execute(
            system_prompt=system_prompt,
            user_input=task.description,
            model=self.model,
        )

        return result.output

    async def _synthesize(
        self, results: list[SubAgentResult], request: str
    ) -> str:
        """Synthesize sub-agent results into a final coherent answer.

        Uses LLM to combine multiple results into one response.
        """
        if not results:
            return "No sub-agents were executed."

        # Format results for synthesis prompt
        results_text = ""
        for r in results:
            status = "✅ Success" if r.success else f"❌ Failed: {r.error}"
            results_text += f"\n[{r.agent_type}] Task {r.sub_task_id}: {status}\n"
            if r.output:
                results_text += f"Output: {r.output[:1000]}\n"

        prompt = SYNTHESIS_PROMPT.format(
            request=request,
            results=results_text,
        )

        try:
            response = await self.heimdall.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.3,
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip() if content else "Synthesis produced no output."

        except Exception as e:
            logger.warning(f"Result synthesis failed: {e}")
            # Fallback: concatenate successful results
            outputs = [r.output for r in results if r.success and r.output]
            return "\n\n".join(outputs) if outputs else f"Orchestration failed: {e}"
