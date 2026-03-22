from google.adk.agents import LlmAgent

# Global tool list — populated at runtime by Bifrost lifespan
# via create_mcp_adk_tools(settings.yggdrasil_mcp_url, "yggdrasil-mcp")
_mcp_tools: list = []


def set_mcp_tools(tools: list) -> None:
    """Inject MCP-discovered tools into this agent module."""
    global _mcp_tools
    _mcp_tools = tools


def create_agent() -> LlmAgent:
    """Create the Yggdrasil agent with dynamically discovered MCP tools."""
    return LlmAgent(
        name="Yggdrasil",
        model="gemini-2.5-flash",
        description="จัดการ authentication และ authorization ผ่าน MCP Sidecar",
        instruction="""Role: Authentication & Authorization Service
You are Yggdrasil, the identity gateway for the Asgard AI Platform.

You have access to MCP tools that let you interact with Zitadel IAM:
- validate_token: Introspect a JWT token to check if it's valid and get claims
- get_user_roles: Look up all roles/grants for a specific user

Constraints:
- NEVER log tokens or credentials in your responses
- Enforce least privilege principle
- Always sanitize token values before including in responses
- If validation fails, explain the error clearly

Knowledge Domains: OAuth 2.0, OpenID Connect, JWT, RBAC""",
        tools=_mcp_tools,
    )


# Default agent instance (no tools until set_mcp_tools is called)
root_agent = create_agent()
