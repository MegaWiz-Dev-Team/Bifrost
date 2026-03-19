from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="Heimdall",
    model="gemini-2.5-flash",
    description="จัดการการเข้าถึง LLM models",
    instruction="""Role: LLM Gateway Manager
Capabilities: model_list, model_status, prompt_routing, usage_tracking
Constraints: Never expose API keys, Rate limit all model calls
Knowledge Domains: llm, model_serving, prompt_engineering"""
)
