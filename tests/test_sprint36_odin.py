"""Sprint 36 TDD — Odin Agent Coordinator (Multi-Agent Orchestration).

Tests: models, registry, task decomposition, sub-agent spawning,
       timeout enforcement, result synthesis, Sprint 35 integration,
       error handling, API endpoints.

Run: cd /Users/mimir/Developer/Bifrost && python -m pytest tests/test_sprint36_odin.py -v
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ═══════════════════════════════════════════
# 1. SubTask Model
# ═══════════════════════════════════════════


class TestSubTaskModel:
    """SubTask data model tests."""

    def test_subtask_creation(self):
        """SubTask can be created with required fields."""
        from bifrost.agents.odin.models import SubTask

        task = SubTask(
            id="task-1",
            description="Search for vulnerabilities",
            agent_type="researcher",
        )
        assert task.id == "task-1"
        assert task.description == "Search for vulnerabilities"
        assert task.agent_type == "researcher"

    def test_subtask_default_status(self):
        """SubTask defaults to 'pending' status."""
        from bifrost.agents.odin.models import SubTask

        task = SubTask(id="t1", description="test", agent_type="general")
        assert task.status == "pending"

    def test_subtask_status_transitions(self):
        """SubTask status can transition: pending → running → completed/failed."""
        from bifrost.agents.odin.models import SubTask

        task = SubTask(id="t1", description="test", agent_type="general")
        assert task.status == "pending"
        task.status = "running"
        assert task.status == "running"
        task.status = "completed"
        assert task.status == "completed"

    def test_subtask_serialization(self):
        """SubTask can serialize to dict."""
        from bifrost.agents.odin.models import SubTask

        task = SubTask(
            id="task-1",
            description="Analyze code",
            agent_type="coder",
            depends_on=["task-0"],
        )
        d = task.to_dict()
        assert d["id"] == "task-1"
        assert d["description"] == "Analyze code"
        assert d["agent_type"] == "coder"
        assert d["depends_on"] == ["task-0"]

    def test_subtask_depends_on_default_empty(self):
        """SubTask.depends_on defaults to empty list."""
        from bifrost.agents.odin.models import SubTask

        task = SubTask(id="t1", description="test", agent_type="general")
        assert task.depends_on == []


# ═══════════════════════════════════════════
# 2. TaskPlan Model
# ═══════════════════════════════════════════


class TestTaskPlanModel:
    """TaskPlan data model tests."""

    def test_taskplan_creation(self):
        """TaskPlan can be created with request and sub_tasks."""
        from bifrost.agents.odin.models import SubTask, TaskPlan

        tasks = [
            SubTask(id="t1", description="Research", agent_type="researcher"),
            SubTask(id="t2", description="Code", agent_type="coder"),
        ]
        plan = TaskPlan(original_request="Build a feature", sub_tasks=tasks)
        assert plan.original_request == "Build a feature"
        assert len(plan.sub_tasks) == 2

    def test_taskplan_sub_task_count(self):
        """TaskPlan.sub_task_count returns correct count."""
        from bifrost.agents.odin.models import SubTask, TaskPlan

        tasks = [SubTask(id=f"t{i}", description=f"Task {i}", agent_type="general") for i in range(4)]
        plan = TaskPlan(original_request="complex task", sub_tasks=tasks)
        assert plan.sub_task_count == 4

    def test_taskplan_empty(self):
        """TaskPlan can be created with no sub_tasks."""
        from bifrost.agents.odin.models import TaskPlan

        plan = TaskPlan(original_request="simple task", sub_tasks=[])
        assert plan.sub_task_count == 0

    def test_taskplan_serialization(self):
        """TaskPlan can serialize to dict."""
        from bifrost.agents.odin.models import SubTask, TaskPlan

        tasks = [SubTask(id="t1", description="Do X", agent_type="general")]
        plan = TaskPlan(original_request="test", sub_tasks=tasks)
        d = plan.to_dict()
        assert d["original_request"] == "test"
        assert len(d["sub_tasks"]) == 1


# ═══════════════════════════════════════════
# 3. SubAgentRegistry
# ═══════════════════════════════════════════


class TestSubAgentRegistry:
    """SubAgentRegistry tests."""

    def test_registry_has_builtin_types(self):
        """Registry includes 5 built-in agent types."""
        from bifrost.agents.odin.registry import SubAgentRegistry

        registry = SubAgentRegistry()
        types = registry.list_types()
        assert len(types) >= 5
        type_names = [t.name for t in types]
        assert "general" in type_names
        assert "researcher" in type_names
        assert "coder" in type_names
        assert "medical" in type_names
        assert "devops" in type_names

    def test_registry_get_existing_type(self):
        """Registry.get() returns type config for known types."""
        from bifrost.agents.odin.registry import SubAgentRegistry

        registry = SubAgentRegistry()
        agent_type = registry.get("researcher")
        assert agent_type is not None
        assert agent_type.name == "researcher"
        assert agent_type.system_prompt  # non-empty

    def test_registry_get_unknown_type(self):
        """Registry.get() returns None for unknown types."""
        from bifrost.agents.odin.registry import SubAgentRegistry

        registry = SubAgentRegistry()
        assert registry.get("nonexistent") is None

    def test_registry_register_custom_type(self):
        """Registry allows registering custom agent types."""
        from bifrost.agents.odin.registry import SubAgentRegistry, SubAgentType

        registry = SubAgentRegistry()
        custom = SubAgentType(
            name="data-analyst",
            system_prompt="You are a data analyst.",
            allowed_tools=["query_db", "chart_builder"],
        )
        registry.register(custom)
        retrieved = registry.get("data-analyst")
        assert retrieved is not None
        assert retrieved.name == "data-analyst"

    def test_registry_type_has_system_prompt(self):
        """Each built-in type has a non-empty system prompt."""
        from bifrost.agents.odin.registry import SubAgentRegistry

        registry = SubAgentRegistry()
        for agent_type in registry.list_types():
            assert agent_type.system_prompt, f"{agent_type.name} has empty system_prompt"


# ═══════════════════════════════════════════
# 4. Task Decomposition (Planner)
# ═══════════════════════════════════════════


class TestTaskDecomposition:
    """OdinPlanner — LLM-based task decomposition."""

    @pytest.mark.asyncio
    async def test_decompose_simple_request(self):
        """Simple request → 1 sub-task of type 'general'."""
        from bifrost.agents.odin.planner import OdinPlanner

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": '[{"id":"t1","description":"Answer the question","agent_type":"general","depends_on":[]}]'}}]
        }

        planner = OdinPlanner(heimdall=mock_heimdall)
        plan = await planner.decompose("What is Python?")

        assert len(plan.sub_tasks) == 1
        assert plan.sub_tasks[0].agent_type == "general"

    @pytest.mark.asyncio
    async def test_decompose_complex_request(self):
        """Complex request → multiple sub-tasks with dependencies."""
        from bifrost.agents.odin.planner import OdinPlanner
        import json

        plan_data = [
            {"id": "t1", "description": "Research vulnerabilities", "agent_type": "researcher", "depends_on": []},
            {"id": "t2", "description": "Write patches", "agent_type": "coder", "depends_on": ["t1"]},
            {"id": "t3", "description": "Deploy fixes", "agent_type": "devops", "depends_on": ["t2"]},
        ]
        content_str = json.dumps(plan_data)

        mock_heimdall = AsyncMock()

        async def mock_chat(**kwargs):
            return {"choices": [{"message": {"content": content_str}}]}

        mock_heimdall.chat_completion = mock_chat

        planner = OdinPlanner(heimdall=mock_heimdall)
        plan = await planner.decompose("Find and fix security vulnerabilities, then deploy")

        assert len(plan.sub_tasks) == 3
        assert plan.sub_tasks[1].depends_on == ["t1"]
        assert plan.sub_tasks[2].depends_on == ["t2"]

    @pytest.mark.asyncio
    async def test_decompose_fallback_on_error(self):
        """If LLM returns invalid JSON, fallback to single general sub-task."""
        from bifrost.agents.odin.planner import OdinPlanner

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "I cannot parse this into a plan."}}]
        }

        planner = OdinPlanner(heimdall=mock_heimdall)
        plan = await planner.decompose("Do something complex")

        assert len(plan.sub_tasks) == 1
        assert plan.sub_tasks[0].agent_type == "general"


# ═══════════════════════════════════════════
# 5. Sub-Agent Spawning
# ═══════════════════════════════════════════


class TestSubAgentSpawning:
    """OdinCoordinator — sub-agent spawning and concurrency."""

    @pytest.mark.asyncio
    async def test_spawn_single_agent(self):
        """Coordinator can spawn and execute a single sub-agent."""
        from bifrost.agents.odin.coordinator import OdinCoordinator
        from bifrost.agents.odin.models import SubTask

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "Result from agent"}, "finish_reason": "stop"}]
        }

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
        )

        task = SubTask(id="t1", description="Answer question", agent_type="general")
        result = await coordinator._execute_sub_agent(task)

        assert result.success is True
        assert result.output  # non-empty

    @pytest.mark.asyncio
    async def test_max_3_concurrent(self):
        """Coordinator enforces max 3 concurrent sub-agents via semaphore."""
        from bifrost.agents.odin.coordinator import OdinCoordinator
        from bifrost.agents.odin.models import SubTask

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "done"}, "finish_reason": "stop"}]
        }

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
            max_concurrent=3,
        )

        # Verify semaphore is set to 3
        assert coordinator._semaphore._value == 3

    @pytest.mark.asyncio
    async def test_concurrent_execution(self):
        """Multiple independent sub-tasks execute concurrently."""
        from bifrost.agents.odin.coordinator import OdinCoordinator
        from bifrost.agents.odin.models import SubTask

        execution_order = []

        async def mock_chat(**kwargs):
            # Simulate varied response times
            execution_order.append("started")
            await asyncio.sleep(0.01)
            execution_order.append("finished")
            return {
                "choices": [{"message": {"content": "result"}, "finish_reason": "stop"}]
            }

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion = mock_chat

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
        )

        tasks = [
            SubTask(id=f"t{i}", description=f"Task {i}", agent_type="general")
            for i in range(3)
        ]

        results = await coordinator._execute_batch(tasks)
        assert len(results) == 3
        assert all(r.success for r in results)


# ═══════════════════════════════════════════
# 6. Timeout Enforcement
# ═══════════════════════════════════════════


class TestTimeoutEnforcement:
    """OdinCoordinator — 15-min timeout per sub-agent."""

    @pytest.mark.asyncio
    async def test_within_timeout(self):
        """Sub-agent completing within timeout returns normally."""
        from bifrost.agents.odin.coordinator import OdinCoordinator
        from bifrost.agents.odin.models import SubTask

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "Quick result"}, "finish_reason": "stop"}]
        }

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
            sub_agent_timeout=900,  # 15 min
        )

        task = SubTask(id="t1", description="Quick task", agent_type="general")
        result = await coordinator._execute_sub_agent(task)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_exceeds_timeout(self):
        """Sub-agent exceeding timeout returns failure with timeout error."""
        from bifrost.agents.odin.coordinator import OdinCoordinator
        from bifrost.agents.odin.models import SubTask

        async def slow_run(task):
            await asyncio.sleep(10)  # Simulates slow agent
            return "late"

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "late"}, "finish_reason": "stop"}]
        }

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
            sub_agent_timeout=0.05,  # 50ms for test speed
        )
        # Override _run_agent to simulate a slow agent
        coordinator._run_agent = slow_run

        task = SubTask(id="t1", description="Slow task", agent_type="general")
        result = await coordinator._execute_sub_agent(task)
        assert result.success is False
        assert "timeout" in result.error.lower()


# ═══════════════════════════════════════════
# 7. Result Synthesis
# ═══════════════════════════════════════════


class TestResultSynthesis:
    """OdinCoordinator — combining sub-agent results into final answer."""

    @pytest.mark.asyncio
    async def test_synthesize_single_result(self):
        """Single result passes through as final output."""
        from bifrost.agents.odin.coordinator import OdinCoordinator
        from bifrost.agents.odin.models import SubAgentResult

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "Synthesized answer"}}]
        }

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
        )

        results = [
            SubAgentResult(sub_task_id="t1", agent_type="general", output="Answer A", success=True),
        ]

        final = await coordinator._synthesize(results, "original question")
        assert final  # non-empty string

    @pytest.mark.asyncio
    async def test_synthesize_multiple_results(self):
        """Multiple results are combined into a coherent final answer."""
        from bifrost.agents.odin.coordinator import OdinCoordinator
        from bifrost.agents.odin.models import SubAgentResult

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "Combined answer from all agents"}}]
        }

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
        )

        results = [
            SubAgentResult(sub_task_id="t1", agent_type="researcher", output="Research findings", success=True),
            SubAgentResult(sub_task_id="t2", agent_type="coder", output="Code solution", success=True),
            SubAgentResult(sub_task_id="t3", agent_type="devops", output="Deployment plan", success=True),
        ]

        final = await coordinator._synthesize(results, "full pipeline request")
        assert final
        assert isinstance(final, str)

    @pytest.mark.asyncio
    async def test_synthesize_partial_failure(self):
        """Synthesis handles partial failures gracefully."""
        from bifrost.agents.odin.coordinator import OdinCoordinator
        from bifrost.agents.odin.models import SubAgentResult

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "Partial result with some tasks failed"}}]
        }

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
        )

        results = [
            SubAgentResult(sub_task_id="t1", agent_type="researcher", output="Success", success=True),
            SubAgentResult(sub_task_id="t2", agent_type="coder", output="", success=False, error="timeout"),
        ]

        final = await coordinator._synthesize(results, "mixed request")
        assert final  # Still produces output despite failure


# ═══════════════════════════════════════════
# 8. Sprint 35 Integration
# ═══════════════════════════════════════════


class TestSprint35Integration:
    """OdinCoordinator — memory, skills, context engineering integration."""

    @pytest.mark.asyncio
    async def test_memory_injection(self):
        """Coordinator injects memory facts into sub-agent system prompts."""
        from bifrost.agents.odin.coordinator import OdinCoordinator
        from bifrost.agents.odin.models import SubTask
        from bifrost.memory.schema import MemoryFact

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "answer with memory"}, "finish_reason": "stop"}]
        }

        mock_memory = AsyncMock()
        mock_memory.get_facts.return_value = [
            MemoryFact(id=1, tenant_id="t1", category="fact", content="User prefers Thai"),
        ]

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
            memory_store=mock_memory,
            tenant_id="t1",
        )

        task = SubTask(id="t1", description="Greet user", agent_type="general")
        result = await coordinator._execute_sub_agent(task)

        # Memory store should have been queried
        mock_memory.get_facts.assert_called_once()

    @pytest.mark.asyncio
    async def test_skills_injection(self):
        """Coordinator injects relevant skills into sub-agent prompts."""
        from bifrost.agents.odin.coordinator import OdinCoordinator
        from bifrost.agents.odin.models import SubTask
        from bifrost.skills.models import SkillConfig

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "answer with skills"}, "finish_reason": "stop"}]
        }

        mock_loader = MagicMock()
        mock_loader.get_relevant_skills.return_value = [
            SkillConfig(name="medical-research", description="Research medical topics", tags=["medical"]),
        ]
        mock_loader.format_skills_prompt.return_value = "<skills>...</skills>"

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
            skills_loader=mock_loader,
            all_skills=[SkillConfig(name="test", description="test", tags=[])],
        )

        task = SubTask(id="t1", description="Medical research", agent_type="medical")
        result = await coordinator._execute_sub_agent(task)

        # Skills loader should have been queried
        mock_loader.get_relevant_skills.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_middleware(self):
        """Coordinator applies context middleware to conversation history."""
        from bifrost.agents.odin.coordinator import OdinCoordinator

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "synthesized"}}]
        }

        # Planner returns single task
        mock_planner_response = {
            "choices": [{"message": {"content": '[{"id":"t1","description":"Answer","agent_type":"general","depends_on":[]}]'}}]
        }

        call_count = 0
        async def mock_chat(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_planner_response
            return {"choices": [{"message": {"content": "done"}, "finish_reason": "stop"}]}

        mock_heimdall.chat_completion = mock_chat

        mock_context = AsyncMock()
        mock_context.process.return_value = [{"role": "user", "content": "compressed"}]

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
            context_middleware=mock_context,
        )

        # Provide long history that should trigger compression
        history = [{"role": "user", "content": f"msg {i}"} for i in range(25)]
        result = await coordinator.execute("summarize conversation", history=history)

        # Context middleware should have been called
        mock_context.process.assert_called()


# ═══════════════════════════════════════════
# 9. Error Handling
# ═══════════════════════════════════════════


class TestErrorHandling:
    """OdinCoordinator — error handling and fallbacks."""

    @pytest.mark.asyncio
    async def test_all_agents_fail(self):
        """When all sub-agents fail, returns error summary."""
        from bifrost.agents.odin.coordinator import OdinCoordinator
        from bifrost.agents.odin.models import SubAgentResult

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "All tasks failed. Summary of errors..."}}]
        }

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
        )

        results = [
            SubAgentResult(sub_task_id="t1", agent_type="general", output="", success=False, error="timeout"),
            SubAgentResult(sub_task_id="t2", agent_type="coder", output="", success=False, error="LLM error"),
        ]

        final = await coordinator._synthesize(results, "failing request")
        assert final  # Should still produce a response

    @pytest.mark.asyncio
    async def test_planner_error_fallback(self):
        """When planner fails completely, falls back to single general task."""
        from bifrost.agents.odin.planner import OdinPlanner

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.side_effect = Exception("LLM unreachable")

        planner = OdinPlanner(heimdall=mock_heimdall)
        plan = await planner.decompose("Some request")

        # Should fallback to single task
        assert len(plan.sub_tasks) == 1
        assert plan.sub_tasks[0].agent_type == "general"

    @pytest.mark.asyncio
    async def test_invalid_agent_type_fallback(self):
        """Sub-task with unknown agent_type falls back to 'general'."""
        from bifrost.agents.odin.coordinator import OdinCoordinator
        from bifrost.agents.odin.models import SubTask

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "handled by general"}, "finish_reason": "stop"}]
        }

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
        )

        # Unknown agent type
        task = SubTask(id="t1", description="Do something", agent_type="unknown_type")
        result = await coordinator._execute_sub_agent(task)

        # Should still succeed, falling back to general
        assert result.success is True


# ═══════════════════════════════════════════
# 10. API Endpoints
# ═══════════════════════════════════════════


class TestOdinAPI:
    """Odin REST API endpoint tests."""

    @pytest.mark.asyncio
    async def test_api_orchestrate(self):
        """POST /v1/odin/orchestrate returns orchestrated response."""
        from bifrost.config import settings
        settings.auth_enabled = False

        from httpx import ASGITransport, AsyncClient
        from bifrost.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/v1/odin/orchestrate", json={
                "request": "Analyze and fix security issues",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert "output" in data
            assert "plan" in data

    @pytest.mark.asyncio
    async def test_api_plan(self):
        """POST /v1/odin/plan returns decomposition plan only."""
        from bifrost.config import settings
        settings.auth_enabled = False

        from httpx import ASGITransport, AsyncClient
        from bifrost.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/v1/odin/plan", json={
                "request": "Build a REST API",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert "sub_tasks" in data

    @pytest.mark.asyncio
    async def test_api_agent_types(self):
        """GET /v1/odin/agent-types returns available sub-agent types."""
        from bifrost.config import settings
        settings.auth_enabled = False

        from httpx import ASGITransport, AsyncClient
        from bifrost.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/odin/agent-types")
            assert resp.status_code == 200
            data = resp.json()
            assert "types" in data
            assert len(data["types"]) >= 5
