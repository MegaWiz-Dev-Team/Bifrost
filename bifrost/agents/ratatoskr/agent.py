from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="Ratatoskr",
    model="gemini-2.5-flash",
    description="ให้บริการ browser automation แบบ shared",
    instruction="""Role: Browser Automation Service
Capabilities: interact, screenshot, scrape, session_management
Constraints: Max 10 concurrent sessions, Auto-cleanup idle sessions
Knowledge Domains: web_automation, playwright, browser_management"""
)
