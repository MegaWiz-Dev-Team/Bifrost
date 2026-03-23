"""Tests for Long-Term Memory system — Sprint 35 Part B (TDD: written FIRST)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiosqlite
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixture: in-memory SQLite DB with schema
# ---------------------------------------------------------------------------

MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    category TEXT NOT NULL CHECK(category IN ('fact', 'context', 'medical', 'preference')),
    content TEXT NOT NULL,
    source TEXT DEFAULT '',
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_facts_tenant ON memory_facts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_facts_category ON memory_facts(tenant_id, category);
CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_dedup ON memory_facts(tenant_id, content);
"""


@pytest.fixture
async def memory_db(tmp_path: Path):
    """Create a temporary SQLite database with memory schema."""
    db_path = str(tmp_path / "test_memory.db")
    db = await aiosqlite.connect(db_path)
    await db.executescript(MEMORY_SCHEMA)
    await db.commit()
    yield db
    await db.close()


# ===========================================================================
# Test: MemoryFact schema
# ===========================================================================

class TestMemorySchema:
    """Test MemoryFact dataclass."""

    def test_memory_fact_creation(self):
        """Create a MemoryFact with all fields."""
        from bifrost.memory.schema import MemoryFact

        fact = MemoryFact(
            id=1,
            tenant_id="tenant-abc",
            category="fact",
            content="User prefers dark mode.",
            source="session-123",
            confidence=0.9,
        )

        assert fact.tenant_id == "tenant-abc"
        assert fact.category == "fact"
        assert fact.content == "User prefers dark mode."
        assert fact.confidence == 0.9

    def test_memory_fact_valid_categories(self):
        """Validate category enum values."""
        from bifrost.memory.schema import VALID_CATEGORIES

        assert "fact" in VALID_CATEGORIES
        assert "context" in VALID_CATEGORIES
        assert "medical" in VALID_CATEGORIES
        assert "preference" in VALID_CATEGORIES

    def test_memory_fact_to_dict(self):
        """MemoryFact serializes to dict."""
        from bifrost.memory.schema import MemoryFact

        fact = MemoryFact(
            id=1,
            tenant_id="t1",
            category="preference",
            content="Likes Thai food",
        )

        d = fact.to_dict()
        assert d["category"] == "preference"
        assert d["content"] == "Likes Thai food"
        assert "tenant_id" in d


# ===========================================================================
# Test: MemoryStore — CRUD operations
# ===========================================================================

class TestMemoryStore:
    """Test MemoryStore with real SQLite."""

    @pytest.mark.asyncio
    async def test_add_and_get_facts(self, memory_db):
        """Add facts and retrieve by tenant."""
        from bifrost.memory.store import MemoryStore

        store = MemoryStore(db=memory_db)
        await store.add_fact("tenant-1", "fact", "User is a doctor.")
        await store.add_fact("tenant-1", "preference", "Prefers English responses.")

        facts = await store.get_facts("tenant-1")
        assert len(facts) == 2
        contents = {f.content for f in facts}
        assert "User is a doctor." in contents
        assert "Prefers English responses." in contents

    @pytest.mark.asyncio
    async def test_dedup_facts(self, memory_db):
        """Duplicate content for same tenant is ignored."""
        from bifrost.memory.store import MemoryStore

        store = MemoryStore(db=memory_db)
        await store.add_fact("tenant-1", "fact", "User is a doctor.")
        await store.add_fact("tenant-1", "fact", "User is a doctor.")  # duplicate

        facts = await store.get_facts("tenant-1")
        assert len(facts) == 1

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, memory_db):
        """Tenant A cannot see tenant B's facts."""
        from bifrost.memory.store import MemoryStore

        store = MemoryStore(db=memory_db)
        await store.add_fact("tenant-a", "fact", "Tenant A info")
        await store.add_fact("tenant-b", "fact", "Tenant B info")

        facts_a = await store.get_facts("tenant-a")
        facts_b = await store.get_facts("tenant-b")

        assert len(facts_a) == 1
        assert facts_a[0].content == "Tenant A info"
        assert len(facts_b) == 1
        assert facts_b[0].content == "Tenant B info"

    @pytest.mark.asyncio
    async def test_get_facts_by_category(self, memory_db):
        """Filter facts by category."""
        from bifrost.memory.store import MemoryStore

        store = MemoryStore(db=memory_db)
        await store.add_fact("t1", "fact", "General fact")
        await store.add_fact("t1", "medical", "Patient has diabetes")
        await store.add_fact("t1", "preference", "Likes dark mode")

        medical = await store.get_facts("t1", categories=["medical"])
        assert len(medical) == 1
        assert medical[0].content == "Patient has diabetes"

    @pytest.mark.asyncio
    async def test_get_facts_limit(self, memory_db):
        """Respect limit parameter."""
        from bifrost.memory.store import MemoryStore

        store = MemoryStore(db=memory_db)
        for i in range(20):
            await store.add_fact("t1", "fact", f"Fact number {i}")

        facts = await store.get_facts("t1", limit=5)
        assert len(facts) == 5

    @pytest.mark.asyncio
    async def test_search_facts(self, memory_db):
        """Search facts by keyword."""
        from bifrost.memory.store import MemoryStore

        store = MemoryStore(db=memory_db)
        await store.add_fact("t1", "fact", "User is a cardiologist.")
        await store.add_fact("t1", "fact", "User likes pizza.")
        await store.add_fact("t1", "medical", "Patient has heart disease.")

        results = await store.search_facts("t1", "heart")
        assert len(results) == 1
        assert "heart" in results[0].content.lower()

    @pytest.mark.asyncio
    async def test_delete_fact(self, memory_db):
        """Delete a fact by ID."""
        from bifrost.memory.store import MemoryStore

        store = MemoryStore(db=memory_db)
        await store.add_fact("t1", "fact", "Temporary fact")
        facts = await store.get_facts("t1")
        assert len(facts) == 1

        deleted = await store.delete_fact("t1", facts[0].id)
        assert deleted is True

        facts = await store.get_facts("t1")
        assert len(facts) == 0

    @pytest.mark.asyncio
    async def test_count_facts(self, memory_db):
        """Count facts per tenant."""
        from bifrost.memory.store import MemoryStore

        store = MemoryStore(db=memory_db)
        await store.add_fact("t1", "fact", "Fact 1")
        await store.add_fact("t1", "fact", "Fact 2")
        await store.add_fact("t2", "fact", "Fact 3")

        assert await store.count_facts("t1") == 2
        assert await store.count_facts("t2") == 1
        assert await store.count_facts("t3") == 0


