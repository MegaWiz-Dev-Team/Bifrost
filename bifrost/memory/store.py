"""Memory store — SQLite-backed persistent fact storage (per-tenant).

Provides CRUD operations for long-term memory facts with:
- Deduplication via UNIQUE index on (tenant_id, content)
- Per-tenant isolation
- Category-based filtering
- Keyword search
"""

import logging
from typing import TYPE_CHECKING

import aiosqlite

from bifrost.memory.schema import MemoryFact

if TYPE_CHECKING:
    pass

logger = logging.getLogger("bifrost.memory")


class MemoryStore:
    """Persistent fact store backed by SQLite."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def add_fact(
        self,
        tenant_id: str,
        category: str,
        content: str,
        source: str = "",
        confidence: float = 1.0,
    ) -> bool:
        """Add a fact. Dedup: silently skips if identical content exists for tenant.

        Returns True if inserted, False if duplicate.
        """
        try:
            await self.db.execute(
                """INSERT OR IGNORE INTO memory_facts
                   (tenant_id, category, content, source, confidence)
                   VALUES (?, ?, ?, ?, ?)""",
                (tenant_id, category, content, source, confidence),
            )
            await self.db.commit()
            return True
        except Exception as e:
            logger.warning(f"Failed to add fact: {e}")
            return False

    async def get_facts(
        self,
        tenant_id: str,
        limit: int = 15,
        categories: list[str] | None = None,
    ) -> list[MemoryFact]:
        """Get facts for a tenant, ordered by most recent first.

        Args:
            tenant_id: Tenant identifier.
            limit: Max facts to return (default 15 for context window efficiency).
            categories: Optional filter by category list.
        """
        if categories:
            placeholders = ",".join("?" for _ in categories)
            cursor = await self.db.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                f"""SELECT id, tenant_id, category, content, source, confidence,
                       created_at, updated_at
                FROM memory_facts
                WHERE tenant_id = ? AND category IN ({placeholders})
                ORDER BY updated_at DESC LIMIT ?""",
                (tenant_id, *categories, limit),
            )
        else:
            cursor = await self.db.execute(
                """SELECT id, tenant_id, category, content, source, confidence,
                       created_at, updated_at
                FROM memory_facts
                WHERE tenant_id = ?
                ORDER BY updated_at DESC LIMIT ?""",
                (tenant_id, limit),
            )

        rows = await cursor.fetchall()
        return [MemoryFact.from_row(row) for row in rows]

    async def search_facts(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
    ) -> list[MemoryFact]:
        """Search facts by keyword (LIKE match)."""
        cursor = await self.db.execute(
            """SELECT id, tenant_id, category, content, source, confidence,
                   created_at, updated_at
            FROM memory_facts
            WHERE tenant_id = ? AND content LIKE ?
            ORDER BY updated_at DESC LIMIT ?""",
            (tenant_id, f"%{query}%", limit),
        )
        rows = await cursor.fetchall()
        return [MemoryFact.from_row(row) for row in rows]

    async def delete_fact(self, tenant_id: str, fact_id: int) -> bool:
        """Delete a fact by ID (scoped to tenant)."""
        cursor = await self.db.execute(
            "DELETE FROM memory_facts WHERE id = ? AND tenant_id = ?",
            (fact_id, tenant_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def count_facts(self, tenant_id: str) -> int:
        """Count facts for a tenant."""
        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE tenant_id = ?",
            (tenant_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    @staticmethod
    def format_memory_prompt(facts: list[MemoryFact]) -> str:
        """Render facts into a <memory> block for system prompt injection.

        Format:
            <memory>
            - [category] fact content
            </memory>
        """
        if not facts:
            return ""

        lines = ["<memory>"]
        for fact in facts:
            lines.append(f"- [{fact.category}] {fact.content}")
        lines.append("</memory>")
        return "\n".join(lines)
