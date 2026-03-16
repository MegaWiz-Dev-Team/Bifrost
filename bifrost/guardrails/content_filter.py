"""Content Filter — Block dangerous LLM output categories.

Detects: medical advice without disclaimer, financial guarantees,
personal data requests.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class ContentCategory(str, Enum):
    """Content categories that can be flagged."""
    MEDICAL_ADVICE = "medical_advice_without_disclaimer"
    FINANCIAL_GUARANTEE = "financial_guarantee"
    PERSONAL_DATA_REQUEST = "personal_data_request"


@dataclass
class ContentCheckResult:
    """Result of content check."""
    safe: bool
    flagged_categories: List[ContentCategory] = field(default_factory=list)
    details: str = ""


# Medical keywords (Thai + English)
_MEDICAL_KEYWORDS = re.compile(
    r'(ควรกิน|ควรทาน|ให้กิน|ให้ทาน|ควรใช้ยา|prescribe|take\s+\d+\s*(mg|tablet|pill|เม็ด|แคปซูล))',
    re.IGNORECASE,
)

# Medical disclaimer (Thai)
_MEDICAL_DISCLAIMER = re.compile(
    r'(ปรึกษาแพทย์|พบแพทย์|หมอ|consult.*doctor|medical\s+professional|ควรไปพบ)',
    re.IGNORECASE,
)

# Financial guarantee keywords
_FINANCIAL_GUARANTEE = re.compile(
    r'(รับรองผลตอบแทน|การันตี.*กำไร|guaranteed\s+return|รับประกัน.*ผลตอบแทน|ผลตอบแทนแน่นอน)',
    re.IGNORECASE,
)

# Personal data request keywords
_PERSONAL_DATA_REQUEST = re.compile(
    r'(ส่งเลขบัตรประชาชน|ส่งเลขบัตร|ขอเลขบัตร|send.*id\s*card|provide.*national\s*id|ขอเลขบัญชี|ส่งเลขบัญชี)',
    re.IGNORECASE,
)


def check_content(text: str) -> ContentCheckResult:
    """Check text for dangerous content categories.

    Returns ContentCheckResult with safe=True if no issues found.
    """
    flagged: list[ContentCategory] = []

    # Medical advice without disclaimer
    if _MEDICAL_KEYWORDS.search(text) and not _MEDICAL_DISCLAIMER.search(text):
        flagged.append(ContentCategory.MEDICAL_ADVICE)

    # Financial guarantee
    if _FINANCIAL_GUARANTEE.search(text):
        flagged.append(ContentCategory.FINANCIAL_GUARANTEE)

    # Personal data request
    if _PERSONAL_DATA_REQUEST.search(text):
        flagged.append(ContentCategory.PERSONAL_DATA_REQUEST)

    return ContentCheckResult(
        safe=len(flagged) == 0,
        flagged_categories=flagged,
        details=f"Flagged {len(flagged)} categories" if flagged else "Content is safe",
    )
