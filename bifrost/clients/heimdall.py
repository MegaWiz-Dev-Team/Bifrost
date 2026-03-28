"""Heimdall LLM Gateway client — OpenAI-compatible API."""

import json
import time
import httpx
from typing import AsyncIterator

from bifrost.config import settings


class PromptCache:
    """LRU prompt cache with TTL expiration."""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self._cache: dict[str, tuple[str, float]] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> str | None:
        """Get cached prompt, returns None on miss/expiry."""
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        value, ts = entry
        if time.time() - ts > self._ttl:
            del self._cache[key]
            self._misses += 1
            return None
        self._hits += 1
        return value

    def put(self, key: str, value: str) -> None:
        """Cache a prompt."""
        if len(self._cache) >= self._max_size:
            # Evict oldest
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        self._cache[key] = (value, time.time())

    def hit_rate(self) -> float:
        """Return cache hit rate as fraction."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0


class HeimdallClient:
    """Async HTTP client for Heimdall LLM Gateway."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.heimdall_url).rstrip("/")
        self.api_key = api_key or settings.heimdall_api_key
        self._client: httpx.AsyncClient | None = None
        self._agent_models: dict[str, str] = {}
        self._prompt_cache = PromptCache()

    def set_agent_model(self, agent_id: str, model: str) -> None:
        """Configure a specific model for an agent."""
        self._agent_models[agent_id] = model

    def model_for_agent(self, agent_id: str) -> str:
        """Get the model configured for an agent, or default."""
        return self._agent_models.get(agent_id, settings.default_model)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
        return self._client

    async def chat_completion(
        self,
        messages: list[dict],
        model: str | None = None,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> dict:
        """Send a chat completion request (non-streaming).

        Returns the full response dict from Heimdall.
        """
        client = await self._get_client()
        payload: dict = {
            "model": model or settings.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = await client.post("chat/completions", json=payload)
        response.raise_for_status()
        return response.json()

    async def chat_completion_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[dict]:
        """Send a chat completion request with SSE streaming.

        Yields parsed delta dicts from each SSE chunk.
        """
        client = await self._get_client()
        payload: dict = {
            "model": model or settings.default_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with client.stream("POST", "chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        continue

    async def health_check(self) -> bool:
        """Check if Heimdall is reachable."""
        try:
            client = await self._get_client()
            response = await client.get("models")
            return response.status_code == 200
        except (httpx.HTTPError, httpx.ConnectError):
            return False

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
