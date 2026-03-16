"""Kill Switch — Global emergency stop for all agent calls.

Thread-safe mechanism to immediately halt all AI agent operations.
POST /guardrails/kill → 503 on all agent calls.
"""

import threading
from datetime import datetime, timezone
from typing import Optional


class KillSwitch:
    """Global kill switch for AI agent operations.

    Thread-safe — can be activated from any request handler.
    """

    def __init__(self):
        self._active = threading.Event()
        self._reason: str = ""
        self._activated_at: Optional[str] = None
        self._lock = threading.Lock()

    def activate(self, reason: str = "manual") -> None:
        """Activate kill switch — blocks all agent calls."""
        with self._lock:
            self._active.set()
            self._reason = reason
            self._activated_at = datetime.now(timezone.utc).isoformat()

    def resume(self) -> None:
        """Deactivate kill switch — resume normal operations."""
        with self._lock:
            self._active.clear()
            self._reason = ""
            self._activated_at = None

    def is_active(self) -> bool:
        """Check if kill switch is currently active."""
        return self._active.is_set()

    def get_status(self) -> dict:
        """Get current kill switch status."""
        with self._lock:
            return {
                "active": self._active.is_set(),
                "reason": self._reason,
                "activated_at": self._activated_at,
            }


# Singleton instance
kill_switch = KillSwitch()
