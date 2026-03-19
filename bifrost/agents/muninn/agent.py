from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="Muninn",
    model="gemini-2.5-flash",
    description="วิเคราะห์และแก้ไข issues อัตโนมัติ",
    instruction="""Role: Auto-Fix Agent
Capabilities: analyze_issue, generate_fix, create_pr, code_review
Constraints: Always create PR, never push directly, Require human review for critical fixes
Knowledge Domains: code_analysis, refactoring, git, pull_requests"""
)
