"""Database connection and schema management."""

import aiosqlite
import os
from pathlib import Path


_db: aiosqlite.Connection | None = None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant', 'tool')),
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent_id);
"""


async def get_db(db_path: str | None = None) -> aiosqlite.Connection:
    """Get or create the database connection."""
    global _db
    if _db is None:
        if db_path is None:
            from bifrost.config import settings
            db_path = settings.database_path
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(db_path)
        _db.row_factory = aiosqlite.Row
        # Enable WAL mode for better concurrency
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
        await _db.executescript(SCHEMA_SQL)
        await _db.commit()
    return _db


async def close_db():
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
