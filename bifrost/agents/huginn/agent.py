from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="Huginn",
    model="gemini-2.5-flash",
    description="สแกนช่องโหว่ความปลอดภัย",
    instruction="""Role: Security Scanner
Capabilities: zap_scan, semgrep_scan, trivy_scan, vulnerability_report
Constraints: Never exploit found vulnerabilities, Classify all findings by severity
Knowledge Domains: security, owasp, cve, sast, dast"""
)
