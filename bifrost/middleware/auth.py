"""JWT Auth Middleware — protect Bifrost API endpoints via Yggdrasil.

Uses Yggdrasil's `validate_jwt` to verify Zitadel-issued JWTs.
Public endpoints (health, docs, A2A agent card) are excluded.
"""

import logging

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("bifrost.auth")

# Routes that NEVER require authentication
PUBLIC_PATHS = frozenset({
    "/healthz",
    "/readyz",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/.well-known/agent.json",
})

# Path prefixes that are always public
PUBLIC_PREFIXES = (
    "/docs",
    "/redoc",
    "/a2a/",
)


async def validate_jwt(token: str) -> "TokenClaims":
    """Validate JWT via Yggdrasil middleware.

    Separated for easy mocking in tests.
    """
    from yggdrasil.middleware import validate_jwt as ygg_validate
    return await ygg_validate(token)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that validates JWT Bearer tokens.

    Skips authentication for:
    - Health endpoints (/healthz, /readyz)
    - OpenAPI docs (/docs, /redoc, /openapi.json)
    - A2A agent card (/.well-known/agent.json)
    - A2A protocol endpoints (/a2a/*)

    When auth_enabled=False (in settings), all requests pass through.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        from bifrost.config import settings
        path = request.url.path

        # Always skip public endpoints
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        # Skip auth if disabled (dev mode) — read from settings at request time
        if not settings.auth_enabled:
            return await call_next(request)

        # Extract Bearer token
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[7:]  # Strip "Bearer "

        try:
            claims = await validate_jwt(token)
            # Attach claims to request state for downstream use
            request.state.claims = claims
        except Exception as e:
            logger.warning(f"JWT validation failed: {e}")
            return JSONResponse(
                status_code=401,
                content={"detail": f"Invalid token: {e}"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)
