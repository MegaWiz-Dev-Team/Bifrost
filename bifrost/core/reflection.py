"""Self-reflection loop — evaluate and improve own output.

After generating a response, the agent critiques its own work
and optionally retries for a better result.
"""

import logging
from dataclasses import dataclass

from bifrost.clients.heimdall import HeimdallClient

logger = logging.getLogger("bifrost.reflection")


REFLECTION_PROMPT = """You are a critical evaluator. Review the following AI-generated response and evaluate its quality.

Original user request: {user_input}

AI response to evaluate:
{response}

Evaluate on these criteria (score 1-5 each):
1. Accuracy — Is the information correct?
2. Completeness — Does it fully address the request?
3. Clarity — Is it clear and well-structured?
4. Helpfulness — Is it practically useful?

Output EXACTLY this format:
ACCURACY: <score>
COMPLETENESS: <score>
CLARITY: <score>
HELPFULNESS: <score>
OVERALL: <average score>
CRITIQUE: <1-2 sentence critique>
SHOULD_RETRY: <yes/no>
IMPROVEMENT: <specific improvement suggestion if retry needed>"""


@dataclass
class ReflectionResult:
    """Result of a self-reflection evaluation."""
    accuracy: int = 0
    completeness: int = 0
    clarity: int = 0
    helpfulness: int = 0
    overall: float = 0.0
    critique: str = ""
    should_retry: bool = False
    improvement: str = ""

    def to_dict(self) -> dict:
        return {
            "accuracy": self.accuracy,
            "completeness": self.completeness,
            "clarity": self.clarity,
            "helpfulness": self.helpfulness,
            "overall": self.overall,
            "critique": self.critique,
            "should_retry": self.should_retry,
            "improvement": self.improvement,
        }

    @property
    def passed(self) -> bool:
        """Did the response pass quality threshold?"""
        return self.overall >= 3.5


def _parse_reflection(text: str) -> ReflectionResult:
    """Parse the structured reflection output."""
    result = ReflectionResult()

    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("ACCURACY:"):
            try:
                result.accuracy = int(line.split(":")[1].strip())
            except ValueError:
                pass
        elif line.startswith("COMPLETENESS:"):
            try:
                result.completeness = int(line.split(":")[1].strip())
            except ValueError:
                pass
        elif line.startswith("CLARITY:"):
            try:
                result.clarity = int(line.split(":")[1].strip())
            except ValueError:
                pass
        elif line.startswith("HELPFULNESS:"):
            try:
                result.helpfulness = int(line.split(":")[1].strip())
            except ValueError:
                pass
        elif line.startswith("OVERALL:"):
            try:
                result.overall = float(line.split(":")[1].strip())
            except ValueError:
                pass
        elif line.startswith("CRITIQUE:"):
            result.critique = line.split(":", 1)[1].strip()
        elif line.startswith("SHOULD_RETRY:"):
            val = line.split(":")[1].strip().lower()
            result.should_retry = val in ("yes", "true", "1")
        elif line.startswith("IMPROVEMENT:"):
            result.improvement = line.split(":", 1)[1].strip()

    # Calculate overall if not provided
    if result.overall == 0.0 and any([result.accuracy, result.completeness, result.clarity, result.helpfulness]):
        scores = [s for s in [result.accuracy, result.completeness, result.clarity, result.helpfulness] if s > 0]
        result.overall = sum(scores) / len(scores) if scores else 0.0

    return result


class SelfReflection:
    """Self-reflection loop for quality improvement."""

    def __init__(
        self,
        heimdall: HeimdallClient,
        max_retries: int = 2,
        quality_threshold: float = 3.5,
    ):
        self.heimdall = heimdall
        self.max_retries = max_retries
        self.quality_threshold = quality_threshold

    async def reflect(
        self, user_input: str, response: str, model: str | None = None
    ) -> ReflectionResult:
        """Evaluate a response quality."""
        prompt = REFLECTION_PROMPT.format(user_input=user_input, response=response)

        llm_response = await self.heimdall.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.2,
        )

        content = llm_response.get("choices", [{}])[0].get("message", {}).get("content", "")
        return _parse_reflection(content)

    async def reflect_and_improve(
        self, user_input: str, initial_response: str,
        executor_fn, model: str | None = None,
    ) -> tuple[str, list[ReflectionResult]]:
        """Reflect on response and retry if quality is low.

        Args:
            user_input: Original user request
            initial_response: First response to evaluate
            executor_fn: async callable(improvement_hint) -> str
            model: LLM model to use

        Returns:
            (final_response, list_of_reflections)
        """
        reflections = []
        current_response = initial_response

        for attempt in range(self.max_retries + 1):
            reflection = await self.reflect(user_input, current_response, model)
            reflections.append(reflection)

            logger.info(
                f"Reflection {attempt + 1}: overall={reflection.overall:.1f} "
                f"retry={reflection.should_retry}"
            )

            if reflection.overall >= self.quality_threshold or not reflection.should_retry:
                break

            if attempt < self.max_retries and reflection.improvement:
                logger.info(f"Retrying with improvement: {reflection.improvement[:100]}")
                try:
                    current_response = await executor_fn(
                        f"Previous attempt was insufficient. {reflection.improvement}\n\n"
                        f"Original request: {user_input}"
                    )
                except Exception as e:
                    logger.warning(f"Retry failed: {e}")
                    break

        return current_response, reflections
