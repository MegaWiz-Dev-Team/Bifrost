"""Tests for Sprint 4 — Plan-and-Execute, Self-Reflection, PSO Agent Generator."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from bifrost.core.planner import PlanStep, PlanResult, PlanAndExecute
from bifrost.core.reflection import (
    ReflectionResult, SelfReflection, _parse_reflection,
)
from bifrost.core.pso import (
    Particle, PSOResult, PSOAgentGenerator, AGENT_PROMPTS,
)
from bifrost.core.agents import AgentConfig


# === Plan-and-Execute Tests ===

class TestPlanStep:
    def test_create(self):
        step = PlanStep(step=1, task="Search for information")
        assert step.step == 1
        assert step.status == "pending"

    def test_to_dict(self):
        step = PlanStep(step=2, task="Analyze data", depends_on=[1], result="Done")
        d = step.to_dict()
        assert d["step"] == 2
        assert d["depends_on"] == [1]


class TestPlanResult:
    def test_create(self):
        steps = [
            PlanStep(step=1, task="A", status="completed", result="R1"),
            PlanStep(step=2, task="B", status="completed", result="R2"),
        ]
        result = PlanResult(output="Combined", steps=steps, total_steps=2, completed_steps=2)
        assert result.total_steps == 2
        assert result.failed_steps == 0

    def test_to_dict(self):
        result = PlanResult(output="test", steps=[], total_steps=0)
        d = result.to_dict()
        assert "output" in d
        assert "steps" in d


class TestPlanAndExecute:
    @pytest.mark.asyncio
    async def test_create_plan(self):
        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion = AsyncMock(return_value={
            "choices": [{"message": {"content": '[{"step":1,"task":"Search","depends_on":[]},{"step":2,"task":"Analyze","depends_on":[1]}]'}}]
        })
        mock_registry = MagicMock()

        planner = PlanAndExecute(heimdall=mock_heimdall, tool_registry=mock_registry)
        steps = await planner._create_plan("Find and analyze market data")

        assert len(steps) == 2
        assert steps[0].task == "Search"
        assert steps[1].depends_on == [1]

    @pytest.mark.asyncio
    async def test_create_plan_fallback(self):
        """If plan parsing fails, fall back to single-step."""
        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion = AsyncMock(return_value={
            "choices": [{"message": {"content": "not valid json"}}]
        })
        mock_registry = MagicMock()

        planner = PlanAndExecute(heimdall=mock_heimdall, tool_registry=mock_registry)
        steps = await planner._create_plan("Test query")
        assert len(steps) == 1  # Fallback


# === Self-Reflection Tests ===

class TestParseReflection:
    def test_parse_full(self):
        text = """ACCURACY: 4
COMPLETENESS: 3
CLARITY: 5
HELPFULNESS: 4
OVERALL: 4.0
CRITIQUE: Good but could be more complete
SHOULD_RETRY: no
IMPROVEMENT: Add more details about edge cases"""

        result = _parse_reflection(text)
        assert result.accuracy == 4
        assert result.completeness == 3
        assert result.clarity == 5
        assert result.helpfulness == 4
        assert result.overall == 4.0
        assert result.should_retry is False
        assert "edge cases" in result.improvement

    def test_parse_retry_needed(self):
        text = """ACCURACY: 2
COMPLETENESS: 2
CLARITY: 3
HELPFULNESS: 2
OVERALL: 2.25
CRITIQUE: Response is too vague
SHOULD_RETRY: yes
IMPROVEMENT: Provide specific examples and data"""

        result = _parse_reflection(text)
        assert result.should_retry is True
        assert result.overall == 2.25

    def test_parse_empty(self):
        result = _parse_reflection("")
        assert result.accuracy == 0
        assert result.overall == 0.0

    def test_auto_calculate_overall(self):
        text = """ACCURACY: 4
