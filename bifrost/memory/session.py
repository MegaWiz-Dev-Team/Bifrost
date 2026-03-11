"""Session manager — conversation history persistence."""

import json
import uuid
from datetime import datetime, timezone

from bifrost.db.connection import get_db


class SessionManager:
    """Manages agent conversation sessions in SQLite."""

    async def create_session(self, agent_id: str, metadata: dict | None = None) -> str:
        """Create a new session and return its ID."""
        db = await get_db()
        session_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO sessions (id, agent_id, metadata) VALUES (?, ?, ?)",
            (session_id, agent_id, json.dumps(metadata or {})),
        )
        await db.commit()
        return session_id

    async def get_session(self, session_id: str) -> dict | None:
        """Get session details by ID."""
        db = await get_db()
        cursor = await db.execute(
            "SELECT id, agent_id, metadata, created_at, updated_at FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "agent_id": row[1],
            "metadata": json.loads(row[2]),
            "created_at": row[3],
            "updated_at": row[4],
        }

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str | None = None,
        tool_calls: list | None = None,
        tool_call_id: str | None = None,
        name: str | None = None,
    ) -> int:
        """Add a message to a session. Returns the message ID."""
        db = await get_db()
        cursor = await db.execute(
            """INSERT INTO messages (session_id, role, content, tool_calls, tool_call_id, name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session_id, role, content,
                json.dumps(tool_calls) if tool_calls else None,
                tool_call_id, name,
            ),
        )
        await db.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), session_id),
        )
        await db.commit()
        return cursor.lastrowid

    async def get_history(self, session_id: str, limit: int = 50) -> list[dict]:
        """Get conversation history for a session."""
        db = await get_db()
        cursor = await db.execute(
            """SELECT role, content, tool_calls, tool_call_id, name
               FROM messages WHERE session_id = ?
               ORDER BY created_at ASC LIMIT ?""",
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        messages = []
        for row in rows:
            msg: dict = {"role": row[0]}
            if row[1] is not None:
                msg["content"] = row[1]
            if row[2] is not None:
                msg["tool_calls"] = json.loads(row[2])
            if row[3] is not None:
                msg["tool_call_id"] = row[3]
            if row[4] is not None:
                msg["name"] = row[4]
            messages.append(msg)
        return messages

    async def list_sessions(self, agent_id: str | None = None, limit: int = 20) -> list[dict]:
        """List sessions, optionally filtered by agent_id."""
        db = await get_db()
        if agent_id:
            cursor = await db.execute(
                "SELECT id, agent_id, created_at, updated_at FROM sessions WHERE agent_id = ? ORDER BY updated_at DESC LIMIT ?",
                (agent_id, limit),
            )
        else:
            cursor = await db.execute(
                "SELECT id, agent_id, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [{"id": r[0], "agent_id": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and its messages."""
        db = await get_db()
        cursor = await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
        return cursor.rowcount > 0
