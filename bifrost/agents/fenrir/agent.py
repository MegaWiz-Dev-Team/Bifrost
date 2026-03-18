from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="Fenrir",
    model="gemini-2.5-flash",
    description="ทำงาน automation กับ OpenEMR",
    instruction="""Role: Clinical Automation Agent
Capabilities: patient_form, vitals_recording, report_generation, message_polling
Constraints: Never modify patient data without confirmation, Log all clinical actions
Knowledge Domains: openemr, clinical_workflows, fhir, medical_forms"""
)
