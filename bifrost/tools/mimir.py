"""Mimir RAG tools — connect to Mimir's REST API for knowledge search."""

from typing import Any
import httpx

from bifrost.tools.base import Tool


class SearchKnowledgeTool(Tool):
    """Search the Mimir knowledge base using vector + hybrid search."""

    name = "search_knowledge"
    description = (
        "Search the knowledge base for relevant information. "
        "Use this when you need to look up facts, procedures, or reference data. "
        "Returns the most relevant chunks with source attribution."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query in natural language",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default: 5)",
            },
        },
        "required": ["query"],
    }

    def __init__(self, mimir_url: str, api_key: str = "", tenant_id: str = "default"):
        self._mimir_url = mimir_url.rstrip("/")
        self._api_key = api_key
        self._tenant_id = tenant_id

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        limit = kwargs.get("limit", 5)

        headers = {"Content-Type": "application/json", "X-Tenant-ID": self._tenant_id}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._mimir_url}/api/search",
                    json={"query": query, "limit": limit},
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                results = data.get("results", [])
                if not results:
                    return "No results found."

                output = []
                for i, r in enumerate(results[:limit], 1):
                    score = r.get("score", 0)
                    text = r.get("content", r.get("text", ""))
                    source = r.get("source", r.get("source_name", "unknown"))
                    output.append(f"[{i}] (score: {score:.3f}) [{source}]\n{text}")
                return "\n\n".join(output)

        except httpx.HTTPError as e:
            return f"Search error: {e}"


class ListSourcesTool(Tool):
    """List available knowledge sources in Mimir."""

    name = "list_sources"
    description = "List all available knowledge sources (documents, files, URLs) in the knowledge base."
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def __init__(self, mimir_url: str, api_key: str = "", tenant_id: str = "default"):
        self._mimir_url = mimir_url.rstrip("/")
        self._api_key = api_key
        self._tenant_id = tenant_id

    async def execute(self, **kwargs: Any) -> str:
        headers = {"X-Tenant-ID": self._tenant_id}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._mimir_url}/api/sources",
                    headers=headers,
                )
                response.raise_for_status()
                sources = response.json()

                if not sources:
                    return "No sources found."

                lines = []
                for s in sources:
                    name = s.get("name", "unknown")
                    s_type = s.get("source_type", "unknown")
                    chunks = s.get("total_chunks", "?")
                    lines.append(f"- {name} ({s_type}, {chunks} chunks)")
                return "\n".join(lines)

        except httpx.HTTPError as e:
            return f"Error listing sources: {e}"


class GetDocumentTool(Tool):
    """Get a specific document chunk from Mimir."""

    name = "get_document"
    description = "Retrieve a specific document or chunk by its ID from the knowledge base."
    parameters = {
        "type": "object",
        "properties": {
            "chunk_id": {
                "type": "integer",
                "description": "The ID of the chunk to retrieve",
            },
        },
        "required": ["chunk_id"],
    }

    def __init__(self, mimir_url: str, api_key: str = "", tenant_id: str = "default"):
        self._mimir_url = mimir_url.rstrip("/")
        self._api_key = api_key
        self._tenant_id = tenant_id

    async def execute(self, **kwargs: Any) -> str:
        chunk_id = kwargs.get("chunk_id")
        if chunk_id is None:
            return "Error: chunk_id is required"

        headers = {"X-Tenant-ID": self._tenant_id}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._mimir_url}/api/chunks/{chunk_id}",
                    headers=headers,
                )
                response.raise_for_status()
                chunk = response.json()

                text = chunk.get("chunk_text", chunk.get("content", ""))
                source = chunk.get("source_name", "unknown")
                return f"[Source: {source}]\n{text}"

        except httpx.HTTPError as e:
            return f"Error: {e}"


def register_mimir_tools(mimir_url: str, api_key: str = "", tenant_id: str = "default"):
    """Register all Mimir RAG tools in the global registry."""
    from bifrost.tools.registry import registry

    registry.register(SearchKnowledgeTool(mimir_url, api_key, tenant_id))
    registry.register(ListSourcesTool(mimir_url, api_key, tenant_id))
    registry.register(GetDocumentTool(mimir_url, api_key, tenant_id))
