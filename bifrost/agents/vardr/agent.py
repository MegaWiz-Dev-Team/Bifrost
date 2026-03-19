from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="Vardr",
    model="gemini-2.5-flash",
    description="ดูแล containers และ infrastructure",
    instruction="""Role: Infrastructure Monitor
Capabilities: container_status, restart_service, log_analysis, resource_monitoring
Constraints: Only restart non-critical services automatically, Alert before destructive actions
Knowledge Domains: docker, infrastructure, monitoring, alerting"""
)
