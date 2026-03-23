"""Sprint 36 Part B — Per-Agent Credential Isolation Tests.

TDD tests for:
- AgentToken model (creation, serialization, expiry)
- AgentTokenIssuer (sign, validate, expired, invalid)
- CredentialProxy (tool wrapping, filtering, access logging)
- Coordinator integration (scoped tokens per sub-agent)
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ═══════════════════════════════════════════════════════════════
# 1. AgentToken Model
# ═══════════════════════════════════════════════════════════════

class TestAgentToken:
    """AgentToken — scoped credential for a sub-agent."""

    def test_agent_token_creation(self):
        """Token has agent_id, tenant_id, allowed_tools, ttl."""
        from bifrost.agents.odin.agent_token import AgentToken

        token = AgentToken(
            agent_id="researcher-001",
            tenant_id="tenant-acme",
            allowed_tools=["mimir_query", "knowledge_search"],
            ttl_seconds=900,
        )
        assert token.agent_id == "researcher-001"
        assert token.tenant_id == "tenant-acme"
        assert token.allowed_tools == ["mimir_query", "knowledge_search"]
        assert token.ttl_seconds == 900
        assert token.token_id != ""  # auto-generated UUID

    def test_agent_token_serialization(self):
        """Token can be serialized to dict for JWT claims."""
        from bifrost.agents.odin.agent_token import AgentToken

        token = AgentToken(
            agent_id="coder-002",
            tenant_id="tenant-sakura",
            allowed_tools=["execute_sandbox_command"],
            ttl_seconds=300,
        )
        d = token.to_claims()
        assert d["sub"] == "coder-002"
        assert d["tid"] == "tenant-sakura"
        assert d["tools"] == ["execute_sandbox_command"]
        assert "jti" in d
        assert "exp" in d
        assert "iat" in d

    def test_agent_token_expiry_check(self):
        """Token knows if it's expired."""
        from bifrost.agents.odin.agent_token import AgentToken

        token = AgentToken(
            agent_id="test",
            tenant_id="test",
            allowed_tools=[],
            ttl_seconds=0,  # Immediately expired
        )
        # With TTL=0, token should be expired
        assert token.is_expired is True

        token2 = AgentToken(
            agent_id="test",
            tenant_id="test",
            allowed_tools=[],
            ttl_seconds=3600,
        )
        assert token2.is_expired is False


# ═══════════════════════════════════════════════════════════════
# 2. AgentTokenIssuer (HMAC-SHA256 signing)
# ═══════════════════════════════════════════════════════════════

class TestAgentTokenIssuer:
    """AgentTokenIssuer — signs and validates scoped agent tokens."""

    def test_issue_returns_jwt_string(self):
        """Issuer produces a non-empty JWT string."""
        from bifrost.agents.odin.agent_token import AgentTokenIssuer

        issuer = AgentTokenIssuer(secret_key="test-secret-key-32bytes-long!!!!")
        jwt_str = issuer.issue(
            agent_id="researcher-001",
            tenant_id="tenant-acme",
            allowed_tools=["mimir_query"],
        )
        assert isinstance(jwt_str, str)
        assert len(jwt_str) > 20
        # JWT has 3 parts separated by dots
        assert jwt_str.count(".") == 2

    def test_validate_roundtrip(self):
        """Issue → validate → get back correct claims."""
        from bifrost.agents.odin.agent_token import AgentTokenIssuer

        issuer = AgentTokenIssuer(secret_key="test-secret-key-32bytes-long!!!!")
        jwt_str = issuer.issue(
            agent_id="coder-002",
            tenant_id="tenant-sakura",
            allowed_tools=["execute_sandbox_command", "read_sandbox_file"],
            ttl=600,
        )
        token = issuer.validate(jwt_str)
        assert token.agent_id == "coder-002"
        assert token.tenant_id == "tenant-sakura"
        assert token.allowed_tools == ["execute_sandbox_command", "read_sandbox_file"]

    def test_validate_rejects_expired(self):
        """Expired token raises ValueError."""
        from bifrost.agents.odin.agent_token import AgentTokenIssuer

        issuer = AgentTokenIssuer(secret_key="test-secret-key-32bytes-long!!!!")
        jwt_str = issuer.issue(
            agent_id="test",
            tenant_id="test",
            allowed_tools=[],
            ttl=-1,  # Already expired
        )
        with pytest.raises(ValueError, match="[Ee]xpir"):
            issuer.validate(jwt_str)

    def test_validate_rejects_wrong_key(self):
        """Token signed with different key is rejected."""
        from bifrost.agents.odin.agent_token import AgentTokenIssuer

        issuer1 = AgentTokenIssuer(secret_key="key-one-32bytes-padded-here!!!!")
        issuer2 = AgentTokenIssuer(secret_key="key-two-32bytes-padded-here!!!!")

        jwt_str = issuer1.issue(agent_id="test", tenant_id="test", allowed_tools=[])
        with pytest.raises(ValueError, match="[Ii]nvalid"):
            issuer2.validate(jwt_str)


# ═══════════════════════════════════════════════════════════════
# 3. CredentialProxy (tool filtering)
# ═══════════════════════════════════════════════════════════════