COMPLETENESS: 4
CLARITY: 4
HELPFULNESS: 4
OVERALL: 0
CRITIQUE: Fine"""

        result = _parse_reflection(text)
        # Should auto-calculate since OVERALL was 0
        assert result.overall == 4.0


class TestReflectionResult:
    def test_passed(self):
        result = ReflectionResult(overall=4.0)
        assert result.passed is True

    def test_not_passed(self):
        result = ReflectionResult(overall=2.0)
        assert result.passed is False

    def test_threshold(self):
        result = ReflectionResult(overall=3.5)
        assert result.passed is True

    def test_to_dict(self):
        result = ReflectionResult(accuracy=5, completeness=4, clarity=3, helpfulness=4)
        d = result.to_dict()
        assert d["accuracy"] == 5


class TestSelfReflection:
    @pytest.mark.asyncio
    async def test_reflect(self):
        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion = AsyncMock(return_value={
            "choices": [{"message": {"content": "ACCURACY: 4\nCOMPLETENESS: 4\nCLARITY: 5\nHELPFULNESS: 4\nOVERALL: 4.25\nCRITIQUE: Good\nSHOULD_RETRY: no\nIMPROVEMENT: none"}}]
        })

        reflector = SelfReflection(heimdall=mock_heimdall)
        result = await reflector.reflect("What is Python?", "Python is a language")
        assert result.overall == 4.25
        assert result.should_retry is False


# === PSO Agent Generator Tests ===

class TestParticle:
    def test_create(self):
        config = AgentConfig(id="p1", name="P1", system_prompt="Hello")
        particle = Particle(id=0, config=config)
        assert particle.fitness == 0.0
        assert particle.best_fitness == 0.0

    def test_to_dict(self):
        config = AgentConfig(id="p1", name="P1", system_prompt="Hello")
        particle = Particle(id=0, config=config, fitness=0.85)
        d = particle.to_dict()
        assert d["fitness"] == 0.85


class TestPSOAgentGenerator:
    def test_random_config(self):
        gen = PSOAgentGenerator(available_tools=["calculate", "search_knowledge", "http_request"])
        config = gen._random_config(0)
        assert config.id == "pso-agent-0"
        assert len(config.tools) >= 1
        assert 0.1 <= config.temperature <= 1.0
        assert config.system_prompt in AGENT_PROMPTS

    def test_mutate_config(self):
        gen = PSOAgentGenerator(available_tools=["calculate", "search_knowledge", "http_request"])
        original = AgentConfig(
            id="test", name="Test", system_prompt="Hello",
            temperature=0.5, tools=["calculate"],
        )
        global_best = AgentConfig(
            id="best", name="Best", system_prompt="Best prompt",
            temperature=0.7, tools=["calculate", "search_knowledge"],
        )
        mutated = gen._mutate_config(original, global_best)
        # Should be different (at least temperature should change)
        assert mutated.id == original.id  # ID preserved

    @pytest.mark.asyncio
    async def test_optimize(self):
        gen = PSOAgentGenerator(
            available_tools=["calculate", "search_knowledge"],
            swarm_size=3,
            max_generations=2,
        )

        # Simple fitness: higher temperature = higher fitness
        async def fitness_fn(config: AgentConfig) -> float:
            return config.temperature

        result = await gen.optimize(fitness_fn, purpose="test optimization")
        assert result.best_fitness > 0
        assert result.iterations == 2
        assert result.particles_evaluated == 6  # 3 particles × 2 generations
        assert len(result.history) == 2
        assert result.best_config.name.startswith("PSO Optimized")

    @pytest.mark.asyncio
    async def test_optimize_with_errors(self):
        gen = PSOAgentGenerator(
            available_tools=["calculate"],
            swarm_size=2,
            max_generations=1,
        )

        call_count = 0
        async def failing_fitness(config):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Test error")
            return 0.5

        result = await gen.optimize(failing_fitness)
        assert result.best_fitness >= 0  # Should still produce a result


class TestPSOResult:
    def test_to_dict(self):
        config = AgentConfig(id="best", name="Best", system_prompt="Hello")
        result = PSOResult(
            best_config=config, best_fitness=0.95,
            iterations=3, particles_evaluated=18
        )
        d = result.to_dict()
        assert d["best_fitness"] == 0.95
        assert d["iterations"] == 3
