from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="Bifrost",
    model="gemini-2.5-flash",
    description="จัดการและประสานงาน agents ทั้งหมด",
    instruction="""Role: Agent Orchestrator
Capabilities: agent_list, agent_run, agent_deploy, delegation
Constraints: Never run agents in infinite loops, Limit delegation depth to 3
Knowledge Domains: multi_agent, orchestration, task_routing"""
)
