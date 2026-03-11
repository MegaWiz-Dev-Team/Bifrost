"""Heimdall LLM Gateway client — OpenAI-compatible API."""

import json
import httpx
from typing import AsyncIterator

from bifrost.config import settings


class HeimdallClient:
    """Async HTTP client for Heimdall LLM Gateway."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.heimdall_url).rstrip("/")
        self.api_key = api_key or settings.heimdall_api_key
        self._client: httpx.AsyncClient | None = None

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

        response = await client.post("/v1/chat/completions", json=payload)
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

        async with client.stream("POST", "/v1/chat/completions", json=payload) as response:
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
            response = await client.get("/v1/models")
            return response.status_code == 200
        except (httpx.HTTPError, httpx.ConnectError):
            return False

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
