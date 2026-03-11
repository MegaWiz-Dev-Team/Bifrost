"""Tracing API endpoints — view execution traces."""

from fastapi import APIRouter, HTTPException
from bifrost.core.tracing import trace_store

router = APIRouter(prefix="/v1/traces", tags=["traces"])


@router.get("/{session_id}")
async def get_traces(session_id: str):
    """Get execution traces for a session."""
    traces = await trace_store.get_by_session(session_id)
    return {
        "session_id": session_id,
        "traces": traces,
        "total": len(traces),
    }


@router.get("/{session_id}/summary")
async def get_trace_summary(session_id: str):
    """Get execution summary for a session."""
    summary = await trace_store.get_summary(session_id)
    return summary
