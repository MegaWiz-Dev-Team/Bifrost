"""Mimir Agent Config Sync — periodic sync from Mimir API.

Pulls agent configurations from Mimir's REST API and updates
Bifrost's AgentStore. Supports periodic background refresh.

Usage:
    from bifrost.clients.mimir_sync import create_sync_client

    client = create_sync_client()
    await client.sync_once()        # Manual sync
    await client.start_periodic()   # Background sync loop
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime

from bifrost.core.agents import agent_store

logger = logging.getLogger("bifrost.mimir_sync")


@dataclass
class MimirSyncClient:
    """Syncs agent configs from Mimir API to Bifrost AgentStore.

    Supports:
    - One-shot sync via sync_once()
    - Periodic background sync via start_periodic()
    - Status tracking for health checks
    """

    mimir_url: str
    api_key: str = ""
    tenant_id: str = "default"
    sync_interval: int = 300  # seconds (5 minutes default)

    # Internal state
    _synced: bool = field(default=False, init=False, repr=False)
    _agent_count: int = field(default=0, init=False, repr=False)
    _last_sync: datetime | None = field(default=None, init=False, repr=False)
    _task: asyncio.Task | None = field(default=None, init=False, repr=False)

    async def sync_once(self) -> int:
        """Pull agent configs from Mimir and update local store.

        Returns:
            int: Number of agents synced
        """
        logger.info(f"Syncing agents from Mimir ({self.mimir_url})...")

        count = await agent_store.sync_from_mimir(
            self.mimir_url,
            api_key=self.api_key,
            tenant_id=self.tenant_id,
        )

        self._agent_count = count
        self._synced = count > 0
        self._last_sync = datetime.now()

        if count > 0:
            logger.info(f"Synced {count} agents from Mimir")
        else:
            logger.warning("No agents synced from Mimir (0 returned)")

        return count

    async def start_periodic(self) -> None:
        """Start background periodic sync loop."""
        async def _loop():
            while True:
                try:
                    await self.sync_once()
                except Exception as e:
                    logger.error(f"Periodic sync error: {e}")
                await asyncio.sleep(self.sync_interval)

        self._task = asyncio.create_task(_loop())
        logger.info(
            f"Periodic Mimir sync started (every {self.sync_interval}s)"
        )

    async def stop_periodic(self) -> None:
        """Stop background periodic sync loop."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Periodic Mimir sync stopped")

    @property
    def status(self) -> dict:
        """Current sync status for health checks."""
        return {
            "synced": self._synced,
            "agent_count": self._agent_count,
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "sync_interval": self.sync_interval,
            "mimir_url": self.mimir_url,
        }


def create_sync_client() -> MimirSyncClient:
    """Factory — build MimirSyncClient from Bifrost settings."""
    from bifrost.config import settings

    return MimirSyncClient(
        mimir_url=settings.mimir_url,
        api_key=settings.mimir_api_key,
        tenant_id=settings.mimir_tenant_id,
        sync_interval=getattr(settings, "mimir_sync_interval", 300),
    )
