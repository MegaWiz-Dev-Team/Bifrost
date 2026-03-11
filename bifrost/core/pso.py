"""PSO Agent Auto-Generate — Particle Swarm Optimization for agent creation.

Inspired by SwarmAgentic: uses PSO concepts to automatically generate
optimal agent configurations by evaluating different combinations of
system prompts, tools, temperature, and parameters.
"""

import random
import logging
from dataclasses import dataclass, field
from typing import Any

from bifrost.core.agents import AgentConfig

logger = logging.getLogger("bifrost.pso")


@dataclass
class Particle:
    """A particle in PSO — represents one candidate agent configuration."""
    id: int
    config: AgentConfig
    fitness: float = 0.0
    best_fitness: float = 0.0
    best_config: AgentConfig | None = None
    velocity: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "config": self.config.to_dict(),
            "fitness": round(self.fitness, 4),
            "best_fitness": round(self.best_fitness, 4),
        }


@dataclass
class PSOResult:
    """Result of PSO optimization."""
    best_config: AgentConfig
    best_fitness: float
    iterations: int
    particles_evaluated: int
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "best_config": self.best_config.to_dict(),
            "best_fitness": round(self.best_fitness, 4),
            "iterations": self.iterations,
            "particles_evaluated": self.particles_evaluated,
            "history": self.history,
        }


# === Prompt Templates for Agent Generation ===
AGENT_PROMPTS = [
    "You are a helpful assistant that answers questions accurately and concisely.",
    "You are an expert analyst who provides detailed, well-researched answers with citations.",
    "You are a friendly conversational assistant who explains complex topics simply.",
    "You are a task-focused assistant who breaks down problems step by step.",
    "You are a creative problem solver who explores multiple approaches before answering.",
    "You are a medical knowledge assistant who provides evidence-based health information.",
    "You are a technical documentation expert who writes clear, structured guides.",
    "You are a data analysis assistant who interprets results and provides actionable insights.",
]

TEMPERATURE_RANGE = (0.1, 1.0)
MAX_ITERATIONS_RANGE = (5, 15)


