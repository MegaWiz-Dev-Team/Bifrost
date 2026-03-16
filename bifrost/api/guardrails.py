"""Guardrails API — AI Safety endpoints.

Endpoints:
- POST /guardrails/check — Run all guardrails on text
- POST /guardrails/kill — Activate kill switch
- POST /guardrails/resume — Deactivate kill switch
- GET  /guardrails/status — Kill switch status
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, List

from bifrost.guardrails.pii_filter import detect_pii, mask_pii
from bifrost.guardrails.content_filter import check_content
from bifrost.guardrails.hallucination import check_grounding
from bifrost.guardrails.kill_switch import kill_switch

logger = logging.getLogger("bifrost.guardrails")
router = APIRouter(prefix="/guardrails", tags=["guardrails"])


# --- Request/Response models ---

class GuardrailCheckRequest(BaseModel):
    text: str
    sources: Optional[List[str]] = Field(default=None, description="Sources for grounding check")


class PIIMatchResponse(BaseModel):
    pii_type: str
    matched_text: str


class GuardrailCheckResponse(BaseModel):
    safe: bool
    masked_text: str
    pii_detected: List[PIIMatchResponse]
    content_safe: bool
    content_flags: List[str]
    grounding_score: Optional[float] = None
    grounding_grounded: Optional[bool] = None


class KillSwitchRequest(BaseModel):
    reason: str = "manual"


# --- Endpoints ---

@router.post("/check", response_model=GuardrailCheckResponse)
async def check_guardrails(req: GuardrailCheckRequest):
    """Run all guardrails checks on input text."""
    # PII detection
    pii_matches = detect_pii(req.text)
    masked = mask_pii(req.text)

    # Content filter
    content_result = check_content(req.text)

    # Grounding (only if sources provided)
    grounding_score = None
    grounding_grounded = None
    if req.sources:
        grounding = check_grounding(req.text, req.sources)
        grounding_score = grounding.score
        grounding_grounded = grounding.grounded

    safe = content_result.safe and len(pii_matches) == 0

    return GuardrailCheckResponse(
        safe=safe,
        masked_text=masked,
        pii_detected=[
            PIIMatchResponse(pii_type=m.pii_type.value, matched_text=m.matched_text)
            for m in pii_matches
        ],
        content_safe=content_result.safe,
        content_flags=[c.value for c in content_result.flagged_categories],
        grounding_score=grounding_score,
        grounding_grounded=grounding_grounded,
    )


@router.post("/kill")
async def activate_kill_switch(req: KillSwitchRequest):
    """Activate emergency kill switch — blocks all agent calls."""
    kill_switch.activate(reason=req.reason)
    logger.warning(f"🛑 Kill switch activated: {req.reason}")
    return {"status": "activated", "reason": req.reason}


@router.post("/resume")
async def resume_from_kill_switch():
    """Deactivate kill switch — resume normal operations."""
    kill_switch.resume()
    logger.info("✅ Kill switch deactivated — operations resumed")
    return {"status": "resumed"}


@router.get("/status")
async def get_kill_switch_status():
    """Get current kill switch status."""
    return kill_switch.get_status()
