"""Handover Context Builder — Escalate to human with context.

Builds a summary of the conversation for human handover,
including priority scoring based on urgency keywords.
"""

from dataclasses import dataclass
import re
from typing import List


@dataclass
class HandoverContext:
    """Context package for human handover."""
    summary: str
    priority: str  # "low", "medium", "high", "critical"
    message_count: int
    key_topics: List[str]


# Urgency keywords for priority scoring
_CRITICAL_KEYWORDS = re.compile(
    r'(เจ็บหน้าอก|หายใจไม่ออก|หมดสติ|เลือดออก|chest\s+pain|can\'t\s+breathe|unconscious|emergency)',
    re.IGNORECASE,
)

_HIGH_KEYWORDS = re.compile(
    r'(ปวดมาก|ไข้สูง|อาเจียน|ท้องเสีย|severe|high\s+fever|vomiting|urgent)',
    re.IGNORECASE,
)

_MEDIUM_KEYWORDS = re.compile(
    r'(ปวด|ไม่สบาย|เป็นไข้|pain|sick|fever|ไม่หาย|worry)',
    re.IGNORECASE,
)


def build_handover_context(messages: List[dict]) -> HandoverContext:
    """Build handover context from conversation messages.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.

    Returns:
        HandoverContext with summary, priority, and key topics.
    """
    if not messages:
        return HandoverContext(
            summary="",
            priority="low",
            message_count=0,
            key_topics=[],
        )

    # Build summary from user messages
    user_messages = [m["content"] for m in messages if m.get("role") == "user"]
    all_text = " ".join(m.get("content", "") for m in messages)
    summary = " | ".join(user_messages) if user_messages else all_text[:200]

    # Priority scoring
    priority = "low"
    if _MEDIUM_KEYWORDS.search(all_text):
        priority = "medium"
    if _HIGH_KEYWORDS.search(all_text):
        priority = "high"
    if _CRITICAL_KEYWORDS.search(all_text):
        priority = "critical"

    # Extract key topics (simple keyword extraction)
    key_topics = []
    if user_messages:
        # Use first user message as main topic
        key_topics.append(user_messages[0][:50])

    return HandoverContext(
        summary=summary,
        priority=priority,
        message_count=len(messages),
        key_topics=key_topics,
    )
