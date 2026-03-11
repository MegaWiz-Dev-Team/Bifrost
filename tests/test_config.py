"""Tests for config module."""

import os
import pytest
from bifrost.config import Settings


class TestSettings:
    def test_default_values(self):
        s = Settings(_env_file=None)  # Don't load .env
        assert s.heimdall_url == "http://localhost:8080"
        assert s.bifrost_port == 8100
        assert s.max_iterations == 10
        assert s.max_execution_time == 120
        assert s.default_model == "qwen3.5"
        assert s.log_level == "INFO"

    def test_custom_values(self, monkeypatch):
        monkeypatch.setenv("HEIMDALL_URL", "http://custom:9999")
        monkeypatch.setenv("BIFROST_PORT", "9100")
        monkeypatch.setenv("MAX_ITERATIONS", "5")
        s = Settings(_env_file=None)
        assert s.heimdall_url == "http://custom:9999"
        assert s.bifrost_port == 9100
        assert s.max_iterations == 5
