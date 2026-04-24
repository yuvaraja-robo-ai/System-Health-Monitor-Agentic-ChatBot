import time
from pathlib import Path
import shutil
import subprocess

from fastapi import APIRouter, Query

from app.analytics import correlate as correlator
from app.analytics.anomaly import detector as anomaly_detector
from app.analytics.health import scorer
from app.analytics.leak import detector
from app.db import duckdb as ldb
from app.db import sqlite as sdb
from app.hub import hub
from app.utils.service import WINDOW_MAP

router = APIRouter(prefix="/api", tags=["derived"])


@router.get("/health")
def health() -> dict:
    return scorer.latest()


@router.get("/leaks")
def leaks() -> list[dict]:
    return detector.current()


@router.get("/anomalies")
def anomalies(history_limit: int = Query(50, ge=0, le=500)) -> dict:
    return {
        "current": anomaly_detector.current(),
        "count": len(anomaly_detector.active),
        "history": anomaly_detector.history(limit=history_limit) if history_limit else [],
    }


@router.get("/correlate")
def correlate_endpoint(
    ts: int | None = Query(None, description="incident timestamp (epoch seconds); defaults to now"),
    window: int = Query(300, ge=30, le=7200, description="incident window size in seconds"),
    top: int = Query(15, ge=1, le=50),
) -> dict:
    return correlator.correlate(incident_ts=ts, window_s=window, top=top)


@router.get("/crashes")
def crashes(window: str = Query("24h")) -> dict:
    env = hub.latest("crashes")
    live = (env or {}).get("data") or {"counts": {}, "recent": []}
    since = int(time.time()) - WINDOW_MAP.get(window, 86400)
    events = sdb.recent_events("crash.", since, limit=200)
    counts: dict[str, int] = {}
    for e in events:
        sig = e["kind"].replace("crash.", "")
        counts[sig] = counts.get(sig, 0) + 1
    merged = dict(live.get("counts", {}))
    for k, v in counts.items():
        merged[k] = max(merged.get(k, 0), v)
    return {"counts": merged, "recent": live.get("recent", [])[:50], "events_24h": events[:50]}


@router.get("/units")
def units(window: str = Query("24h"), limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    since = int(time.time()) - WINDOW_MAP.get(window, 86400)
    units = _list_units()
    if not units:
        return []

    log_summary = _service_lookup(ldb.service_log_summary(since, limit=2000))
    crashes = _crash_lookup(sdb.recent_events("crash.", since, limit=500))

    enriched = []
    for unit in units:
        key = _unit_key(unit["name"])
        logs = log_summary.get(key, {"errors": 0, "warns": 0, "last_seen": None, "sample": ""})
        crash = crashes.get(key, {"count": 0, "signal": None})

        severity = _severity(unit["active_state"], unit["sub_state"], logs["errors"], logs["warns"], crash["count"])
        detail = _detail(unit, logs, crash)
        enriched.append(
            {
                **unit,
                "errors": logs["errors"],
                "warns": logs["warns"],
                "crashes": crash["count"],
                "last_seen": logs["last_seen"],
                "sample": logs["sample"],
                "status": severity,
                "detail": detail,
                "sort_key": _sort_key(severity, logs["errors"], logs["warns"], crash["count"]),
            }
        )

    enriched.sort(key=lambda row: row["sort_key"], reverse=True)
    return [{k: v for k, v in row.items() if k != "sort_key"} for row in enriched[:limit]]


def _list_units() -> list[dict]:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return []
    try:
        res = subprocess.run(
            [systemctl, "list-units", "--type=service", "--all", "--plain", "--no-legend", "--no-pager"],
            capture_output=True,
            text=True,
            check=True,
            timeout=4,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    out: list[dict] = []
    for raw in res.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        name, load_state, active_state, sub_state, description = parts
        out.append(
            {
                "name": name,
                "load_state": load_state,
                "active_state": active_state,
                "sub_state": sub_state,
                "description": description,
            }
        )
    return out


def _unit_key(name: str | None) -> str | None:
    if not name:
        return None
    if name.endswith(".service"):
        return name[:-8]
    return Path(name).stem


def _service_lookup(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        key = _unit_key(row.get("service"))
        if not key:
            continue
        prev = out.get(key)
        if prev is None:
            out[key] = dict(row)
            continue
        prev["errors"] += row["errors"]
        prev["warns"] += row["warns"]
        if row.get("last_seen") and (not prev.get("last_seen") or row["last_seen"] > prev["last_seen"]):
            prev["last_seen"] = row["last_seen"]
            prev["sample"] = row.get("sample", "")
    return out


def _crash_lookup(events: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for event in events:
        payload = event.get("payload") or {}
        key = _unit_key(payload.get("unit"))
        if not key:
            continue
        cur = out.setdefault(key, {"count": 0, "signal": None})
        cur["count"] += 1
        cur["signal"] = payload.get("signal") or cur["signal"]
    return out


def _severity(active_state: str, sub_state: str, errors: int, warns: int, crashes: int) -> str:
    if active_state == "failed" or sub_state in {"failed", "auto-restart"} or crashes:
        return "err"
    if active_state in {"activating", "deactivating", "reloading"} or errors or warns:
        return "warn"
    return "ok"


def _detail(unit: dict, logs: dict, crash: dict) -> str:
    if crash["count"]:
        signal = crash.get("signal")
        return f"{signal or 'crash'} x{crash['count']}"
    if logs["errors"]:
        return f"err x{logs['errors']}"
    if logs["warns"]:
        return f"warn x{logs['warns']}"
    return unit["sub_state"]


def _sort_key(severity: str, errors: int, warns: int, crashes: int) -> tuple[int, int, int, int]:
    priority = {"err": 3, "warn": 2, "ok": 1}.get(severity, 0)
    return (priority, crashes, errors, warns)
