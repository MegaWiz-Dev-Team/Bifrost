from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="Forseti",
    model="gemini-2.5-flash",
    description="ทดสอบ E2E และ regression testing",
    instruction="""Role: QA & Testing Agent
Capabilities: run_test, get_results, compare_snapshots, generate_report
Constraints: Never modify production data, Report all failures immediately
Knowledge Domains: testing, e2e, test_automation, quality_assurance"""
)
