"""Credential Proxy — restricts tool access based on agent tokens.

Wraps a ToolRegistry to filter tools to only those allowed
by the agent's scoped token. Provides an audit trail of access.
"""

from __future__ import annotations

import logging

from bifrost.agents.odin.agent_token import AgentToken
from bifrost.tools.registry import ToolRegistry

logger = logging.getLogger("bifrost.odin.credential_proxy")


class CredentialProxy:
    """Proxy that filters tool registries based on agent tokens.

    Sub-agents receive a filtered view of the tool registry
    containing only the tools their token permits.
    """

    def wrap_tool_registry(
        self,
        registry: ToolRegistry,
        token: AgentToken,
    ) -> ToolRegistry:
        """Create a filtered copy of the tool registry.

        Args:
            registry: Full tool registry with all available tools.
            token: Scoped agent token with allowed_tools list.

        Returns:
            New ToolRegistry containing only permitted tools.
        """
        allowed_set = set(token.allowed_tools)
        filtered = ToolRegistry()

        for tool in registry.list_tools():
            if tool.name in allowed_set:
                filtered.register(tool)

        logger.info(
            f"Credential proxy: agent={token.agent_id} "
            f"allowed={len(allowed_set)} granted={len(filtered)} "
            f"tools={[t.name for t in filtered.list_tools()]}"
        )

        return filtered
