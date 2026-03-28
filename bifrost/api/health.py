"""Health check endpoints."""

from fastapi import APIRouter
from bifrost.clients.heimdall import HeimdallClient
from bifrost.config import settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
@router.get("/v1/healthz")
async def healthz():
    """Liveness probe — always returns 200."""
    return {"status": "ok", "service": "bifrost", "version": "0.1.0"}


@router.get("/readyz")
@router.get("/v1/readyz")
async def readyz():
    """Readiness probe — checks Heimdall connectivity."""
    client = HeimdallClient()
    heimdall_ok = await client.health_check()
    await client.close()

    return {
        "status": "ready" if heimdall_ok else "degraded",
        "heimdall": {
            "url": settings.heimdall_url,
            "connected": heimdall_ok,
        },
    }
