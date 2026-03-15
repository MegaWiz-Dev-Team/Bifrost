"""Eir Gateway tools — connect to Eir's REST API for clinical data.

Provides patient search, FHIR query, and clinical summary tools
via the Eir Gateway's agent endpoints.
"""

from typing import Any
import httpx

from bifrost.tools.base import Tool


class EirPatientSearchTool(Tool):
    """Search for patients in OpenEMR via the Eir Gateway."""

    name = "eir_patient_search"
    description = (
        "Search for patients in the clinic system by name, birthdate, or identifier. "
        "Use this when you need to find specific patients. "
        "Returns matching patient records from OpenEMR."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Patient name to search for (partial match supported)",
            },
            "birthdate": {
                "type": "string",
                "description": "Date of birth in YYYY-MM-DD format",
            },
            "identifier": {
                "type": "string",
                "description": "Patient identifier / MRN number",
            },
        },
    }

    def __init__(self, eir_url: str, api_key: str = ""):
        self._eir_url = eir_url.rstrip("/")
        self._api_key = api_key

    async def execute(self, **kwargs: Any) -> str:
        params = {}
        if kwargs.get("name"):
            params["name"] = kwargs["name"]
        if kwargs.get("birthdate"):
            params["birthdate"] = kwargs["birthdate"]
        if kwargs.get("identifier"):
            params["identifier"] = kwargs["identifier"]

        headers = self._build_headers()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._eir_url}/v1/patients/search",
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                status = data.get("status", "unknown")
                patients = data.get("data", {})

                if status != "success":
                    return f"Search failed: {data}"

                # Format FHIR Bundle response
                entries = patients.get("entry", [])
                if not entries:
                    total = patients.get("total", 0)
                    return f"No patients found (total: {total})."

                output = [f"Found {len(entries)} patient(s):"]
                for entry in entries:
                    resource = entry.get("resource", {})
                    names = resource.get("name", [{}])
                    name_parts = []
                    for n in names:
                        given = " ".join(n.get("given", []))
                        family = n.get("family", "")
                        name_parts.append(f"{given} {family}".strip())
                    display_name = ", ".join(name_parts) or "Unknown"
                    pid = resource.get("id", "?")
                    gender = resource.get("gender", "?")
                    dob = resource.get("birthDate", "?")
                    output.append(f"  - [{pid}] {display_name} (DOB: {dob}, Gender: {gender})")

                return "\n".join(output)

        except httpx.HTTPError as e:
            return f"Eir patient search error: {e}"

    def _build_headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers


class EirFhirQueryTool(Tool):
    """Query FHIR resources via natural language through the Eir Gateway."""

    name = "eir_fhir_query"
    description = (
        "Query clinical data using natural language or structured FHIR parameters. "
        "Supports querying any FHIR resource type (Patient, Condition, Observation, etc.). "
        "Use this for flexible clinical data lookups."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language query or structured search string",
            },
            "resource_type": {
                "type": "string",
                "description": "FHIR resource type (e.g. Patient, Condition, MedicationRequest). Default: Patient",
            },
            "patient_id": {
                "type": "string",
                "description": "Optional patient ID to scope the query to",
            },
        },
        "required": ["query"],
    }

    def __init__(self, eir_url: str, api_key: str = ""):
        self._eir_url = eir_url.rstrip("/")
        self._api_key = api_key

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "Error: query is required"

        payload = {"query": query}
        if kwargs.get("resource_type"):
            payload["resource_type"] = kwargs["resource_type"]
        if kwargs.get("patient_id"):
            payload["patient_id"] = kwargs["patient_id"]

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._eir_url}/v1/fhir/query",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                status = data.get("status", "unknown")
                result = data.get("data", {})
                metadata = data.get("metadata", {})

                if status != "success":
                    return f"FHIR query failed: {data}"

                resource_type = metadata.get("resource_type", "unknown")
                return f"[FHIR {resource_type} query result]\n{_format_fhir_data(result)}"

        except httpx.HTTPError as e:
            return f"Eir FHIR query error: {e}"


class EirClinicalSummaryTool(Tool):
    """Get an aggregated clinical summary for a patient."""

    name = "eir_clinical_summary"
    description = (
        "Get a comprehensive clinical summary for a patient, including conditions, "
        "medications, and allergies. Use this when you need a complete overview "
        "of a patient's clinical data."
    )
    parameters = {
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "The patient ID to get a clinical summary for",
            },
            "include": {
                "type": "array",
                "items": {"type": "string"},
                "description": "FHIR resource types to include (default: Patient, Condition, MedicationRequest, AllergyIntolerance)",
            },
        },
        "required": ["patient_id"],
    }

    def __init__(self, eir_url: str, api_key: str = ""):
        self._eir_url = eir_url.rstrip("/")
        self._api_key = api_key

    async def execute(self, **kwargs: Any) -> str:
        patient_id = kwargs.get("patient_id", "")
        if not patient_id:
            return "Error: patient_id is required"

        payload = {"patient_id": patient_id}
        if kwargs.get("include"):
            payload["include"] = kwargs["include"]

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self._eir_url}/v1/clinical/summary",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                status = data.get("status", "unknown")
                summary = data.get("data", {})
                metadata = data.get("metadata", {})

                if status != "success":
                    return f"Clinical summary failed: {data}"

                output = [f"Clinical Summary for Patient {patient_id}:"]
                for resource_type, resource_data in summary.items():
                    output.append(f"\n## {resource_type.title()}")
                    if isinstance(resource_data, dict) and "error" in resource_data:
                        output.append(f"  ⚠️ {resource_data['error']}")
                    else:
                        output.append(f"  {_format_fhir_data(resource_data)}")

                return "\n".join(output)

        except httpx.HTTPError as e:
            return f"Eir clinical summary error: {e}"


def _format_fhir_data(data: Any) -> str:
    """Format FHIR response data for LLM consumption."""
    if isinstance(data, dict):
        # Handle FHIR Bundle
        if data.get("resourceType") == "Bundle":
            entries = data.get("entry", [])
            total = data.get("total", len(entries))
            if not entries:
                return f"No results (total: {total})"
            parts = [f"Bundle ({total} results):"]
            for entry in entries[:10]:  # Cap at 10 for LLM context
                resource = entry.get("resource", {})
                r_type = resource.get("resourceType", "Unknown")
                r_id = resource.get("id", "?")
                parts.append(f"  - {r_type}/{r_id}")
            if total > 10:
                parts.append(f"  ... and {total - 10} more")
            return "\n".join(parts)

        # Handle single resource
        r_type = data.get("resourceType", "")
        r_id = data.get("id", "")
        if r_type:
            import json
            return f"{r_type}/{r_id}: {json.dumps(data, indent=2, ensure_ascii=False)[:2000]}"

    # Fallback
    import json
    return json.dumps(data, indent=2, ensure_ascii=False)[:2000]


def register_eir_tools(eir_url: str, api_key: str = "") -> None:
    """Register all Eir Gateway tools in the global registry."""
    from bifrost.tools.registry import registry

    registry.register(EirPatientSearchTool(eir_url, api_key))
    registry.register(EirFhirQueryTool(eir_url, api_key))
    registry.register(EirClinicalSummaryTool(eir_url, api_key))
