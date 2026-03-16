"""Tests for handover context builder.

TDD Red Phase: Tests define expected behavior BEFORE implementation.
"""

import pytest

from bifrost.guardrails.handover import build_handover_context


class TestHandover:
    """Test handover context generation."""

    def test_build_context_from_messages(self):
        messages = [
            {"role": "user", "content": "ปวดหัวมาก 3 วันแล้ว"},
            {"role": "assistant", "content": "อาการปวดหัวเริ่มตั้งแต่เมื่อไร?"},
            {"role": "user", "content": "ตั้งแต่วันจันทร์ กินยาแล้วไม่หาย"},
        ]
        ctx = build_handover_context(messages)
        assert ctx.summary is not None
        assert len(ctx.summary) > 0
        assert ctx.message_count == 3

    def test_priority_assignment(self):
        messages = [
            {"role": "user", "content": "เจ็บหน้าอกมาก หายใจไม่ออก"},
        ]
        ctx = build_handover_context(messages)
        assert ctx.priority in ("low", "medium", "high", "critical")

    def test_empty_messages(self):
        ctx = build_handover_context([])
        assert ctx.message_count == 0
        assert ctx.summary == ""