# ===========================================================================
# Test: Memory prompt formatting
# ===========================================================================

class TestMemoryPrompt:
    """Test memory injection into system prompt."""

    def test_format_memory_prompt(self):
        """Render facts into a <memory> block."""
        from bifrost.memory.schema import MemoryFact
        from bifrost.memory.store import MemoryStore

        facts = [
            MemoryFact(id=1, tenant_id="t1", category="fact", content="User is a doctor."),
            MemoryFact(id=2, tenant_id="t1", category="preference", content="Prefers Thai language."),
        ]

        prompt = MemoryStore.format_memory_prompt(facts)

        assert "<memory>" in prompt
        assert "</memory>" in prompt
        assert "User is a doctor." in prompt
        assert "Prefers Thai language." in prompt

    def test_format_memory_prompt_empty(self):
        """Empty facts returns empty string."""
        from bifrost.memory.store import MemoryStore

        prompt = MemoryStore.format_memory_prompt([])
        assert prompt == ""


# ===========================================================================
# Test: MemoryUpdater — fact extraction
# ===========================================================================

class TestMemoryUpdater:
    """Test LLM-based fact extraction."""

    @pytest.mark.asyncio
    async def test_extract_facts_from_messages(self):
        """Extract facts from a conversation using mocked LLM."""
        from bifrost.memory.updater import MemoryUpdater

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{
                "message": {
                    "content": '["User is a cardiologist", "User prefers English responses"]'
                },
                "finish_reason": "stop",
            }],
        }

        updater = MemoryUpdater(heimdall=mock_heimdall)
        facts = await updater.extract_facts([
            {"role": "user", "content": "I'm a cardiologist. Please respond in English."},
            {"role": "assistant", "content": "Of course, doctor. How can I help?"},
        ])

        assert len(facts) == 2
        assert "cardiologist" in facts[0].lower()
        assert "English" in facts[1]

    @pytest.mark.asyncio
    async def test_extract_facts_handles_invalid_json(self):
        """Gracefully handle invalid JSON from LLM."""
        from bifrost.memory.updater import MemoryUpdater

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{
                "message": {"content": "Not valid JSON at all"},
                "finish_reason": "stop",
            }],
        }

        updater = MemoryUpdater(heimdall=mock_heimdall)
        facts = await updater.extract_facts([
            {"role": "user", "content": "Hello"},
        ])

        assert facts == []


# ===========================================================================
# Test: Executor integration with memory
# ===========================================================================

class TestMemoryExecutorIntegration:
    """Test memory injection in AgentExecutor."""

    @pytest.mark.asyncio
    async def test_executor_injects_memory(self, memory_db):
        """Executor injects <memory> block when memory_store is provided."""
        from bifrost.core.executor import AgentExecutor
        from bifrost.memory.store import MemoryStore

        store = MemoryStore(db=memory_db)
        await store.add_fact("tenant-1", "fact", "User is a pediatrician.")
        await store.add_fact("tenant-1", "preference", "Prefers concise answers.")

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{
                "message": {"content": "Hello, doctor!"},
                "finish_reason": "stop",
            }],
        }

        mock_registry = MagicMock()
        mock_registry.get_openai_tools.return_value = []

        executor = AgentExecutor(
            heimdall=mock_heimdall,
            tool_registry=mock_registry,
            memory_store=store,
            tenant_id="tenant-1",
        )

        result = await executor.execute(
            system_prompt="You are a helpful assistant.",
            user_input="Hello",
        )

        # Check system prompt contains memory block
        call_args = mock_heimdall.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages") or call_args[0][0]
        system_msg = messages[0]["content"]

        assert "<memory>" in system_msg
        assert "pediatrician" in system_msg

    @pytest.mark.asyncio
    async def test_executor_no_memory_without_store(self):
        """Without memory_store, no <memory> block is injected."""
        from bifrost.core.executor import AgentExecutor

        mock_heimdall = AsyncMock()
        mock_heimdall.chat_completion.return_value = {
            "choices": [{
                "message": {"content": "Hi!"},
                "finish_reason": "stop",
            }],
        }

        mock_registry = MagicMock()
        mock_registry.get_openai_tools.return_value = []

        executor = AgentExecutor(
            heimdall=mock_heimdall,
            tool_registry=mock_registry,
        )

        await executor.execute(
            system_prompt="You are a helper.",
            user_input="Hi",
        )

        call_args = mock_heimdall.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages") or call_args[0][0]
        system_msg = messages[0]["content"]

        assert "<memory>" not in system_msg
