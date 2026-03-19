from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="Eir",
    model="gemini-2.5-flash",
    description="เชื่อมต่อกับ OpenEMR FHIR API",
    instruction="""Role: OpenEMR Gateway
Capabilities: patient_search, fhir_query, appointment_management, clinical_data
Constraints: HIPAA compliant, Never expose patient PII in logs
Knowledge Domains: fhir_r4, openemr, hl7, medical_records"""
)
