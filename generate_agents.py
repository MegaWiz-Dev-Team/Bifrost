import os
import sys

# Add Developer to path so we can import bifrost
sys.path.insert(0, "/Users/mimir/Developer/Bifrost")
from bifrost.core.service_agents import SERVICE_AGENTS

base_dir = "/Users/mimir/Developer/Bifrost/bifrost/agents"
os.makedirs(base_dir, exist_ok=True)
with open(os.path.join(base_dir, "__init__.py"), "w") as f:
    pass

for agent in SERVICE_AGENTS:
    if agent.agent_id == "asgard-agent":
        continue
    
    agent_dir = os.path.join(base_dir, agent.agent_id.split("-")[0])
    os.makedirs(agent_dir, exist_ok=True)
    
    with open(os.path.join(agent_dir, "__init__.py"), "w") as f:
        pass
        
    code = f'''from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="{agent.persona_name}",
    model="gemini-2.5-flash",
    description="{agent.persona_description}",
    instruction="""Role: {agent.persona_role}
Capabilities: {', '.join(agent.capabilities)}
Constraints: {', '.join(agent.constraints)}
Knowledge Domains: {', '.join(agent.knowledge_domains)}"""
)
'''
    with open(os.path.join(agent_dir, "agent.py"), "w") as f:
        f.write(code)

asgard = next(a for a in SERVICE_AGENTS if a.agent_id == "asgard-agent")
asgard_dir = os.path.join(base_dir, "asgard")
os.makedirs(asgard_dir, exist_ok=True)
with open(os.path.join(asgard_dir, "__init__.py"), "w") as f:
    pass

imports = []
sub_agent_vars = []
for a in SERVICE_AGENTS:
    if a.agent_id == "asgard-agent": continue
    pkg = a.agent_id.split("-")[0]
    imports.append(f"from bifrost.agents.{pkg}.agent import root_agent as {pkg}_agent")
    sub_agent_vars.append(f"{pkg}_agent")

code = f'''from google.adk.agents import LlmAgent
{chr(10).join(imports)}

agent = LlmAgent(
    name="{asgard.persona_name}",
    model="gemini-2.5-flash",
    description="{asgard.persona_description}",
    instruction="""You are Asgard, the master Platform Orchestrator.
Role: {asgard.persona_role}
You coordinate the workflow of 11 expert sub-agents to fulfill any user request.
Constraints: {', '.join(asgard.constraints)}""",
    sub_agents=[{', '.join(sub_agent_vars)}]
)
'''
with open(os.path.join(asgard_dir, "agent.py"), "w") as f:
    f.write(code)

print("Generated all agents under", base_dir)
