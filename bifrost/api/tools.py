"""Tool listing endpoints."""

from fastapi import APIRouter
from bifrost.tools.registry import registry

router = APIRouter(prefix="/v1/tools", tags=["tools"])


@router.get("")
async def list_tools():
    """List all registered tools."""
    tools = registry.list_tools()
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in tools
        ],
        "total": len(tools),
    }


@router.get("/{name}")
async def get_tool(name: str):
    """Get details of a specific tool."""
    tool = registry.get(name)
    if tool is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
        "openai_schema": tool.to_openai_schema(),
    }
