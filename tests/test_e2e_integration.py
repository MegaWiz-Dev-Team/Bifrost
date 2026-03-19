"""E2E Integration tests — Bifrost ↔ Eir + Mimir + Fenrir tool registration.

Tests tool creation, registration, and request/response handling with mocked backends.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from bifrost.tools.eir import (
    EirPatientSearchTool,
    EirFhirQueryTool,
    EirClinicalSummaryTool,
    register_eir_tools,
)
from bifrost.tools.registry import ToolRegistry


# === Eir Patient Search Tool ===


class TestEirPatientSearchTool:
    """Test EirPatientSearchTool."""

    def test_tool_schema(self):
        tool = EirPatientSearchTool("http://localhost:8300")
        assert tool.name == "eir_patient_search"
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "eir_patient_search"
        assert "name" in schema["function"]["parameters"]["properties"]
        assert "birthdate" in schema["function"]["parameters"]["properties"]
        assert "identifier" in schema["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_search_returns_patients(self):
        tool = EirPatientSearchTool("http://localhost:8300")
        mock_response = {
            "status": "success",
            "data": {
                "resourceType": "Bundle",
                "total": 1,
                "entry": [
                    {
                        "resource": {
                            "resourceType": "Patient",
                            "id": "1",
                            "name": [{"given": ["สมชาย"], "family": "ใจดี"}],
                            "gender": "male",
                            "birthDate": "1980-05-15",
                        }
                    }
                ],
            },
            "metadata": {"gateway": "eir"},
        }

        with patch("bifrost.tools.eir.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(return_value=MagicMock(
                status_code=200,
                raise_for_status=MagicMock(),
                json=MagicMock(return_value=mock_response),
            ))

            result = await tool.execute(name="สมชาย")
            assert "สมชาย" in result
            assert "1" in result
            assert "Found 1 patient" in result

    @pytest.mark.asyncio
    async def test_search_no_results(self):
        tool = EirPatientSearchTool("http://localhost:8300")
        mock_response = {
            "status": "success",
            "data": {"resourceType": "Bundle", "total": 0, "entry": []},
            "metadata": {},
        }

        with patch("bifrost.tools.eir.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(return_value=MagicMock(
                status_code=200,
                raise_for_status=MagicMock(),
                json=MagicMock(return_value=mock_response),
            ))

            result = await tool.execute(name="nonexistent")
            assert "No patients found" in result

    @pytest.mark.asyncio
    async def test_search_handles_network_error(self):
        tool = EirPatientSearchTool("http://localhost:8300")

        import httpx
        with patch("bifrost.tools.eir.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

            result = await tool.execute(name="test")
            assert "error" in result.lower()


# === Eir FHIR Query Tool ===


class TestEirFhirQueryTool:
    """Test EirFhirQueryTool."""

    def test_tool_schema(self):
        tool = EirFhirQueryTool("http://localhost:8300")
        assert tool.name == "eir_fhir_query"
        schema = tool.to_openai_schema()
        assert "query" in schema["function"]["parameters"]["properties"]
        assert "query" in schema["function"]["parameters"]["required"]

    @pytest.mark.asyncio
    async def test_query_requires_query_param(self):
        tool = EirFhirQueryTool("http://localhost:8300")
        result = await tool.execute()
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_query_returns_fhir_data(self):
        tool = EirFhirQueryTool("http://localhost:8300")
        mock_response = {
            "status": "success",
            "data": {"resourceType": "Bundle", "total": 2, "entry": []},
            "metadata": {"resource_type": "Condition", "query": "diabetes"},
        }

        with patch("bifrost.tools.eir.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=MagicMock(
                status_code=200,
                raise_for_status=MagicMock(),
                json=MagicMock(return_value=mock_response),
            ))

            result = await tool.execute(query="diabetes conditions", resource_type="Condition")
            assert "FHIR" in result
            assert "Condition" in result


# === Eir Clinical Summary Tool ===


class TestEirClinicalSummaryTool:
    """Test EirClinicalSummaryTool."""

    def test_tool_schema(self):
        tool = EirClinicalSummaryTool("http://localhost:8300")
        assert tool.name == "eir_clinical_summary"
        schema = tool.to_openai_schema()
        assert "patient_id" in schema["function"]["parameters"]["required"]

    @pytest.mark.asyncio
    async def test_summary_requires_patient_id(self):
        tool = EirClinicalSummaryTool("http://localhost:8300")
        result = await tool.execute()
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_summary_returns_aggregated_data(self):
        tool = EirClinicalSummaryTool("http://localhost:8300")
        mock_response = {
            "status": "success",
            "data": {
                "patient": {"resourceType": "Patient", "id": "1", "name": [{"given": ["Test"]}]},
                "condition": {"resourceType": "Bundle", "total": 2, "entry": []},
                "medicationrequest": {"resourceType": "Bundle", "total": 1, "entry": []},
            },
            "metadata": {"patient_id": "1"},
        }

        with patch("bifrost.tools.eir.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(return_value=MagicMock(
                status_code=200,
                raise_for_status=MagicMock(),
                json=MagicMock(return_value=mock_response),
            ))

            result = await tool.execute(patient_id="1")
            assert "Clinical Summary" in result
            assert "Patient" in result or "patient" in result.lower()


# === Tool Registration ===


class TestToolRegistration:
    """Test tool registration for all services."""

    def test_register_eir_tools(self):
        registry = ToolRegistry()
        with patch("bifrost.tools.registry.registry", registry):
            register_eir_tools("http://localhost:8300")
        assert len(registry) == 3
        assert "eir_patient_search" in registry
        assert "eir_fhir_query" in registry
        assert "eir_clinical_summary" in registry

    def test_register_eir_tools_with_api_key(self):
        registry = ToolRegistry()
        with patch("bifrost.tools.registry.registry", registry):
            register_eir_tools("http://localhost:8300", api_key="test-key")
        tool = registry.get("eir_patient_search")
        assert tool is not None
        assert tool._api_key == "test-key"

    def test_all_tools_have_openai_schema(self):
        """All Eir tools must produce valid OpenAI function calling schemas."""
        tools = [
            EirPatientSearchTool("http://localhost:8300"),
            EirFhirQueryTool("http://localhost:8300"),
            EirClinicalSummaryTool("http://localhost:8300"),
        ]
        for tool in tools:
            schema = tool.to_openai_schema()
            assert schema["type"] == "function"
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]
            assert schema["function"]["parameters"]["type"] == "object"

    def test_eir_registry_total(self):
        """Verify Eir registers 3 tools (Mimir tools now come via MCP dynamically)."""
        registry = ToolRegistry()
        with patch("bifrost.tools.registry.registry", registry):
            register_eir_tools("http://localhost:8300")

        assert len(registry) == 3
        # Eir tools
        assert "eir_patient_search" in registry
        assert "eir_fhir_query" in registry
        assert "eir_clinical_summary" in registry
