"""Memory updater — LLM-based fact extraction from conversations.

Extracts persistent facts, preferences, and context from conversation
messages using the LLM. Extracted facts are deduplicated before storage.
"""

import json
import logging

logger = logging.getLogger("bifrost.memory")

EXTRACTION_PROMPT = """You are a memory extraction system. Analyze the conversation below and extract key facts worth remembering across sessions.

Extract:
- User preferences (language, communication style, format preferences)
- User context (role, organization, specialty, location)
- Important facts (relationships, goals, recurring topics)
- Medical context (diagnoses, allergies, medications — if applicable)

Rules:
- Return ONLY a JSON array of strings, e.g. ["fact 1", "fact 2"]
- Each fact should be a single, concise statement
- Skip trivial or transient information (greetings, small talk)
- If no meaningful facts are found, return []

Conversation:
"""


class MemoryUpdater:
    """Extract persistent facts from conversations using LLM."""

    def __init__(self, heimdall, model: str | None = None):
        self.heimdall = heimdall
        self.model = model

    async def extract_facts(self, messages: list[dict]) -> list[str]:
        """Extract facts from conversation messages.

        Args:
            messages: List of message dicts with 'role' and 'content'.

        Returns:
            List of fact strings extracted by LLM.
        """
        if not messages:
            return []

        # Build conversation text
        conversation = "\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')}"
            for m in messages
            if m.get("content")
        )

        try:
            response = await self.heimdall.chat_completion(
                messages=[
                    {"role": "system", "content": EXTRACTION_PROMPT + conversation},
                    {"role": "user", "content": "Extract facts from the conversation above."},
                ],
                model=self.model,
                temperature=0.1,  # Low temperature for consistency
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Parse JSON array from response
            # Handle cases where LLM wraps in markdown code blocks
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            facts = json.loads(content)
            if isinstance(facts, list):
                return [str(f) for f in facts if f]
            return []

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"Failed to extract facts: {e}")
            return []
        except Exception as e:
            logger.error(f"Memory extraction error: {e}")
            return []
