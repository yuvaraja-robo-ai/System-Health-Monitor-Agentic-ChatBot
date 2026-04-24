import time
from typing import Any

from fastapi import APIRouter, Query

from app.agent import diagnose as diag
from app.analytics.health import scorer
from app.api.apps import app_rows
from app.db import duckdb as ldb
from app.hub import hub
from app.utils.service import WINDOW_MAP

router = APIRouter(prefix="/api", tags=["briefing"])


def _headline(health: dict[str, Any], apps: list[dict[str, Any]]) -> str:
    score = health.get("score", "?")
    leak = next((app for app in apps if app.get("status") == "leak"), None)
    if leak:
        return f"System is mostly healthy, but {leak['label']} has been leaking memory."
    noisy = next((app for app in apps if app.get("errors") or app.get("crashes")), None)
    if noisy:
        return f"System health is {score}/100 and {noisy['label']} needs attention."
    return f"System health is {score}/100 with no active incidents."


def _featured(apps: list[dict[str, Any]]) -> dict[str, Any]:
    featured = next((app for app in apps if app.get("status") == "leak"), None)
    if not featured:
        featured = next((app for app in apps if app.get("crashes")), None)
    if not featured:
        featured = next((app for app in apps if app.get("errors")), None)
    if not featured:
        featured = apps[0] if apps else None
    if not featured:
        return {}
    cause = "No strong anomaly detected."
    impact = "Low."
    steps = []
    if featured.get("status") == "leak":
        cause = "RSS is trending upward over the rolling window with enough span and confidence to flag a leak."
        impact = f"Projected OOM in {featured.get('ttl_oom_s') or 'unknown'} seconds if growth continues."
        steps = [
            "Capture a process snapshot and relevant allocator/runtime state.",
            "Restart the affected service as a holdover if memory pressure is increasing.",
            "Review recent error clusters and app logs for allocation or queue growth messages.",
        ]
    elif featured.get("crashes"):
        cause = "Crash events were detected for this service in the selected window."
        impact = "Service stability is degraded and dependent workloads may be affected."
        steps = [
            "Inspect the latest crash signal and surrounding logs.",
            "Check service restart count and current active state.",
            "Compare the failure signature with previous incidents or KB matches.",
        ]
    elif featured.get("errors"):
        cause = "The service is producing repeated error-level logs."
        impact = "The system is still up, but the service is noisy and may be partially degraded."
        steps = [
            "Inspect recent error clusters and the latest matching app logs.",
            "Confirm dependent services are still healthy.",
            "Run the on-demand diagnose flow scoped to this service.",
        ]
    return {
        "app": featured,
        "probable_cause": cause,
        "impact": impact,
        "suggested_steps": steps,
    }


@router.get("/briefing")
def briefing(window: str = Query("6h")) -> dict[str, Any]:
    window_s = WINDOW_MAP.get(window, 21600)
    now = int(time.time())
    health = scorer.latest()
    apps = app_rows(window)
    clusters = ldb.cluster_logs(now - window_s, limit=6)
    ctx = diag.collect_context({"window": window})
    return {
        "ts": now,
        "health": health,
        "headline": _headline(health, apps),
        "featured_incident": _featured(apps),
        "apps": apps[:8],
        "clusters": clusters[:3],
        "context_digest": diag._digest_text(ctx),
        "sources": {
            "metrics_streams": 4,
            "log_clusters": len(clusters[:3]),
            "apps": len(apps),
        },
        "host": (hub.latest("system") or {}).get("data", {}).get("ts"),
    }
