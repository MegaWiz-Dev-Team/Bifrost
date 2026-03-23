"""Agent Executor — ReAct loop core.

The heart of Bifrost: think → tool_call → observe → loop until final answer.
"""

from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from bifrost.clients.heimdall import HeimdallClient
from bifrost.tools.registry import ToolRegistry

logger = logging.getLogger("bifrost.executor")


@dataclass
class TraceStep:
    """A single step in the ReAct execution trace."""
    step: int
    type: str  # "thought", "tool_call", "tool_result", "final_answer", "error"
    content: str
    tool_name: str | None = None
    tool_args: dict | None = None
    duration_ms: float = 0


@dataclass
class ExecutionResult:
    """Result of an agent execution."""
    output: str
    trace: list[TraceStep] = field(default_factory=list)
    total_iterations: int = 0
    total_duration_ms: float = 0
    model: str = ""


class AgentExecutor:
    """Execute an agent using the ReAct (Reasoning + Acting) loop.

    Flow:
        1. Build context (system prompt + history + tools)
        2. Call LLM via Heimdall
        3. If tool_calls → execute tools → add results → loop back to 2
        4. If text response → return as final answer
        5. Guards: max_iterations, max_execution_time
    """

    def __init__(
        self,
        heimdall: HeimdallClient,
        tool_registry: ToolRegistry,
        max_iterations: int = 10,
        max_execution_time: int = 120,
        skills_loader: "SkillsLoader | None" = None,
        skills_dirs: list[str] | None = None,
        memory_store: "MemoryStore | None" = None,
        tenant_id: str = "default",
    ):
        self.heimdall = heimdall
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.max_execution_time = max_execution_time
        self.skills_loader = skills_loader
        self.skills_dirs = skills_dirs or []
        self.memory_store = memory_store
        self.tenant_id = tenant_id
        # Pre-scan skills once at init (not per-request)
        self._all_skills: list = []
        if self.skills_loader and self.skills_dirs:
            self._all_skills = self.skills_loader.scan(self.skills_dirs)
            logger.info(f"Skills loaded: {len(self._all_skills)} skills from {len(self.skills_dirs)} dirs")

    def _augment_with_skills(self, system_prompt: str, user_input: str) -> str:
        """Inject relevant skills into the system prompt (progressive loading)."""
        if not self.skills_loader or not self._all_skills:
            return system_prompt

        relevant = self.skills_loader.get_relevant_skills(user_input, self._all_skills)
        if not relevant:
            return system_prompt

        skills_block = self.skills_loader.format_skills_prompt(relevant)
        logger.info(f"Injecting {len(relevant)} skills: {[s.name for s in relevant]}")
        return f"{system_prompt}\n\n{skills_block}"

    async def _augment_with_memory(self, system_prompt: str) -> str:
        """Inject top facts from long-term memory into the system prompt."""
        if not self.memory_store:
            return system_prompt

        from bifrost.memory.store import MemoryStore
        facts = await self.memory_store.get_facts(self.tenant_id, limit=15)
        if not facts:
            return system_prompt

        memory_block = MemoryStore.format_memory_prompt(facts)
        logger.info(f"Injecting {len(facts)} memory facts for tenant {self.tenant_id}")
        return f"{system_prompt}\n\n{memory_block}"

    async def execute(
        self,
        system_prompt: str,
        user_input: str,
        model: str | None = None,
        temperature: float = 0.7,
        history: list[dict] | None = None,
    ) -> ExecutionResult:
        """Execute the ReAct loop (non-streaming).

        Args:
            system_prompt: The agent's system prompt.
            user_input: The user's message.
            model: LLM model name (uses default if None).
            temperature: Sampling temperature.
            history: Previous conversation messages.

        Returns:
            ExecutionResult with output, trace, and metadata.
        """
        start_time = time.monotonic()
        trace: list[TraceStep] = []
        tools_schema = self.tool_registry.get_openai_tools()

        # Augment system prompt with memory (persistent facts)
        augmented_prompt = await self._augment_with_memory(system_prompt)
        # Augment system prompt with relevant skills (progressive loading)
        augmented_prompt = self._augment_with_skills(augmented_prompt, user_input)

        # Build initial messages
        messages: list[dict] = [{"role": "system", "content": augmented_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        for iteration in range(1, self.max_iterations + 1):
            # Check execution time limit
            elapsed = (time.monotonic() - start_time) * 1000
            if elapsed > self.max_execution_time * 1000:
                trace.append(TraceStep(
                    step=iteration, type="error",
                    content=f"Execution timeout after {self.max_execution_time}s",
                ))
                return ExecutionResult(
                    output=f"⏱️ Execution timed out after {self.max_execution_time}s.",
                    trace=trace, total_iterations=iteration,
                    total_duration_ms=elapsed, model=model or "",
                )

            # Call LLM
            step_start = time.monotonic()
            response = await self.heimdall.chat_completion(
                messages=messages,
                model=model,
                tools=tools_schema if tools_schema else None,
                temperature=temperature,
            )
            step_duration = (time.monotonic() - step_start) * 1000

            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "")

            # Case 1: Tool calls
            tool_calls = message.get("tool_calls")
            if tool_calls:
                # Add assistant message with tool calls
                messages.append(message)

                for tc in tool_calls:
                    func = tc.get("function", {})
                    tool_name = func.get("name", "")
                    tool_args_raw = func.get("arguments", "{}")

                    try:
                        tool_args = json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw
                    except json.JSONDecodeError:
                        tool_args = {}

                    trace.append(TraceStep(
                        step=iteration, type="tool_call",
                        content=f"Calling {tool_name}",
                        tool_name=tool_name, tool_args=tool_args,
                        duration_ms=step_duration,
                    ))

                    # Execute tool
                    tool = self.tool_registry.get(tool_name)
                    if tool:
                        try:
                            tool_start = time.monotonic()
                            result = await tool.execute(**tool_args)
                            tool_duration = (time.monotonic() - tool_start) * 1000
                        except Exception as e:
                            result = f"Tool error: {e}"
                            tool_duration = 0
                    else:
                        result = f"Unknown tool: {tool_name}"
                        tool_duration = 0

                    trace.append(TraceStep(
                        step=iteration, type="tool_result",
                        content=result, tool_name=tool_name,
                        duration_ms=tool_duration,
                    ))

                    # Add tool result message
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "name": tool_name,
                        "content": result,
                    })

                continue  # Loop back for next LLM call

            # Case 2: Final answer (text response)
            content = message.get("content", "")
            trace.append(TraceStep(
                step=iteration, type="final_answer",
                content=content, duration_ms=step_duration,
            ))

            total_duration = (time.monotonic() - start_time) * 1000
            return ExecutionResult(
                output=content, trace=trace,
                total_iterations=iteration,
                total_duration_ms=total_duration,
                model=model or "",
            )

        # Max iterations reached
        total_duration = (time.monotonic() - start_time) * 1000
        trace.append(TraceStep(
            step=self.max_iterations, type="error",
            content=f"Max iterations ({self.max_iterations}) reached",
        ))
        return ExecutionResult(
            output="⚠️ Max iterations reached without a final answer.",
            trace=trace, total_iterations=self.max_iterations,
            total_duration_ms=total_duration, model=model or "",
        )

    async def execute_stream(
        self,
        system_prompt: str,
        user_input: str,
        model: str | None = None,
        temperature: float = 0.7,
        history: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Execute the ReAct loop with SSE streaming events.

        Yields SSE event dicts: {"event": "...", "data": "..."}
        """
        # For MVP, run non-streaming and yield events from the trace
        result = await self.execute(
            system_prompt=system_prompt,
            user_input=user_input,
            model=model,
            temperature=temperature,
            history=history,
        )

        for step in result.trace:
            yield {
                "event": step.type,
                "data": json.dumps({
                    "step": step.step,
                    "content": step.content,
                    "tool_name": step.tool_name,
                    "tool_args": step.tool_args,
                    "duration_ms": step.duration_ms,
                }),
            }

        yield {
            "event": "done",
            "data": json.dumps({
                "output": result.output,
                "total_iterations": result.total_iterations,
                "total_duration_ms": result.total_duration_ms,
            }),
        }
