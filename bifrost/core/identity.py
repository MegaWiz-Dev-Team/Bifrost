"""Agent Identity — rich persona model and system prompt builder.

Provides structured agent identity with persona, capabilities, constraints,
knowledge domains, and automatic system prompt generation.
"""

import logging

from pydantic import BaseModel, Field

from bifrost.core.agents import AgentConfig

logger = logging.getLogger("bifrost.identity")


class AgentIdentity(BaseModel):
    """Rich identity model for an AI agent.

    Goes beyond simple system_prompt to provide structured persona,
    capabilities, constraints, and knowledge domains.
    """

    # Required
    agent_id: str
    persona_name: str
    persona_role: str

    # Persona details
    persona_description: str = ""
    language: str = "th"  # Primary language: th, en, etc.
    tone: str = "professional"  # professional, friendly, empathetic, formal

    # Capabilities and constraints
    capabilities: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    knowledge_domains: list[str] = Field(default_factory=list)

    # LLM settings
    model: str | None = None
    temperature: float = 0.7
    tools: list[str] = Field(default_factory=list)
    max_iterations: int = 10

    # Schema version
    version: int = 1


class SystemPromptBuilder:
    """Builds system prompts from AgentIdentity."""

    @staticmethod
    def build(identity: AgentIdentity) -> str:
        """Generate a complete system prompt from an identity."""
        sections: list[str] = []

        # ── Persona ──
        persona_line = f"You are {identity.persona_name}, a {identity.persona_role}."
        if identity.persona_description:
            persona_line += f" {identity.persona_description}"
        sections.append(persona_line)

        # ── Language ──
        if identity.language == "th":
            sections.append("ตอบเป็นภาษาไทยเสมอ ยกเว้นคำศัพท์เฉพาะทาง (Respond in Thai)")
        elif identity.language == "en":
            sections.append("Always respond in English.")
        else:
            sections.append(f"Respond in {identity.language}.")

        # ── Tone ──
        tone_map = {
            "professional": "Maintain a professional and courteous tone.",
            "friendly": "Be warm, approachable, and conversational.",
            "empathetic": "Show empathy and understanding in your responses.",
            "formal": "Use formal language and proper honorifics.",
        }
        if identity.tone in tone_map:
            sections.append(tone_map[identity.tone])

        # ── Capabilities ──
        if identity.capabilities:
            caps = "\n".join(f"- {c}" for c in identity.capabilities)
            sections.append(f"Your capabilities:\n{caps}")

        # ── Knowledge Domains ──
        if identity.knowledge_domains:
            domains = ", ".join(identity.knowledge_domains)
            sections.append(f"Your areas of expertise: {domains}.")

        # ── Constraints ──
        if identity.constraints:
            rules = "\n".join(f"- {c}" for c in identity.constraints)
            sections.append(f"Rules you MUST follow:\n{rules}")

        return "\n\n".join(sections)


def identity_to_config(identity: AgentIdentity) -> AgentConfig:
    """Convert an AgentIdentity to an AgentConfig with built system prompt."""
    system_prompt = SystemPromptBuilder.build(identity)

    return AgentConfig(
        id=identity.agent_id,
        name=identity.persona_name,
        system_prompt=system_prompt,
        model=identity.model,
        temperature=identity.temperature,
        tools=identity.tools,
        max_iterations=identity.max_iterations,
        metadata={
            "identity_version": identity.version,
            "persona_role": identity.persona_role,
            "language": identity.language,
        },
    )
