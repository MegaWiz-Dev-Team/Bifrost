"""Context middleware — trigger-based context window management.

Monitors conversation length and compresses when triggers fire:
- Message count exceeds threshold
- Estimated token count exceeds threshold

Keeps recent messages verbatim, summarizes older messages.
Inspired by DeerFlow's context engineering approach.
"""

import logging
from dataclasses import dataclass

from bifrost.context.summarizer import Summarizer

logger = logging.getLogger("bifrost.context")


@dataclass
class ContextConfig:
    """Configuration for context compression triggers."""

    max_messages: int = 20
    """Compress when conversation exceeds this many messages."""

    max_tokens: int = 6000
    """Compress when estimated token count exceeds this limit."""

    recent_messages_to_keep: int = 6
    """Number of most recent messages to keep verbatim (not summarized)."""


class ContextMiddleware:
    """Middleware that compresses conversation context when triggers fire."""

    # Rough estimate: ~1.3 tokens per word (English average)
    TOKENS_PER_WORD = 1.3

    def __init__(self, summarizer: Summarizer, config: ContextConfig | None = None):
        self.summarizer = summarizer
        self.config = config or ContextConfig()

    def estimate_tokens(self, messages: list[dict]) -> int:
        """Estimate token count for a list of messages.

        Uses word-count * 1.3 as a rough approximation.
        """
        total_words = 0
        for msg in messages:
            content = msg.get("content", "")
            if content:
                total_words += len(content.split())
        return int(total_words * self.TOKENS_PER_WORD)

    def should_compress(self, messages: list[dict]) -> bool:
        """Check if any compression trigger fires.

        Returns True if:
        - Message count > max_messages, OR
        - Estimated tokens > max_tokens
        """
        if len(messages) > self.config.max_messages:
            return True
        if self.estimate_tokens(messages) > self.config.max_tokens:
            return True
        return False

    async def compress(self, messages: list[dict]) -> list[dict]:
        """Compress messages if triggers fire.

        Strategy: keep the most recent N messages verbatim,
        summarize everything older into a single system message.

        Args:
            messages: Full conversation message list.

        Returns:
            Compressed message list (or original if no trigger fired).
        """
        if not self.should_compress(messages):
            return messages

        keep_count = self.config.recent_messages_to_keep
        if len(messages) <= keep_count:
            return messages

        # Split into old (to summarize) and recent (to keep)
        old_messages = messages[:-keep_count]
        recent_messages = messages[-keep_count:]

        # Summarize old messages
        summary = await self.summarizer.summarize(old_messages)

        if not summary:
            # If summarization fails, fall back to keeping all messages
            return messages

        # Build compressed history
        compressed = [
            {
                "role": "system",
                "content": f"[Previous conversation summary]\n{summary}",
            },
        ]
        compressed.extend(recent_messages)

        logger.info(
            f"Context compressed: {len(messages)} messages → {len(compressed)} "
            f"(summarized {len(old_messages)} old messages)"
        )
        return compressed

    async def process(self, messages: list[dict]) -> list[dict]:
        """Process messages through the context middleware.

        Convenience method that checks triggers and compresses if needed.
        """
        return await self.compress(messages)
