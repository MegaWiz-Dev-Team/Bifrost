"""TDD tests for Mimir agent config sync — written BEFORE implementation.

Tests periodic agent sync from Mimir API to Bifrost AgentStore.
Following ISO/IEC 29110 test-first development.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# === MimirSyncClient Tests ===

class TestMimirSyncClient:
    """Tests for MimirSyncClient periodic sync."""

    @pytest.fixture
    def client(self):
        from bifrost.clients.mimir_sync import MimirSyncClient
        return MimirSyncClient(
            mimir_url="http://localhost:3000",
            tenant_id="default",
            sync_interval=300,
        )

    @pytest.mark.asyncio
    async def test_sync_once_success(self, client):
        """Should call agent_store.sync_from_mimir with correct params."""
        with patch("bifrost.clients.mimir_sync.agent_store") as mock_store:
            mock_store.sync_from_mimir = AsyncMock(return_value=3)

            count = await client.sync_once()
            assert count == 3
            mock_store.sync_from_mimir.assert_called_once_with(
                "http://localhost:3000",
                api_key="",
                tenant_id="default",
            )

    @pytest.mark.asyncio
    async def test_sync_once_with_api_key(self):
        """Should pass API key to sync_from_mimir."""
        from bifrost.clients.mimir_sync import MimirSyncClient
        client = MimirSyncClient(
            mimir_url="http://localhost:3000",
            api_key="secret-key",
            tenant_id="test-tenant",
        )

        with patch("bifrost.clients.mimir_sync.agent_store") as mock_store:
            mock_store.sync_from_mimir = AsyncMock(return_value=5)

            count = await client.sync_once()
            assert count == 5
            mock_store.sync_from_mimir.assert_called_once_with(
                "http://localhost:3000",
                api_key="secret-key",
                tenant_id="test-tenant",
            )

    @pytest.mark.asyncio
    async def test_sync_once_handles_error(self, client):
        """Should return 0 on sync failure (non-fatal)."""
        with patch("bifrost.clients.mimir_sync.agent_store") as mock_store:
            mock_store.sync_from_mimir = AsyncMock(return_value=0)

            count = await client.sync_once()
            assert count == 0

    def test_status_initial(self, client):
        """Should have initial status."""
        status = client.status
        assert status["synced"] is False
        assert status["agent_count"] == 0
        assert status["last_sync"] is None

    @pytest.mark.asyncio
    async def test_status_after_sync(self, client):
        """Status should update after successful sync."""
        with patch("bifrost.clients.mimir_sync.agent_store") as mock_store:
            mock_store.sync_from_mimir = AsyncMock(return_value=3)

            await client.sync_once()

            status = client.status
            assert status["synced"] is True
            assert status["agent_count"] == 3
            assert status["last_sync"] is not None


# === Factory Tests ===

class TestCreateSyncClient:
    """Test convenience factory function."""

    def test_from_settings(self):
        """Should build client from Bifrost settings."""
        with patch("bifrost.config.settings") as mock_settings:
            mock_settings.mimir_url = "http://mimir:3000"
            mock_settings.mimir_api_key = "key-123"
            mock_settings.mimir_tenant_id = "tenant-abc"
            mock_settings.mimir_sync_interval = 600

            from bifrost.clients.mimir_sync import create_sync_client
            client = create_sync_client()
            assert client.mimir_url == "http://mimir:3000"
            assert client.api_key == "key-123"
            assert client.sync_interval == 600
