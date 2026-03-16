"""Tests for content filter — block dangerous LLM outputs.

TDD Red Phase: Tests define expected behavior BEFORE implementation.
"""

import pytest

from bifrost.guardrails.content_filter import check_content, ContentCategory


class TestContentFilter:
    """Test content category detection and blocking."""

    def test_medical_advice_without_disclaimer(self):
        text = "คุณควรกินยา Paracetamol วันละ 3 เม็ด"
        result = check_content(text)
        assert not result.safe
        assert ContentCategory.MEDICAL_ADVICE in result.flagged_categories

    def test_medical_advice_with_disclaimer_is_safe(self):
        text = "คุณควรกินยา Paracetamol วันละ 3 เม็ด กรุณาปรึกษาแพทย์ก่อนใช้ยา"
        result = check_content(text)
        assert result.safe

    def test_financial_guarantee(self):
        text = "รับรองผลตอบแทน 20% ต่อปี guaranteed returns"
        result = check_content(text)
        assert not result.safe
        assert ContentCategory.FINANCIAL_GUARANTEE in result.flagged_categories

    def test_personal_data_request(self):
        text = "กรุณาส่งเลขบัตรประชาชนมาให้ด้วย"
        result = check_content(text)
        assert not result.safe
        assert ContentCategory.PERSONAL_DATA_REQUEST in result.flagged_categories

    def test_safe_content(self):
        text = "สวัสดีครับ วันนี้มีอะไรให้ช่วยไหม?"
        result = check_content(text)
        assert result.safe
        assert len(result.flagged_categories) == 0
