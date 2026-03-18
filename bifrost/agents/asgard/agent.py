from google.adk.agents import LlmAgent
from bifrost.agents.mimir.agent import root_agent as mimir_agent
from bifrost.agents.bifrost.agent import root_agent as bifrost_agent
from bifrost.agents.heimdall.agent import root_agent as heimdall_agent
from bifrost.agents.ratatoskr.agent import root_agent as ratatoskr_agent
from bifrost.agents.fenrir.agent import root_agent as fenrir_agent
from bifrost.agents.forseti.agent import root_agent as forseti_agent
from bifrost.agents.huginn.agent import root_agent as huginn_agent
from bifrost.agents.muninn.agent import root_agent as muninn_agent
from bifrost.agents.eir.agent import root_agent as eir_agent
from bifrost.agents.vardr.agent import root_agent as vardr_agent
from bifrost.agents.yggdrasil.agent import root_agent as yggdrasil_agent

root_agent = LlmAgent(
    name="Asgard",
    model="gemini-2.5-flash",
    description="จัดการ platform ภาพรวม",
    instruction="""You are Asgard, the master Platform Orchestrator.
Role: Platform Orchestrator
You coordinate the workflow of 11 expert sub-agents to fulfill any user request.
Constraints: Never deploy without passing E2E tests, Maintain rollback capability""",
    sub_agents=[mimir_agent, bifrost_agent, heimdall_agent, ratatoskr_agent, fenrir_agent, forseti_agent, huginn_agent, muninn_agent, eir_agent, vardr_agent, yggdrasil_agent]
)
