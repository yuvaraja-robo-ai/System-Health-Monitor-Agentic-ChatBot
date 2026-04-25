"""Incident timeline — merge anomalies, crashes, log errors into chronological view."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from app.analytics.anomaly import detector as anomaly_detector
from app.db import duckdb as ldb
from app.db import sqlite as sdb

router = APIRouter(prefix="/api", tags=["timeline"])


@router.get("/timeline")
def timeline(
    window: int = Query(3600, ge=60, le=86400, description="lookback seconds"),
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    now = int(time.time())
    since = now - window
    events: list[dict[str, Any]] = []

    # Anomaly history
    for a in anomaly_detector.history(limit=500):
        ts = a.get("ts") or 0
        if ts < since:
            continue
        events.append({
            "ts": ts,
            "kind": "anomaly",
            "severity": "warn",
            "source": a.get("metric", "?"),
            "message": f"{a['metric']} z={a.get('z','?')} value={a.get('value','?')}",
        })

    # Crash events
    for e in sdb.recent_events("crash.", since, limit=200):
        payload = e.get("payload") or {}
        events.append({
            "ts": e.get("ts", 0),
            "kind": "crash",
            "severity": "err",
            "source": payload.get("unit") or payload.get("message") or "?",
            "message": f"crash: {payload.get('signal','?')} — {payload.get('unit','?')}",
        })

    # Unit state change events
    for e in sdb.recent_events("unit.", since, limit=200):
        payload = e.get("payload") or {}
        state = payload.get("active_state", "")
        sev = "err" if state == "failed" else "warn"
        events.append({
            "ts": e.get("ts", 0),
            "kind": "unit",
            "severity": sev,
            "source": payload.get("unit", "?"),
            "message": f"unit {payload.get('unit','?')} → {state}",
        })

    # Log error clusters (snapshot — not per-event)
    for row in ldb.cluster_logs(since, limit=50):
        if row.get("level") not in ("ERROR", "CRITICAL", "CRIT"):
            continue
        last_seen = row.get("last")
        if isinstance(last_seen, str):
            try:
                last_ts = int(datetime.fromisoformat(last_seen).timestamp())
            except ValueError:
                last_ts = since
        else:
            last_ts = since
        events.append({
            "ts": last_ts,
            "kind": "log_error",
            "severity": "err" if row.get("level") in ("CRITICAL", "CRIT") else "warn",
            "source": row.get("service", "?"),
            "message": f"[{row.get('level')}] ×{row.get('count',1)}: {(row.get('sample') or '')[:120]}",
        })

    events.sort(key=lambda e: e["ts"], reverse=True)
    return {
        "window_s": window,
        "since": since,
        "count": len(events[:limit]),
        "events": events[:limit],
    }
