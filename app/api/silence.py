"""Alert silence windows — maintenance mode suppresses webhook alerts.

POST /api/alerts/silence  {"duration_minutes": 60}   → mute for 1 hour
GET  /api/alerts/silence                              → current status
DELETE /api/alerts/silence                            → clear immediately
"""

from __future__ import annotations

import time

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.alerts.router import alert_router

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class SilenceRequest(BaseModel):
    duration_minutes: int = Field(60, ge=1, le=1440)


@router.post("/silence")
def silence(body: SilenceRequest) -> dict:
    until = int(time.time()) + body.duration_minutes * 60
    alert_router.silence_until = until
    return {
        "silenced": True,
        "until": until,
        "duration_minutes": body.duration_minutes,
    }


@router.get("/silence")
def get_silence() -> dict:
    now = int(time.time())
    until = getattr(alert_router, "silence_until", 0)
    active = until > now
    return {
        "silenced": active,
        "until": until if active else None,
        "remaining_s": max(0, until - now) if active else 0,
    }


@router.delete("/silence")
def clear_silence() -> dict:
    alert_router.silence_until = 0
    return {"silenced": False}
