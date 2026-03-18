"""BrowseWebTool — Browse web pages via Ratatoskr shared browser service.

Calls Ratatoskr's /api/v1/scrape endpoint to render JavaScript,
extract text, and return structured content to agents.
"""

import os
from typing import Any

import httpx

from bifrost.tools.base import Tool

# Max content length returned to LLM (avoid token overflow)
MAX_CONTENT_LENGTH = 6000


class BrowseWebTool(Tool):
    """Browse a web page and extract its content.

    Uses Ratatoskr shared browser service for JavaScript rendering,
    infinite scroll, and text extraction.
    """

    name = "browse_web"
    description = (
        "Browse a web page and extract its content. "
        "Returns the page title and text content. "
        "Use this when you need to read a web page, check information online, "
        "or extract data from a website."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL of the web page to browse",
            },
            "extract_text": {
                "type": "boolean",
                "description": "Whether to extract plain text (default: true). Set to false to get raw HTML.",
                "default": True,
            },
        },
        "required": ["url"],
    }

    def __init__(self, ratatoskr_url: str | None = None):
        self._ratatoskr_url = ratatoskr_url or os.getenv(
            "RATATOSKR_URL", "http://ratatoskr:9200"
        )

    async def execute(self, **kwargs: Any) -> str:
        url = kwargs.get("url", "")
        extract_text = kwargs.get("extract_text", True)

        if not url:
            return "Error: URL is required"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._ratatoskr_url}/api/v1/scrape",
                    json={
                        "url": url,
                        "extract_text": extract_text,
                        "scroll": False,
                    },
                )

                if response.status_code != 200:
                    return f"Error: Ratatoskr returned status {response.status_code}"

                data = response.json()
                title = data.get("title") or "Untitled"
                text = data.get("text")
                html = data.get("html", "")

                # Build result
                parts = [f"# {title}", f"URL: {url}", ""]

                if extract_text and text:
                    content = text
                else:
                    content = html

                # Truncate if too long
                if len(content) > MAX_CONTENT_LENGTH:
                    content = content[:MAX_CONTENT_LENGTH] + "\n\n...(truncated)"

                parts.append(content)
                return "\n".join(parts)

        except httpx.ConnectError:
            return "Error: Cannot connect to Ratatoskr browser service"
        except httpx.HTTPError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {e}"
