"""SLA tracking — uptime %, incident count, MTTR.

Reads health.score history from SQLite. Uptime = fraction of time score >= 60.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query

from app.db import sqlite as sdb
from app.utils.service import WINDOW_MAP

router = APIRouter(prefix="/api", tags=["sla"])

_HEALTHY_THRESHOLD = 60  # score >= 60 = healthy


@router.get("/sla")
def sla(window: str = Query("7d")) -> dict[str, Any]:
    window_s = WINDOW_MAP.get(window, 7 * 86400)
    now = int(time.time())
    since = now - window_s
    step = max(60, window_s // 1440)  # ~1440 points max

    rows = sdb.history("health.score", since, now, step)
    if not rows:
        return {
            "window": window,
            "uptime_pct": None,
            "downtime_s": None,
            "incident_count": 0,
            "mttr_s": None,
            "samples": 0,
        }

    scores = [v for _, v in rows if v is not None]
    if not scores:
        return {"window": window, "uptime_pct": None, "incident_count": 0, "samples": 0}

    healthy = sum(1 for s in scores if s >= _HEALTHY_THRESHOLD)
    uptime_pct = round(100.0 * healthy / len(scores), 2)
    downtime_s = int((len(scores) - healthy) * step)

    # Count incident spans (consecutive unhealthy blocks)
    incidents = []
    in_incident = False
    inc_start = None
    for ts, v in rows:
        if v is None:
            continue
        if v < _HEALTHY_THRESHOLD:
            if not in_incident:
                in_incident = True
                inc_start = ts
        else:
            if in_incident:
                incidents.append((inc_start, ts))
                in_incident = False
    if in_incident:
        incidents.append((inc_start, now))

    incident_durations = [e - s for s, e in incidents]
    mttr_s = int(sum(incident_durations) / len(incident_durations)) if incident_durations else None

    return {
        "window": window,
        "uptime_pct": uptime_pct,
        "downtime_s": downtime_s,
        "incident_count": len(incidents),
        "mttr_s": mttr_s,
        "samples": len(scores),
        "healthy_threshold": _HEALTHY_THRESHOLD,
    }
