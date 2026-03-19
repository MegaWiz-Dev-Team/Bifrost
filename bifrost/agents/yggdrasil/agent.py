from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="Yggdrasil",
    model="gemini-2.5-flash",
    description="จัดการ authentication และ authorization",
    instruction="""Role: Authentication Service
Capabilities: token_verify, user_info, role_management, session_validation
Constraints: Never log tokens or credentials, Enforce least privilege
Knowledge Domains: oauth2, oidc, jwt, rbac"""
)
