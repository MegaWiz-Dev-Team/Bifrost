"""Built-in tools for Bifrost agents."""

import ast
import operator
from datetime import datetime, timezone
from typing import Any

import httpx

from bifrost.tools.base import Tool


class GetCurrentTimeTool(Tool):
    """Returns the current date and time."""

    name = "get_current_time"
    description = "Get the current date and time in ISO 8601 format."
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> str:
        now = datetime.now(timezone.utc)
        return now.isoformat()


class CalculateTool(Tool):
    """Safe mathematical expression evaluator."""

    name = "calculate"
    description = "Evaluate a mathematical expression. Supports +, -, *, /, **, %, and parentheses."
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate, e.g. '2 + 3 * 4'",
            }
        },
        "required": ["expression"],
    }

    # Allowed operators for safe evaluation
    _OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
    }

    def _safe_eval(self, node: ast.AST) -> float:
        """Safely evaluate an AST node — only arithmetic, no exec."""
        if isinstance(node, ast.Expression):
            return self._safe_eval(node.body)
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self._OPERATORS:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")
            left = self._safe_eval(node.left)
            right = self._safe_eval(node.right)
            return self._OPERATORS[op_type](left, right)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -self._safe_eval(node.operand)
        else:
            raise ValueError(f"Unsupported expression element: {type(node).__name__}")

    async def execute(self, **kwargs: Any) -> str:
        expression = kwargs.get("expression", "")
        try:
            tree = ast.parse(expression, mode="eval")
            result = self._safe_eval(tree)
            return str(result)
        except (ValueError, SyntaxError, ZeroDivisionError) as e:
            return f"Error: {e}"


class HttpRequestTool(Tool):
    """Make HTTP GET/POST requests."""

    name = "http_request"
    description = "Make an HTTP request to a URL. Supports GET and POST methods."
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to request",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST"],
                "description": "HTTP method (default: GET)",
            },
            "body": {
                "type": "string",
                "description": "Request body for POST requests (JSON string)",
            },
        },
        "required": ["url"],
    }

    async def execute(self, **kwargs: Any) -> str:
        url = kwargs.get("url", "")
        method = kwargs.get("method", "GET").upper()
        body = kwargs.get("body")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "POST":
                    response = await client.post(url, content=body, headers={"Content-Type": "application/json"})
                else:
                    response = await client.get(url)

                # Truncate large responses
                text = response.text
                if len(text) > 4000:
                    text = text[:4000] + "\n...(truncated)"

                return f"Status: {response.status_code}\n{text}"
        except httpx.HTTPError as e:
            return f"Error: {e}"


def register_builtin_tools():
    """Register all built-in tools in the global registry."""
    from bifrost.tools.registry import registry
    from bifrost.tools.browse import BrowseWebTool

    registry.register(GetCurrentTimeTool())
    registry.register(CalculateTool())
    registry.register(HttpRequestTool())
    registry.register(BrowseWebTool())
