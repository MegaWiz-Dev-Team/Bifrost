"""Agent Token — scoped credential system for sub-agents.

Each sub-agent receives a short-lived HMAC-SHA256 signed JWT
with restricted tool access. Sub-agents never see real credentials.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass, field

logger = logging.getLogger("bifrost.odin.agent_token")


@dataclass
class AgentToken:
    """Scoped credential token for a sub-agent.

    Attributes:
        agent_id: Identifier of the sub-agent.
        tenant_id: Tenant this token is scoped to.
        allowed_tools: List of tool names this agent can access.
        ttl_seconds: Time-to-live in seconds (default 900 = 15 min).
        token_id: Unique identifier for this token instance.
        issued_at: Unix timestamp when token was issued.
        expires_at: Unix timestamp when token expires.
    """
    agent_id: str
    tenant_id: str
    allowed_tools: list[str] = field(default_factory=list)
    ttl_seconds: int = 900
    token_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    issued_at: float = field(default_factory=time.time)
    expires_at: float = 0

    def __post_init__(self):
        if self.expires_at == 0:
            self.expires_at = self.issued_at + self.ttl_seconds

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    def to_claims(self) -> dict:
        """Serialize to JWT-compatible claims dict."""
        return {
            "sub": self.agent_id,
            "tid": self.tenant_id,
            "tools": self.allowed_tools,
            "jti": self.token_id,
            "iat": int(self.issued_at),
            "exp": int(self.expires_at),
        }


def _b64_encode(data: bytes) -> str:
    """URL-safe base64 encode without padding."""
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64_decode(s: str) -> bytes:
    """URL-safe base64 decode with padding restoration."""
    s += "=" * (4 - len(s) % 4)
    return urlsafe_b64decode(s)


class AgentTokenIssuer:
    """HMAC-SHA256 token issuer for sub-agent credentials.

    Signs short-lived JWTs containing agent_id, tenant_id,
    and allowed_tools. Validates tokens on the receiving end.
    """

    def __init__(self, secret_key: str):
        self._secret = secret_key.encode("utf-8")

    def issue(
        self,
        agent_id: str,
        tenant_id: str,
        allowed_tools: list[str] | None = None,
        ttl: int = 900,
    ) -> str:
        """Issue a signed agent token.

        Args:
            agent_id: Sub-agent identifier.
            tenant_id: Tenant scope.
            allowed_tools: Tool whitelist (empty = no tool access).
            ttl: Time-to-live in seconds (default 15 min).

        Returns:
            JWT-format string: header.payload.signature
        """
        token = AgentToken(
            agent_id=agent_id,
            tenant_id=tenant_id,
            allowed_tools=allowed_tools or [],
            ttl_seconds=ttl,
        )

        # JWT structure: header.payload.signature
        header = _b64_encode(json.dumps({"alg": "HS256", "typ": "AGT"}).encode())
        payload = _b64_encode(json.dumps(token.to_claims()).encode())
        signing_input = f"{header}.{payload}"
        signature = _b64_encode(
            hmac.new(self._secret, signing_input.encode(), hashlib.sha256).digest()
        )

        logger.info(
            f"Issued agent token: agent={agent_id} tenant={tenant_id} "
            f"tools={len(allowed_tools or [])} ttl={ttl}s"
        )

        return f"{header}.{payload}.{signature}"

    def validate(self, token_str: str) -> AgentToken:
        """Validate a signed agent token.

        Args:
            token_str: JWT-format token string.

        Returns:
            AgentToken with decoded claims.

        Raises:
            ValueError: Token is invalid, expired, or tampered.
        """
        parts = token_str.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token format")

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(
            self._secret, signing_input.encode(), hashlib.sha256
        ).digest()

        try:
            actual_sig = _b64_decode(signature_b64)
        except Exception as e:
            raise ValueError(f"Invalid signature encoding: {e}") from e

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("Invalid token signature")

        # Decode payload
        try:
            claims = json.loads(_b64_decode(payload_b64))
        except Exception as e:
            raise ValueError(f"Invalid payload encoding: {e}") from e

        # Check expiry
        exp = claims.get("exp", 0)
        if time.time() >= exp:
            raise ValueError(f"Token expired at {exp}")

        return AgentToken(
            agent_id=claims.get("sub", ""),
            tenant_id=claims.get("tid", ""),
            allowed_tools=claims.get("tools", []),
            ttl_seconds=exp - claims.get("iat", 0),
            token_id=claims.get("jti", ""),
            issued_at=claims.get("iat", 0),
            expires_at=exp,
        )
