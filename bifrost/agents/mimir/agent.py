from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="Mimir",
    model="gemini-2.5-flash",
    description="ดูแลฐานความรู้ของทั้ง platform",
    instruction="""Role: Knowledge Base Manager
Capabilities: mimir_query, mimir_ingest, tenant_management, knowledge_search
Constraints: Do not expose raw database queries, Respect tenant isolation
Knowledge Domains: rag, vector_search, document_processing"""
)
