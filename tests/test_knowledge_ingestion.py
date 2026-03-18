"""Sprint 2 TDD — Mimir Knowledge Ingestion SDK.

Tests: tenant provisioning, doc ingestion, query, auto-provision, batch ingest.

Run: cd /Users/mimir/Developer/Bifrost && python -m pytest tests/test_knowledge_ingestion.py -v
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx


# ═══════════════════════════════════════════
# 1. Tenant Provisioning
# ═══════════════════════════════════════════


@pytest.mark.asyncio
async def test_provision_tenant():
    """MimirKnowledgeClient.provision_tenant creates a tenant via API."""
    from bifrost.clients.mimir_knowledge import MimirKnowledgeClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": 1, "name": "fenrir", "display_name": "Fenrir"}
    mock_response.raise_for_status = MagicMock()

    client = MimirKnowledgeClient(mimir_url="http://test:4200")
    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.provision_tenant("fenrir", "Fenrir — Browser Automation")

    assert result["name"] == "fenrir"


# ═══════════════════════════════════════════
# 2. Document Ingestion
# ═══════════════════════════════════════════


@pytest.mark.asyncio
async def test_ingest_markdown():
    """MimirKnowledgeClient.ingest_markdown pushes content to ingest API."""
    from bifrost.clients.mimir_knowledge import MimirKnowledgeClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"doc_id": "abc123", "chunks": 5}
    mock_response.raise_for_status = MagicMock()

    client = MimirKnowledgeClient(mimir_url="http://test:4200")
    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.ingest_markdown(
            tenant="fenrir",
            content="# Fenrir\nBrowser automation agent.",
            metadata={"source": "README.md"},
        )

    assert result["doc_id"] == "abc123"
    assert result["chunks"] == 5


# ═══════════════════════════════════════════
# 3. Tenant Query
# ═══════════════════════════════════════════


@pytest.mark.asyncio
async def test_query_tenant():
    """MimirKnowledgeClient.query_tenant sends query to tenant query API."""
    from bifrost.clients.mimir_knowledge import MimirKnowledgeClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "answer": "Fenrir is a browser automation agent.",
        "sources": [{"content": "Fenrir automates forms", "score": 0.95}],
    }
    mock_response.raise_for_status = MagicMock()

    client = MimirKnowledgeClient(mimir_url="http://test:4200")
    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.query_tenant("fenrir", "What is Fenrir?")

    assert "answer" in result
    assert "sources" in result


# ═══════════════════════════════════════════
# 4. Auto-Provision All 12 Tenants
# ═══════════════════════════════════════════


@pytest.mark.asyncio
async def test_auto_provision_all():
    """auto_provision_all creates all 12 service tenants."""
    from bifrost.clients.mimir_knowledge import MimirKnowledgeClient

    client = MimirKnowledgeClient(mimir_url="http://test:4200")

    # Mock provision to track calls
    call_names = []
    async def mock_provision(name, display=""):
        call_names.append(name)
        return {"name": name}

    with patch.object(client, "provision_tenant", side_effect=mock_provision):
        count = await client.auto_provision_all()

    assert count == 12
    assert "mimir" in call_names
    assert "bifrost" in call_names
    assert "heimdall" in call_names
    assert "fenrir" in call_names
    assert "ratatoskr" in call_names


# ═══════════════════════════════════════════
# 5. Batch Ingest Service Docs
# ═══════════════════════════════════════════


@pytest.mark.asyncio
async def test_ingest_service_docs():
    """ingest_service_docs ingests both README and ISO docs."""
    from bifrost.clients.mimir_knowledge import MimirKnowledgeClient

    client = MimirKnowledgeClient(mimir_url="http://test:4200")

    ingested = []
    async def mock_ingest(tenant, content, metadata=None):
        ingested.append({"tenant": tenant, "length": len(content)})
        return {"doc_id": f"doc-{len(ingested)}", "chunks": 3}

    with patch.object(client, "ingest_markdown", side_effect=mock_ingest):
        results = await client.ingest_service_docs(
            tenant="fenrir",
            readme_content="# Fenrir\nBrowser automation.",
            iso_content="## Implementation Report\nFenrir v0.2.0",
        )

    assert len(ingested) == 2  # README + ISO
    assert all(item["tenant"] == "fenrir" for item in ingested)
    assert len(results) == 2
