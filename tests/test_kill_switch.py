"""Tests for kill switch — global emergency stop.

TDD Red Phase: Tests define expected behavior BEFORE implementation.
"""

import pytest

from bifrost.guardrails.kill_switch import KillSwitch


class TestKillSwitch:
    """Test kill switch activation and deactivation."""

    def test_initially_inactive(self):
        ks = KillSwitch()
        assert ks.is_active() is False

    def test_activate(self):
        ks = KillSwitch()
        ks.activate(reason="security incident")
        assert ks.is_active() is True

    def test_resume(self):
        ks = KillSwitch()
        ks.activate(reason="test")
        ks.resume()
        assert ks.is_active() is False

    def test_status_includes_reason(self):
        ks = KillSwitch()
        ks.activate(reason="PII leak detected")
        status = ks.get_status()
        assert status["active"] is True
        assert status["reason"] == "PII leak detected"
        assert "activated_at" in status
