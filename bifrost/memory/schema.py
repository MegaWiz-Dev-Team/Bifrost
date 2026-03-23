"""Memory fact schema — data model for long-term agent memory."""

from dataclasses import dataclass, field


VALID_CATEGORIES = {"fact", "context", "medical", "preference"}


@dataclass
class MemoryFact:
    """A single persistent fact extracted from conversations.

    Categories:
        - fact: General knowledge about the user/context
        - context: Situational context (role, organization, etc.)
        - medical: Clinical facts (diagnoses, allergies, etc.)
        - preference: User preferences (language, format, etc.)
    """

    id: int = 0
    tenant_id: str = "default"
    category: str = "fact"
    content: str = ""
    source: str = ""
    confidence: float = 1.0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "category": self.category,
            "content": self.content,
            "source": self.source,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row) -> "MemoryFact":
        """Create from a database row (tuple or Row)."""
        return cls(
            id=row[0],
            tenant_id=row[1],
            category=row[2],
            content=row[3],
            source=row[4] or "",
            confidence=row[5] if row[5] is not None else 1.0,
            created_at=str(row[6]) if row[6] else "",
            updated_at=str(row[7]) if row[7] else "",
        )