class PSOAgentGenerator:
    """PSO-inspired agent configuration optimizer.

    Unlike full PSO with continuous optimization, this uses PSO concepts
    (swarm, personal best, global best) adapted for discrete agent configs:
    - Particles = candidate agent configurations
    - Position = (prompt template, temperature, tool set, max_iterations)
    - Fitness = evaluation score from test queries
    """

    def __init__(
        self,
        available_tools: list[str],
        swarm_size: int = 6,
        max_generations: int = 3,
        inertia: float = 0.7,
        cognitive: float = 1.5,
        social: float = 1.5,
    ):
        self.available_tools = available_tools
        self.swarm_size = swarm_size
        self.max_generations = max_generations
        self.inertia = inertia
        self.cognitive = cognitive
        self.social = social

    def _random_config(self, particle_id: int) -> AgentConfig:
        """Generate a random agent configuration."""
        prompt = random.choice(AGENT_PROMPTS)
        temp = round(random.uniform(*TEMPERATURE_RANGE), 2)
        max_iter = random.randint(*MAX_ITERATIONS_RANGE)

        # Random tool subset (at least 1 tool)
        num_tools = random.randint(1, len(self.available_tools))
        tools = random.sample(self.available_tools, num_tools)

        return AgentConfig(
            id=f"pso-agent-{particle_id}",
            name=f"PSO Agent {particle_id}",
            system_prompt=prompt,
            temperature=temp,
            tools=sorted(tools),
            max_iterations=max_iter,
            metadata={"source": "pso", "particle_id": particle_id},
        )

    def _mutate_config(self, config: AgentConfig, global_best: AgentConfig) -> AgentConfig:
        """Mutate a config, influenced by personal best and global best."""
        new_config = AgentConfig(
            id=config.id,
            name=config.name,
            system_prompt=config.system_prompt,
            temperature=config.temperature,
            tools=list(config.tools),
            max_iterations=config.max_iterations,
            metadata=dict(config.metadata),
        )

        # Temperature mutation (continuous — PSO-style velocity)
        r1, r2 = random.random(), random.random()
        delta_temp = (
            self.inertia * random.uniform(-0.2, 0.2) +
            self.cognitive * r1 * (global_best.temperature - config.temperature) * 0.3 +
            self.social * r2 * random.uniform(-0.1, 0.1)
        )
        new_config.temperature = round(
            max(0.1, min(1.0, config.temperature + delta_temp)), 2
        )

        # Tool mutation (discrete — swap/add/remove one tool)
        if random.random() < 0.4 and self.available_tools:
            action = random.choice(["add", "remove", "swap"])
            current_tools = set(new_config.tools)

            if action == "add":
                available = set(self.available_tools) - current_tools
                if available:
                    current_tools.add(random.choice(list(available)))
            elif action == "remove" and len(current_tools) > 1:
                current_tools.remove(random.choice(list(current_tools)))
            elif action == "swap" and len(current_tools) > 0:
                available = set(self.available_tools) - current_tools
                if available:
                    current_tools.remove(random.choice(list(current_tools)))
                    current_tools.add(random.choice(list(available)))

            new_config.tools = sorted(current_tools)

        # Prompt mutation (discrete — occasionally change prompt)
        if random.random() < 0.2:
            new_config.system_prompt = random.choice(AGENT_PROMPTS)

        # Max iterations mutation
        if random.random() < 0.3:
            new_config.max_iterations = max(
                5, min(15, config.max_iterations + random.randint(-2, 2))
            )

        return new_config

    async def optimize(
        self, fitness_fn, purpose: str = ""
    ) -> PSOResult:
        """Run PSO optimization to find the best agent config.

        Args:
            fitness_fn: async callable(AgentConfig) -> float (0.0 to 1.0)
                Evaluates how good an agent config is for the given purpose.
            purpose: Description of what the agent should be good at.

        Returns:
            PSOResult with the best configuration found.
        """
        # Initialize swarm
        particles = []
        for i in range(self.swarm_size):
            config = self._random_config(i)
            particle = Particle(id=i, config=config)
            particles.append(particle)

        global_best_fitness = 0.0
        global_best_config = particles[0].config
        history = []
        total_evaluations = 0

        for gen in range(self.max_generations):
            gen_best = 0.0

            for particle in particles:
                # Evaluate fitness
                try:
                    particle.fitness = await fitness_fn(particle.config)
                    total_evaluations += 1
                except Exception as e:
                    logger.warning(f"Fitness eval failed for particle {particle.id}: {e}")
                    particle.fitness = 0.0

                # Update personal best
                if particle.fitness > particle.best_fitness:
                    particle.best_fitness = particle.fitness
                    particle.best_config = AgentConfig(**{
                        k: list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v
                        for k, v in particle.config.to_dict().items()
                    })

                # Update global best
                if particle.fitness > global_best_fitness:
                    global_best_fitness = particle.fitness
                    global_best_config = AgentConfig(**{
                        k: list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v
                        for k, v in particle.config.to_dict().items()
                    })

                gen_best = max(gen_best, particle.fitness)

            history.append({
                "generation": gen + 1,
                "best_fitness": round(gen_best, 4),
                "global_best": round(global_best_fitness, 4),
                "particles": [p.to_dict() for p in particles],
            })

            logger.info(
                f"Generation {gen + 1}: best={gen_best:.4f} "
                f"global_best={global_best_fitness:.4f}"
            )

            # Mutate particles for next generation (skip last gen)
            if gen < self.max_generations - 1:
                for particle in particles:
                    particle.config = self._mutate_config(
                        particle.config, global_best_config
                    )

        # Set final best config ID
        global_best_config.id = "pso-best"
        global_best_config.name = f"PSO Optimized Agent{' — ' + purpose if purpose else ''}"
        global_best_config.metadata["source"] = "pso"
        global_best_config.metadata["fitness"] = global_best_fitness

        return PSOResult(
            best_config=global_best_config,
            best_fitness=global_best_fitness,
            iterations=self.max_generations,
            particles_evaluated=total_evaluations,
            history=history,
        )
