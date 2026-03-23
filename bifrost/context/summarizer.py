"""Conversation summarizer — LLM-based message compression.

Summarizes older conversation messages to free up context window space
while preserving key information from the conversation history.
"""

import logging

logger = logging.getLogger("bifrost.context")

SUMMARIZATION_PROMPT = """Summarize the following conversation concisely. 
Preserve key facts, decisions, and context. 
Focus on information that would be important for continuing the conversation.
Return ONLY the summary, no preamble.

Conversation:
"""


class Summarizer:
    """LLM-based conversation summarizer."""

    def __init__(self, heimdall, model: str | None = None):
        self.heimdall = heimdall
        self.model = model

    async def summarize(self, messages: list[dict]) -> str:
        """Summarize a list of conversation messages.

        Args:
            messages: List of message dicts with 'role' and 'content'.

        Returns:
            Concise summary string, or empty string on error/empty input.
        """
        if not messages:
            return ""

        # Build conversation text
        conversation = "\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')}"
            for m in messages
            if m.get("content")
        )

        if not conversation.strip():
            return ""

        try:
            response = await self.heimdall.chat_completion(
                messages=[
                    {"role": "system", "content": SUMMARIZATION_PROMPT + conversation},
                    {"role": "user", "content": "Provide a concise summary."},
                ],
                model=self.model,
                temperature=0.1,
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip()

        except Exception as e:
            logger.warning(f"Summarization failed: {e}")
            return ""
