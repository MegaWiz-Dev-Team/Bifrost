"""TDD tests for JWT auth middleware — written BEFORE implementation.

Tests Yggdrasil JWT integration as FastAPI middleware for Bifrost.
Following ISO/IEC 29110 test-first development.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


# === Fixture: Create test client with mocked settings ===

@pytest.fixture
def auth_enabled_client():
    """Client with auth ENABLED (production mode)."""
    with patch("bifrost.config.settings") as mock_settings:
        mock_settings.heimdall_url = "http://localhost:8080"
        mock_settings.heimdall_api_key = ""
        mock_settings.bifrost_host = "0.0.0.0"
        mock_settings.bifrost_port = 8100
        mock_settings.database_path = ":memory:"
        mock_settings.max_iterations = 10
        mock_settings.max_execution_time = 120
        mock_settings.default_model = "qwen3.5"
        mock_settings.log_level = "WARNING"
        mock_settings.auth_enabled = True
        mock_settings.yggdrasil_issuer = "http://localhost:8085"
        mock_settings.jwt_audience = ""
        mock_settings.mimir_url = ""
        mock_settings.eir_url = ""
        mock_settings.fenrir_enabled = False

        from bifrost.main import app
        with TestClient(app) as c:
            yield c


@pytest.fixture
def auth_disabled_client():
    """Client with auth DISABLED (dev mode)."""
    with patch("bifrost.config.settings") as mock_settings:
        mock_settings.heimdall_url = "http://localhost:8080"
        mock_settings.heimdall_api_key = ""
        mock_settings.bifrost_host = "0.0.0.0"
        mock_settings.bifrost_port = 8100
        mock_settings.database_path = ":memory:"
        mock_settings.max_iterations = 10
        mock_settings.max_execution_time = 120
        mock_settings.default_model = "qwen3.5"
        mock_settings.log_level = "WARNING"
        mock_settings.auth_enabled = False
        mock_settings.yggdrasil_issuer = ""
        mock_settings.jwt_audience = ""
        mock_settings.mimir_url = ""
        mock_settings.eir_url = ""
        mock_settings.fenrir_enabled = False

        from bifrost.main import app
        with TestClient(app) as c:
            yield c


# === Health endpoints should NEVER require auth ===

class TestPublicEndpoints:
    """Health and docs should remain open regardless of auth config."""

    def test_healthz_no_auth_needed(self, auth_enabled_client):
        """GET /healthz should return 200 without any token."""
        response = auth_enabled_client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_docs_no_auth_needed(self, auth_enabled_client):
        """GET /docs should return 200 (Swagger UI)."""
        response = auth_enabled_client.get("/docs")
        assert response.status_code == 200

    def test_openapi_no_auth_needed(self, auth_enabled_client):
        """GET /openapi.json should return 200."""
        response = auth_enabled_client.get("/openapi.json")
        assert response.status_code == 200


# === Protected endpoints should require auth when enabled ===

class TestProtectedEndpoints:
    """API endpoints should require JWT when auth is enabled."""

    def test_list_agents_requires_auth(self, auth_enabled_client):
        """GET /v1/agents should return 401 without token."""
        response = auth_enabled_client.get("/v1/agents")
        assert response.status_code == 401

    def test_run_agent_requires_auth(self, auth_enabled_client):
        """POST /v1/agents/{id}/run should return 401 without token."""
        response = auth_enabled_client.post(
            "/v1/agents/test/run",
            json={"input": "hello"},
        )
        assert response.status_code == 401

    def test_list_tools_requires_auth(self, auth_enabled_client):
        """GET /v1/tools should return 401 without token."""
        response = auth_enabled_client.get("/v1/tools")
        assert response.status_code == 401

    def test_a2a_card_no_auth(self, auth_enabled_client):
        """GET /.well-known/agent.json should be public (A2A discovery)."""
        response = auth_enabled_client.get("/.well-known/agent.json")
        assert response.status_code == 200


# === Auth disabled mode (development) ===

class TestAuthDisabled:
    """When auth_enabled=False, all endpoints work without tokens."""

    def test_healthz_works(self, auth_disabled_client):
        response = auth_disabled_client.get("/healthz")
        assert response.status_code == 200

    def test_list_agents_works(self, auth_disabled_client):
        """List agents should work without auth in dev mode."""
        response = auth_disabled_client.get("/v1/agents")
        assert response.status_code == 200

    def test_list_tools_works(self, auth_disabled_client):
        """List tools should work without auth in dev mode."""
        response = auth_disabled_client.get("/v1/tools")
        assert response.status_code == 200


# === Valid token passes through ===

class TestValidToken:
    """Requests with valid JWT should succeed."""

    @patch("bifrost.middleware.auth.validate_jwt")
    def test_valid_token_allows_access(self, mock_validate, auth_enabled_client):
        """Valid JWT in Authorization header should pass through."""
        from yggdrasil.models import TokenClaims

        mock_validate.return_value = TokenClaims(
            sub="user-123",
            iss="http://localhost:8085",
            org_id="org-1",
        )

        response = auth_enabled_client.get(
            "/v1/agents",
            headers={"Authorization": "Bearer valid-jwt-token"},
        )
        assert response.status_code == 200

    @patch("bifrost.middleware.auth.validate_jwt")
    def test_claims_in_response(self, mock_validate, auth_enabled_client):
        """Valid auth should not affect the response body."""
        from yggdrasil.models import TokenClaims

        mock_validate.return_value = TokenClaims(
            sub="user-456",
            iss="http://localhost:8085",
            org_id="org-2",
        )

        response = auth_enabled_client.get(
            "/v1/tools",
            headers={"Authorization": "Bearer valid-jwt-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "tools" in data


# === Invalid tokens rejected ===

class TestInvalidToken:
    """Requests with invalid/expired JWTs should be rejected."""

    @patch("bifrost.middleware.auth.validate_jwt")
    def test_expired_token_rejected(self, mock_validate, auth_enabled_client):
        """Expired JWT should return 401."""
        import jwt
        mock_validate.side_effect = jwt.ExpiredSignatureError("Token expired")

        response = auth_enabled_client.get(
            "/v1/agents",
            headers={"Authorization": "Bearer expired-token"},
        )
        assert response.status_code == 401

    @patch("bifrost.middleware.auth.validate_jwt")
    def test_invalid_signature_rejected(self, mock_validate, auth_enabled_client):
        """Invalid signature should return 401."""
        import jwt
        mock_validate.side_effect = jwt.InvalidSignatureError("Bad signature")

        response = auth_enabled_client.get(
            "/v1/agents",
            headers={"Authorization": "Bearer bad-sig-token"},
        )
        assert response.status_code == 401
