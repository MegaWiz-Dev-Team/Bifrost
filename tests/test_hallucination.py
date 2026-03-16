"""Tests for hallucination detection — grounding check.

TDD Red Phase: Tests define expected behavior BEFORE implementation.
"""

import pytest

from bifrost.guardrails.hallucination import check_grounding


class TestHallucinationCheck:
    """Test grounding verification."""

    def test_grounded_response(self):
        response = "patient has fever 38.5 degrees celsius headache"
        sources = ["patient came with fever 38.5 degrees celsius and headache symptoms"]
        result = check_grounding(response, sources)
        assert result.grounded is True
        assert result.score >= 0.5

    def test_ungrounded_response(self):
        response = "ผู้ป่วยมีอาการหัวใจวาย ต้องผ่าตัดด่วน"
        sources = ["ผู้ป่วยมาด้วยอาการไข้ 38.5 องศา"]
        result = check_grounding(response, sources)
        assert result.grounded is False
        assert result.score < 0.5

    def test_empty_sources(self):
        response = "ผู้ป่วยมีอาการดี"
        sources = []
        result = check_grounding(response, sources)
        assert result.grounded is False
        assert result.score == 0.0

    def test_threshold_configurable(self):
        response = "some text"
        sources = ["some text here"]
        result = check_grounding(response, sources, threshold=0.9)
        # With high threshold, partial match may not be grounded
        assert isinstance(result.grounded, bool)
        assert 0.0 <= result.score <= 1.0
