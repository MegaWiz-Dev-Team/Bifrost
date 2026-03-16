"""Tests for PII filter — PDPA compliance.

TDD Red Phase: These tests define the expected behavior BEFORE implementation.
"""

import pytest

from bifrost.guardrails.pii_filter import detect_pii, mask_pii, PIIType


class TestDetectPII:
    """Test PII detection across all pattern types."""

    def test_detect_thai_id_with_dashes(self):
        text = "เลขบัตรประชาชน 1-1234-56789-01-2 ครับ"
        matches = detect_pii(text)
        assert len(matches) == 1
        assert matches[0].pii_type == PIIType.THAI_ID
        assert matches[0].matched_text == "1-1234-56789-01-2"

    def test_detect_thai_id_without_dashes(self):
        text = "ID: 1123456789012"
        matches = detect_pii(text)
        assert len(matches) == 1
        assert matches[0].pii_type == PIIType.THAI_ID

    def test_detect_phone_number(self):
        text = "โทร 081-234-5678"
        matches = detect_pii(text)
        assert len(matches) == 1
        assert matches[0].pii_type == PIIType.PHONE

    def test_detect_phone_without_dashes(self):
        text = "เบอร์ 0812345678"
        matches = detect_pii(text)
        assert len(matches) == 1
        assert matches[0].pii_type == PIIType.PHONE

    def test_detect_email(self):
        text = "ส่งมาที่ user@example.com นะ"
        matches = detect_pii(text)
        assert len(matches) == 1
        assert matches[0].pii_type == PIIType.EMAIL

    def test_detect_credit_card(self):
        text = "บัตรเครดิต 4111-1111-1111-1111"
        matches = detect_pii(text)
        assert len(matches) == 1
        assert matches[0].pii_type == PIIType.CREDIT_CARD

    def test_detect_multiple_pii(self):
        text = "ชื่อ สมชาย เลข 1-1234-56789-01-2 โทร 091-234-5678 อีเมล test@mail.com"
        matches = detect_pii(text)
        assert len(matches) == 3  # Thai ID + phone + email

    def test_no_pii(self):
        text = "สวัสดีครับ วันนี้อากาศดี"
        matches = detect_pii(text)
        assert len(matches) == 0


class TestMaskPII:
    """Test PII masking (replacement)."""

    def test_mask_thai_id(self):
        text = "เลขบัตร 1-1234-56789-01-2"
        masked = mask_pii(text)
        assert "[THAI_ID]" in masked
        assert "1234" not in masked

    def test_mask_preserves_non_pii(self):
        text = "สวัสดีครับ โทร 081-234-5678 ขอบคุณ"
        masked = mask_pii(text)
        assert "สวัสดีครับ" in masked
        assert "ขอบคุณ" in masked
        assert "[PHONE]" in masked
        assert "081" not in masked