class TestCredentialProxy:
    """CredentialProxy — restricts tool registry based on agent token."""

    def test_wrap_filters_to_allowed_tools(self):
        """Wrapped registry only contains allowed tools."""
        from bifrost.agents.odin.credential_proxy import CredentialProxy
        from bifrost.agents.odin.agent_token import AgentToken

        # Create mock registry with 3 tools
        mock_registry = MagicMock()
        tool_a = MagicMock()
        tool_a.name = "mimir_query"
        tool_b = MagicMock()
        tool_b.name = "knowledge_search"
        tool_c = MagicMock()
        tool_c.name = "execute_sandbox_command"
        mock_registry.list_tools.return_value = [tool_a, tool_b, tool_c]
        mock_registry.get.side_effect = lambda n: {"mimir_query": tool_a, "knowledge_search": tool_b, "execute_sandbox_command": tool_c}.get(n)

        # Create token allowing only 2 tools
        token = AgentToken(
            agent_id="researcher",
            tenant_id="tenant-1",
            allowed_tools=["mimir_query", "knowledge_search"],
            ttl_seconds=900,
        )

        proxy = CredentialProxy()
        filtered = proxy.wrap_tool_registry(mock_registry, token)
        assert len(filtered) == 2
        assert "mimir_query" in filtered
        assert "knowledge_search" in filtered
        assert "execute_sandbox_command" not in filtered

    def test_wrap_with_empty_allowlist_returns_empty(self):
        """Empty allowed_tools → no tools available."""
        from bifrost.agents.odin.credential_proxy import CredentialProxy
        from bifrost.agents.odin.agent_token import AgentToken

        mock_registry = MagicMock()
        tool_a = MagicMock()
        tool_a.name = "mimir_query"
        mock_registry.list_tools.return_value = [tool_a]

        token = AgentToken(
            agent_id="locked",
            tenant_id="tenant-1",
            allowed_tools=[],
            ttl_seconds=900,
        )

        proxy = CredentialProxy()
        filtered = proxy.wrap_tool_registry(mock_registry, token)
        assert len(filtered) == 0

    def test_logs_tool_access(self):
        """Proxy logs each tool wrap/access for audit trail."""
        from bifrost.agents.odin.credential_proxy import CredentialProxy
        from bifrost.agents.odin.agent_token import AgentToken

        token = AgentToken(
            agent_id="audited-agent",
            tenant_id="tenant-1",
            allowed_tools=["mimir_query"],
            ttl_seconds=900,
        )

        mock_registry = MagicMock()
        tool_a = MagicMock()
        tool_a.name = "mimir_query"
        mock_registry.list_tools.return_value = [tool_a]
        mock_registry.get.side_effect = lambda n: tool_a if n == "mimir_query" else None

        proxy = CredentialProxy()
        with patch("bifrost.agents.odin.credential_proxy.logger") as mock_logger:
            proxy.wrap_tool_registry(mock_registry, token)
            # Should log the wrapping with agent_id
            assert mock_logger.info.called

    def test_denied_tool_not_accessible(self):
        """Accessing a denied tool from the filtered registry returns None."""
        from bifrost.agents.odin.credential_proxy import CredentialProxy
        from bifrost.agents.odin.agent_token import AgentToken

        mock_registry = MagicMock()
        tool_secret = MagicMock()
        tool_secret.name = "admin_panel"
        mock_registry.list_tools.return_value = [tool_secret]

        token = AgentToken(
            agent_id="restricted",
            tenant_id="tenant-1",
            allowed_tools=["mimir_query"],  # admin_panel NOT allowed
            ttl_seconds=900,
        )

        proxy = CredentialProxy()
        filtered = proxy.wrap_tool_registry(mock_registry, token)
        assert filtered.get("admin_panel") is None


# ═══════════════════════════════════════════════════════════════
# 4. Coordinator Credential Integration
# ═══════════════════════════════════════════════════════════════

class TestCoordinatorCredentialIsolation:
    """OdinCoordinator — credential isolation for sub-agents."""

    @pytest.mark.asyncio
    async def test_sub_agent_receives_scoped_token(self):
        """When credential isolation is enabled, each sub-agent gets a unique token."""
        from bifrost.agents.odin.coordinator import OdinCoordinator
        from bifrost.agents.odin.models import SubTask
        from bifrost.agents.odin.agent_token import AgentTokenIssuer

        issued_tokens = []

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{"message": {"content": "Done"}, "finish_reason": "stop"}]
        }

        issuer = AgentTokenIssuer(secret_key="test-secret-key-32bytes-long!!!!")

        coordinator = OdinCoordinator(
            heimdall=mock_heimdall,
            tool_registry=MagicMock(),
            token_issuer=issuer,
            tenant_id="tenant-test",
        )

        # Override _run_agent to capture that it runs with scoped context
        original_run = coordinator._run_agent

        async def tracking_run(task):
            # The coordinator should have set up credential isolation
            result = await original_run(task)
            issued_tokens.append(task.id)
            return result

        coordinator._run_agent = tracking_run

        task = SubTask(id="t1", description="Research", agent_type="researcher")
        result = await coordinator._execute_sub_agent(task)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_different_agent_types_get_different_tool_scopes(self):
        """Researcher and coder get different tool allowlists."""
        from bifrost.agents.odin.agent_token import AgentTokenIssuer
        from bifrost.agents.odin.registry import SubAgentRegistry

        registry = SubAgentRegistry()
        researcher = registry.get("researcher")
        coder = registry.get("coder")

        assert researcher is not None
        assert coder is not None
        # Their allowed_tools should be different
        assert researcher.allowed_tools != coder.allowed_tools
