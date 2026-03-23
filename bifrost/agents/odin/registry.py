"""Sub-agent type registry — defines and manages sub-agent types.

Each sub-agent type has a tailored system prompt and allowed tools.
Built-in types: general, researcher, coder, medical, devops.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("bifrost.odin.registry")


@dataclass
class SubAgentType:
    """Configuration for a sub-agent type.

    Attributes:
        name: Unique name for this type (e.g., 'researcher', 'coder').
        system_prompt: System prompt tailored for this agent type.
        allowed_tools: List of tool names this type can use.
        model_override: Optional model override (None = use coordinator default).
    """
    name: str
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    model_override: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "system_prompt": self.system_prompt[:200],
            "allowed_tools": self.allowed_tools,
            "model_override": self.model_override,
        }


# ─── Built-in agent type definitions ───

BUILTIN_TYPES: list[SubAgentType] = [
    SubAgentType(
        name="general",
        system_prompt=(
            "You are a helpful general-purpose AI assistant. "
            "Answer questions accurately and thoroughly. "
            "Use available tools when they can help provide better answers. "
            "Be concise but comprehensive. Respond in the same language as the request."
        ),
        allowed_tools=[],
    ),
    SubAgentType(
        name="researcher",
        system_prompt=(
            "You are a research specialist. Your job is to investigate, gather information, "
            "and provide well-sourced answers. Focus on:\n"
            "- Finding relevant information from knowledge bases\n"
            "- Cross-referencing multiple sources\n"
            "- Summarizing findings clearly with citations\n"
            "- Identifying gaps in available information\n"
            "Be thorough but structured in your research output."
        ),
        allowed_tools=["mimir_query", "knowledge_search", "web_search"],
    ),
    SubAgentType(
        name="coder",
        system_prompt=(
            "You are an expert software engineer. Your job is to write, analyze, "
            "and debug code. Focus on:\n"
            "- Writing clean, well-documented code\n"
            "- Following best practices and design patterns\n"
            "- Providing clear explanations of your code\n"
            "- Suggesting tests for your implementations\n"
            "Always consider security, performance, and maintainability."
        ),
        allowed_tools=["execute_sandbox_command", "read_sandbox_file", "write_sandbox_file"],
    ),
    SubAgentType(
        name="medical",
        system_prompt=(
            "You are a medical AI assistant operating under strict clinical guidelines. "
            "Your job is to help with medical information and clinical workflows. Focus on:\n"
            "- Providing evidence-based medical information\n"
            "- Supporting clinical decision-making (never replacing physician judgment)\n"
            "- Maintaining patient privacy (HIPAA compliance)\n"
            "- Citing clinical sources and guidelines\n"
            "IMPORTANT: Always include appropriate disclaimers. You do NOT provide diagnoses."
        ),
        allowed_tools=["patient_search", "fhir_query", "mimir_query"],
    ),
    SubAgentType(
        name="devops",
        system_prompt=(
            "You are a DevOps and infrastructure specialist. Your job is to help with "
            "deployment, monitoring, and infrastructure tasks. Focus on:\n"
            "- Container and service management\n"
            "- CI/CD pipeline operations\n"
            "- Security scanning and vulnerability management\n"
            "- Infrastructure monitoring and alerting\n"
            "Always prioritize safety — confirm destructive actions before executing."
        ),
        allowed_tools=["container_status", "restart_service", "zap_scan", "semgrep_scan"],
    ),
]


class SubAgentRegistry:
    """Registry for sub-agent types.

    Manages the available sub-agent type configurations.
    Pre-loaded with 5 built-in types; supports custom type registration.
    """

    def __init__(self):
        self._types: dict[str, SubAgentType] = {}
        # Register built-in types
        for agent_type in BUILTIN_TYPES:
            self._types[agent_type.name] = agent_type

    def register(self, agent_type: SubAgentType) -> None:
        """Register a new agent type or override an existing one."""
        self._types[agent_type.name] = agent_type
        logger.info(f"Registered sub-agent type: {agent_type.name}")

    def get(self, name: str) -> SubAgentType | None:
        """Get an agent type by name. Returns None if not found."""
        return self._types.get(name)

    def list_types(self) -> list[SubAgentType]:
        """List all registered agent types."""
        return list(self._types.values())

    def __len__(self) -> int:
        return len(self._types)

    def __contains__(self, name: str) -> bool:
        return name in self._types
