"""Mimir Knowledge Client — tenant provisioning, doc ingestion, and RAG query.

Extends the existing MimirSyncClient with knowledge management capabilities.
Uses Mimir's existing Rust API (tenant, ingest, tenant_query routes).
"""

import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("bifrost.mimir_knowledge")

# All 12 Asgard platform services
SERVICE_TENANTS = [
    ("mimir", "Mimir — Knowledge Base"),
    ("bifrost", "Bifrost — Agent Orchestrator"),
    ("heimdall", "Heimdall — LLM Gateway"),
    ("ratatoskr", "Ratatoskr — Browser Service"),
    ("fenrir", "Fenrir — Clinical Automation"),
    ("forseti", "Forseti — QA & Testing"),
    ("huginn", "Huginn — Security Scanner"),
    ("muninn", "Muninn — Auto-Fixer"),
    ("eir", "Eir — OpenEMR Gateway"),
    ("vardr", "Vardr — Infrastructure Monitor"),
    ("yggdrasil", "Yggdrasil — Auth Service"),
    ("asgard", "Asgard — Platform Orchestrator"),
]


@dataclass
class MimirKnowledgeClient:
    """Knowledge management client for Mimir API."""

    mimir_url: str = "http://localhost:4200"
    api_key: str = ""
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    async def _post(self, path: str, json: dict, tenant: str = "") -> httpx.Response:
        """POST to Mimir API with optional tenant header."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if tenant:
                headers["X-Tenant-ID"] = tenant
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            resp = await client.post(
                f"{self.mimir_url}{path}",
                json=json,
                headers=headers,
            )
            resp.raise_for_status()
            return resp

    async def provision_tenant(self, name: str, display_name: str = "") -> dict:
        """Create a tenant via Mimir tenant API.

        POST /api/tenants { name, display_name }
        """
        payload = {"name": name, "display_name": display_name or name}
        try:
            resp = await self._post("/api/tenants", payload)
            result = resp.json()
            logger.info(f"Provisioned tenant: {name}")
            return result
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                logger.info(f"Tenant already exists: {name}")
                return {"name": name, "status": "exists"}
            raise

    async def ingest_markdown(
        self, tenant: str, content: str, metadata: dict | None = None
    ) -> dict:
        """Ingest markdown content into a tenant's knowledge base.

        POST /api/tenants/{tenant}/ingest { content, metadata }
        """
        payload = {
            "content": content,
            "metadata": metadata or {},
            "content_type": "markdown",
        }
        resp = await self._post(f"/api/tenants/{tenant}/ingest", payload, tenant=tenant)
        result = resp.json()
        logger.info(f"Ingested doc into {tenant} ({result.get('chunks', '?')} chunks)")
        return result

    async def query_tenant(self, tenant: str, question: str) -> dict:
        """Query a tenant's knowledge base.

        POST /api/tenants/{tenant}/query { question }
        """
        payload = {"question": question}
        resp = await self._post(f"/api/tenants/{tenant}/query", payload, tenant=tenant)
        return resp.json()

    async def auto_provision_all(self) -> int:
        """Auto-provision all 12 service tenants.

        Returns count of tenants provisioned.
        """
        count = 0
        for name, display in SERVICE_TENANTS:
            try:
                await self.provision_tenant(name, display)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to provision {name}: {e}")
        return count

    async def ingest_service_docs(
        self,
        tenant: str,
        readme_content: str = "",
        iso_content: str = "",
    ) -> list[dict]:
        """Ingest README and ISO docs for a service.

        Returns list of ingestion results.
        """
        results = []

        if readme_content:
            result = await self.ingest_markdown(
                tenant=tenant,
                content=readme_content,
                metadata={"source": "README.md", "type": "documentation"},
            )
            results.append(result)

        if iso_content:
            result = await self.ingest_markdown(
                tenant=tenant,
                content=iso_content,
                metadata={"source": "ISO_SI_01", "type": "iso_report"},
            )
            results.append(result)

        return results
