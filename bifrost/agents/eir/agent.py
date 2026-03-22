from google.adk.agents import LlmAgent

# Global tool list — populated at runtime by Bifrost lifespan
# via create_mcp_adk_tools(settings.eir_mcp_url, "eir-mcp")
_mcp_tools: list = []


def set_mcp_tools(tools: list) -> None:
    """Inject MCP-discovered tools into this agent module."""
    global _mcp_tools
    _mcp_tools = tools


def create_agent() -> LlmAgent:
    """Create the Eir agent with dynamically discovered MCP tools."""
    return LlmAgent(
        name="Eir",
        model="gemini-2.5-flash",
        description="เชื่อมต่อกับ OpenEMR FHIR API ผ่าน MCP Sidecar",
        instruction="""Role: OpenEMR FHIR Gateway
You are Eir, the medical data gateway for the Asgard AI Platform.

You have access to MCP tools that let you interact with OpenEMR:
- get_patient_medical_history: Retrieve a patient's full medical record (FHIR $everything)
- book_appointment: Create a new appointment for a patient

Constraints:
- HIPAA compliant — never expose patient PII in logs
- Always confirm patient identity before accessing records
- Log all clinical data access
- If a tool returns an error, explain it clearly to the user

Knowledge Domains: FHIR R4, OpenEMR, HL7, Medical Records""",
        tools=_mcp_tools,
    )


# Default agent instance (no tools until set_mcp_tools is called)
root_agent = create_agent()
