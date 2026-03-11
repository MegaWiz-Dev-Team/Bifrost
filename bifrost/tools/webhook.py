"""Webhook tools — user-defined HTTP tools for agents."""

import json
from typing import Any
import httpx

from bifrost.tools.base import Tool


class WebhookTool(Tool):
    """A custom HTTP webhook tool defined by the user."""

    def __init__(
        self,
        name: str,
        description: str,
        url: str,
        method: str = "POST",
        headers: dict[str, str] | None = None,
        body_template: dict | None = None,
        parameters: dict | None = None,
    ):
        self.name = name
        self.description = description
        self.url = url
        self.method = method.upper()
        self._headers = headers or {"Content-Type": "application/json"}
        self._body_template = body_template
        self.parameters = parameters or {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "Data to send in the request body",
                }
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        try:
            # Build request body
            if self._body_template:
                body = json.dumps(self._body_template)
                # Replace template variables
                for key, value in kwargs.items():
                    body = body.replace(f"{{{{{key}}}}}", str(value))
            elif kwargs:
                body = json.dumps(kwargs)
            else:
                body = None

            async with httpx.AsyncClient(timeout=30.0) as client:
                if self.method == "GET":
                    response = await client.get(self.url, headers=self._headers, params=kwargs)
                elif self.method == "POST":
                    response = await client.post(self.url, headers=self._headers, content=body)
                elif self.method == "PUT":
                    response = await client.put(self.url, headers=self._headers, content=body)
                elif self.method == "DELETE":
                    response = await client.delete(self.url, headers=self._headers)
                else:
                    return f"Unsupported method: {self.method}"

                text = response.text
                if len(text) > 4000:
                    text = text[:4000] + "\n...(truncated)"
                return f"Status: {response.status_code}\n{text}"

        except httpx.HTTPError as e:
            return f"Webhook error: {e}"

    def to_dict(self) -> dict:
        """Serialize webhook tool config for storage."""
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "method": self.method,
            "headers": self._headers,
            "body_template": self._body_template,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WebhookTool":
        """Create a webhook tool from a dict config."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            url=data["url"],
            method=data.get("method", "POST"),
            headers=data.get("headers"),
            body_template=data.get("body_template"),
            parameters=data.get("parameters"),
        )
