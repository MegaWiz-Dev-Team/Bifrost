"""Execution tracing — structured logging of agent execution.

Records every step of the ReAct loop for observability,
debugging, and metrics collection.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from bifrost.db.connection import get_db


@dataclass
class TraceRecord:
    """A single execution trace record."""
    session_id: str
    agent_id: str
    step: int
    type: str  # "llm_call", "tool_call", "tool_result", "final_answer", "error", "delegation"
    content: str
    tool_name: str | None = None
    tool_args: dict | None = None
    duration_ms: float = 0
    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# Schema for traces table
TRACES_SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    type TEXT NOT NULL,
    content TEXT,
    tool_name TEXT,
    tool_args TEXT,
    duration_ms REAL DEFAULT 0,
    model TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_traces_session ON traces(session_id);
"""


class TraceStore:
    """Persists execution traces to SQLite."""

    _initialized = False

    async def _ensure_table(self):
        if not self._initialized:
            db = await get_db()
            await db.executescript(TRACES_SCHEMA)
            await db.commit()
            self._initialized = True

    async def save(self, record: TraceRecord) -> int:
        """Save a trace record. Returns the record ID."""
        await self._ensure_table()
        db = await get_db()
        cursor = await db.execute(
            """INSERT INTO traces
               (session_id, agent_id, step, type, content, tool_name, tool_args,
                duration_ms, model, tokens_in, tokens_out, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.session_id, record.agent_id, record.step, record.type,
                record.content, record.tool_name,
                json.dumps(record.tool_args) if record.tool_args else None,
                record.duration_ms, record.model,
                record.tokens_in, record.tokens_out, record.timestamp,
            ),
        )
        await db.commit()
        return cursor.lastrowid

    async def get_by_session(self, session_id: str) -> list[dict]:
        """Get all traces for a session."""
        await self._ensure_table()
        db = await get_db()
        cursor = await db.execute(
            """SELECT session_id, agent_id, step, type, content, tool_name, tool_args,
                      duration_ms, model, tokens_in, tokens_out, timestamp
               FROM traces WHERE session_id = ? ORDER BY id ASC""",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "session_id": r[0], "agent_id": r[1], "step": r[2], "type": r[3],
                "content": r[4], "tool_name": r[5],
                "tool_args": json.loads(r[6]) if r[6] else None,
                "duration_ms": r[7], "model": r[8],
                "tokens_in": r[9], "tokens_out": r[10], "timestamp": r[11],
            }
            for r in rows
        ]

    async def get_summary(self, session_id: str) -> dict:
        """Get execution summary for a session."""
        traces = await self.get_by_session(session_id)
        if not traces:
            return {"session_id": session_id, "total_steps": 0}

        total_duration = sum(t.get("duration_ms", 0) for t in traces)
        tool_calls = [t for t in traces if t["type"] == "tool_call"]
        errors = [t for t in traces if t["type"] == "error"]

        return {
            "session_id": session_id,
            "agent_id": traces[0]["agent_id"],
            "total_steps": len(traces),
            "total_duration_ms": round(total_duration, 2),
            "tool_calls": len(tool_calls),
            "errors": len(errors),
            "tools_used": list(set(t["tool_name"] for t in tool_calls if t["tool_name"])),
        }


# Singleton
trace_store = TraceStore()
