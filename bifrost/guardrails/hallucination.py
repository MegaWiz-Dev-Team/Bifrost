"""Hallucination Detection — Grounding check for LLM responses.

Compares LLM response against source documents to detect hallucinations.
Uses token overlap (Jaccard-like) for Sprint 8 — can upgrade to LLM-based in S9.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class GroundingResult:
    """Result of grounding check."""
    grounded: bool
    score: float  # 0.0 to 1.0
    details: str = ""


def _tokenize(text: str) -> set[str]:
    """Simple whitespace tokenizer with Thai support."""
    # Split on whitespace + common Thai/English punctuation
    tokens = set()
    for word in text.lower().split():
        cleaned = word.strip(".,!?()[]{}\"'")
        if len(cleaned) >= 2:  # Skip single chars
            tokens.add(cleaned)
    return tokens


def check_grounding(
    response: str,
    sources: List[str],
    threshold: float = 0.5,
) -> GroundingResult:
    """Check if response is grounded in source documents.

    Uses token overlap score. Score >= threshold → grounded.

    Args:
        response: The LLM response text.
        sources: List of source document texts.
        threshold: Minimum score to consider grounded (default 0.5).

    Returns:
        GroundingResult with grounded flag and score.
    """
    if not sources or not response.strip():
        return GroundingResult(
            grounded=False,
            score=0.0,
            details="No sources provided" if not sources else "Empty response",
        )

    response_tokens = _tokenize(response)
    if not response_tokens:
        return GroundingResult(grounded=False, score=0.0, details="No tokens in response")

    # Combine all source tokens
    source_tokens: set[str] = set()
    for source in sources:
        source_tokens.update(_tokenize(source))

    if not source_tokens:
        return GroundingResult(grounded=False, score=0.0, details="No tokens in sources")

    # Calculate overlap score (proportion of response tokens found in sources)
    overlap = response_tokens & source_tokens
    score = len(overlap) / len(response_tokens)

    grounded = score >= threshold

    return GroundingResult(
        grounded=grounded,
        score=round(score, 3),
        details=f"{len(overlap)}/{len(response_tokens)} tokens grounded (threshold={threshold})",
    )
