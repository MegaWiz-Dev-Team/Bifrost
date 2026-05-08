"""Sprint 3 TDD — Mimir Cross-Service Intelligence.

Tests: cross-tenant query, service graph, webhook registration.

Run: python -m pytest tests/test_cross_service.py -v
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ═══════════════════════════════════════════
# 1. Cross-Tenant Query
# ═══════════════════════════════════════════


@pytest.mark.asyncio
async def test_cross_tenant_query():
    """cross_tenant_query searches across multiple tenant knowledge bases."""
    from bifrost.clients.mimir_knowledge import MimirKnowledgeClient

    client = MimirKnowledgeClient(mimir_url="http://test:4200")

    # Mock query_tenant to return results per tenant
    async def mock_query(tenant, question):
        return {
            "answer": f"{tenant} says: relevant info",
            "sources": [{"content": f"From {tenant}", "score": 0.9}],
        }

    with patch.object(client, "query_tenant", side_effect=mock_query):
        results = await client.cross_tenant_query(
            question="How do Huginn and Muninn work together?",
            tenants=["huginn", "muninn"],
        )

    assert len(results) == 2
    assert any("huginn" in r["answer"] for r in results)
    assert any("muninn" in r["answer"] for r in results)


# ═══════════════════════════════════════════
# 2. Service Relationship Graph
# ═══════════════════════════════════════════


def test_service_graph():
    """get_service_graph returns service dependency relationships."""
    from bifrost.clients.mimir_knowledge import MimirKnowledgeClient

    client = MimirKnowledgeClient()
    graph = client.get_service_graph()

    assert isinstance(graph, dict)
    assert "nodes" in graph
    assert "edges" in graph
    assert len(graph["nodes"]) == 12

    # Bifrost should depend on Heimdall
    bifrost_edges = [e for e in graph["edges"] if e["from"] == "bifrost"]
    assert any(e["to"] == "heimdall" for e in bifrost_edges)


# ═══════════════════════════════════════════
# 3. Webhook Registration
# ═══════════════════════════════════════════


@pytest.mark.asyncio
async def test_webhook_registration():
    """register_webhook stores webhook URL for auto-refresh."""
    from bifrost.clients.mimir_knowledge import MimirKnowledgeClient

    client = MimirKnowledgeClient()

    result = client.register_webhook(
        tenant="fenrir",
        url="http://localhost:8200/hooks/git-push",
    )

    assert result["tenant"] == "fenrir"
    assert result["url"] == "http://localhost:8200/hooks/git-push"
    assert result["status"] == "registered"

    # Verify it's stored
    hooks = client.list_webhooks()
    assert len(hooks) >= 1
    assert any(h["tenant"] == "fenrir" for h in hooks)
