"""PII Filter — Detect and mask Personally Identifiable Information.

PDPA compliance: Thai ID (13 digits), phone numbers, email, credit cards, bank accounts.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List


class PIIType(str, Enum):
    """Types of PII that can be detected."""
    THAI_ID = "thai_id"
    PHONE = "phone"
    EMAIL = "email"
    CREDIT_CARD = "credit_card"
    BANK_ACCOUNT = "bank_account"


@dataclass
class PIIMatch:
    """A detected PII match."""
    pii_type: PIIType
    matched_text: str
    start: int
    end: int


# Pattern definitions — order matters (most specific first)
_PATTERNS: list[tuple[PIIType, re.Pattern, str]] = [
    # Thai ID: 1-1234-56789-01-2 or 1123456789012
    (
        PIIType.THAI_ID,
        re.compile(r'\b(\d{1}-?\d{4}-?\d{5}-?\d{2}-?\d{1})\b'),
        "[THAI_ID]",
    ),
    # Credit card: 4111-1111-1111-1111 or 4111111111111111
    (
        PIIType.CREDIT_CARD,
        re.compile(r'\b(\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4})\b'),
        "[CREDIT_CARD]",
    ),
    # Phone: 081-234-5678, 0812345678, 091-2345678
    (
        PIIType.PHONE,
        re.compile(r'\b(0[689]\d{1,2}-?\d{3,4}-?\d{4})\b'),
        "[PHONE]",
    ),
    # Email
    (
        PIIType.EMAIL,
        re.compile(r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b'),
        "[EMAIL]",
    ),
    # Bank account: 123-1-12345-1
    (
        PIIType.BANK_ACCOUNT,
        re.compile(r'\b(\d{3}-?\d{1}-?\d{5}-?\d{1})\b'),
        "[BANK_ACCOUNT]",
    ),
]


def detect_pii(text: str) -> List[PIIMatch]:
    """Detect all PII instances in text.

    Returns list of PIIMatch objects with type, matched text, and positions.
    """
    matches: list[PIIMatch] = []
    matched_spans: set[tuple[int, int]] = set()

    for pii_type, pattern, _ in _PATTERNS:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            # Avoid overlapping matches
            if any(s <= span[0] < e or s < span[1] <= e for s, e in matched_spans):
                continue
            matched_spans.add(span)
            matches.append(PIIMatch(
                pii_type=pii_type,
                matched_text=m.group(0),
                start=m.start(),
                end=m.end(),
            ))

    # Sort by position
    matches.sort(key=lambda m: m.start)
    return matches


def mask_pii(text: str) -> str:
    """Replace all PII in text with type-appropriate placeholders.

    Example: "โทร 081-234-5678" → "โทร [PHONE]"
    """
    result = text
    # Process in reverse order to maintain positions
    matches = detect_pii(text)
    for match in reversed(matches):
        placeholder = f"[{match.pii_type.value.upper()}]"
        result = result[:match.start] + placeholder + result[match.end:]
    return result
