import asyncio
import shutil
import subprocess
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app import runtime
from app.analytics.leak import detector
from app.config import settings
from app.db import duckdb as ldb
from app.db import sqlite as sdb
from app.hub import hub
from app.utils.service import WINDOW_MAP, match_score, normalize

router = APIRouter(prefix="/api/apps", tags=["apps"])

_APP_FLOW_KEYS = ("cpu", "rss", "threads", "procs", "io_read_bps", "io_write_bps", "net_conn", "errors", "warns", "crashes")
_NOISE = {
    "systemd",
    "kernel",
    "python",
    "python3",
    "bash",
    "sh",
    "timeout",
    "login",
    "dbus",
    "rsyslogd",
}


def _parse_window(window: str) -> int:
    return WINDOW_MAP.get(window, 21600)


def _list_units() -> list[dict[str, Any]]:
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
    out: list[dict[str, Any]] = []
    for raw in res.stdout.splitlines():
        parts = raw.strip().split(None, 4)
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
                "norm": normalize(name),
            }
        )
    return out


def _candidate_names(window_s: int, unit_rows: list[dict[str, Any]]) -> list[str]:
    names: list[str] = list(dict.fromkeys([*runtime.load_pinned_apps(), *settings.monitored_apps]))
    for leak in detector.current():
        if leak.get("name"):
            names.append(str(leak["name"]))
    for proc in (hub.latest("processes") or {}).get("data", {}).get("procs", [])[:200]:
        name = str(proc.get("name") or "")
        if name and normalize(name) not in _NOISE:
            names.append(name)
    for unit in unit_rows:
        if unit.get("name"):
            names.append(str(unit["name"]))
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        norm = normalize(name)
        if not norm or norm in seen or norm in _NOISE:
            continue
        seen.add(norm)
        out.append(name)
    return out


def _pick_best(name: str, rows: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    best = None
    best_score = 0
    for row in rows:
        score = match_score(name, str(row.get(field) or ""))
        if score > best_score:
            best = row
            best_score = score
    return best if best_score >= 20 else None


def _service_logs(window_s: int) -> list[dict[str, Any]]:
    since = int(time.time()) - window_s
    return ldb.query_logs(since_s=since, limit=2000)


_runtime_cache: dict[str, tuple[float, dict]] = {}
_RUNTIME_TTL_S = 15.0


def _unit_runtime(unit: str | None) -> dict[str, Any]:
    if not unit:
        return {}
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return {}
    now = time.time()
    cached = _runtime_cache.get(unit)
    if cached and now - cached[0] < _RUNTIME_TTL_S:
        return cached[1]
    try:
        res = subprocess.run(
            [
                systemctl,
                "show",
                unit,
                "--property=Id,Description,ExecMainPID,NRestarts,ActiveState,SubState",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    out: dict[str, Any] = {}
    for line in res.stdout.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k] = v
    if "ExecMainPID" in out:
        try:
            out["ExecMainPID"] = int(out["ExecMainPID"])
        except ValueError:
            out["ExecMainPID"] = 0
    if "NRestarts" in out:
        try:
            out["NRestarts"] = int(out["NRestarts"])
        except ValueError:
            out["NRestarts"] = 0
    _runtime_cache[unit] = (time.time(), out)
    return out


def _state(proc: dict[str, Any] | None, leak: dict[str, Any] | None, log_rows: list[dict[str, Any]], crashes: list[dict[str, Any]], unit: dict[str, Any] | None) -> str:
    if leak and leak.get("flagged"):
        return "leak"
    if crashes:
        return "err"
    errors = sum(1 for row in log_rows if str(row.get("level") or "").upper() in {"ERR", "ERROR", "CRIT", "FATAL"})
    if errors:
        return "warn"
    if unit and (unit.get("active_state") == "failed" or unit.get("sub_state") == "failed"):
        return "err"
    if proc and str(proc.get("status") or "").lower() in {"zombie", "dead"}:
        return "warn"
    return "ok"


def _summary(
    name: str,
    window_s: int,
    all_logs: list[dict[str, Any]],
    unit_rows: list[dict[str, Any]],
    crash_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    proc_rows = (hub.latest("processes") or {}).get("data", {}).get("procs", [])[:200]
    proc = _pick_best(name, proc_rows, "name")
    leak = _pick_best(name, detector.current(), "name")
    unit = _pick_best(name, unit_rows, "name")
    if crash_events is None:
        crash_events = sdb.recent_events("crash.", int(time.time()) - window_s, limit=200)
    crash_rows = _pick_all(name, crash_events, "payload")
    log_rows = [
        row for row in all_logs
        if match_score(name, str(row.get("service") or "")) >= 20
    ][:50]
    # Avoid running systemctl show once per candidate app. That made /api/apps slow
    # when many units were present. Process-backed apps still get pid/rss/cpu from
    # the live process snapshot; unit state comes from list-units.
    runtime: dict[str, Any] = {}

    errors = sum(1 for row in log_rows if str(row.get("level") or "").upper() in {"ERR", "ERROR", "CRIT", "FATAL"})
    warns = sum(1 for row in log_rows if str(row.get("level") or "").upper() == "WARN")

    row = {
        "name": normalize(name) or name,
        "label": proc.get("name") if proc else (unit.get("name") if unit else name),
        "pid": proc.get("pid") if proc else None,
        "cpu": proc.get("cpu") if proc else None,
        "rss": proc.get("rss") if proc else None,
        "threads": proc.get("threads") if proc else None,
        "time_plus": proc.get("time_plus") if proc else None,
        "status": _state(proc, leak, log_rows, crash_rows, unit),
        "slope_mb_min": leak.get("slope_mb_min") if leak else None,
        "ttl_oom_s": leak.get("ttl_oom_s") if leak else None,
        "delta_6h_mb": leak.get("delta_6h_mb") if leak else None,
        "rss_mb": leak.get("rss_mb") if leak else (round(proc["rss"] / (1024 * 1024), 2) if proc and proc.get("rss") else None),
        "errors": errors,
        "warns": warns,
        "crashes": len(crash_rows),
        "restarts": 0,
        "service": unit["name"] if unit else None,
        "description": unit.get("description") if unit else "",
        "active_state": unit.get("active_state") if unit else None,
        "sub_state": unit.get("sub_state") if unit else None,
        "last_log": log_rows[0] if log_rows else None,
        "recent_logs": log_rows[:8],
        "recent_crashes": crash_rows[:8],
    }
    return row


def _crash_match_value(row: dict[str, Any]) -> str:
    payload = row.get("payload") or {}
    return str(payload.get("unit") or payload.get("message") or "")


def _pick_all(name: str, rows: list[dict[str, Any]], field: str, min_score: int = 20) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if field == "payload":
            value = _crash_match_value(row)
        else:
            value = str(row.get(field) or "")
        if match_score(name, value) >= min_score:
            out.append(row)
    return out


_rows_cache: dict[str, tuple[float, list]] = {}
_rows_lock = threading.Lock()
_ROWS_TTL_S = 20.0


def _build_app_rows(
    window: str,
    unit_rows: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    crash_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    window_s = _parse_window(window)
    names = _candidate_names(window_s, unit_rows)
    for row in logs[:200]:
        service = str(row.get("service") or "")
        if service:
            names.append(service)
    for event in crash_events[:100]:
        payload = event.get("payload") or {}
        unit = payload.get("unit")
        if unit:
            names.append(str(unit))
    seen_names: set[str] = set()
    names = [
        name for name in names
        if (normalize(name) or name) not in seen_names
        and not seen_names.add(normalize(name) or name)
    ]
    rows = [_summary(name, window_s, logs, unit_rows, crash_events) for name in names]
    rows.sort(
        key=lambda row: (
            0 if row["status"] == "leak" else 1 if row["status"] == "err" else 2 if row["status"] == "warn" else 3,
            -(row.get("rss") or 0),
            -(row.get("errors") or 0),
        )
    )
    return rows


def app_rows(window: str = "6h") -> list[dict[str, Any]]:
    now = time.time()
    with _rows_lock:
        cached = _rows_cache.get(window)
        if cached and now - cached[0] < _ROWS_TTL_S:
            return cached[1]

    window_s = _parse_window(window)
    unit_rows = _list_units()
    logs = _service_logs(window_s)
    crash_events = sdb.recent_events("crash.", int(time.time()) - window_s, limit=200)
    rows = _build_app_rows(window, unit_rows, logs, crash_events)
    with _rows_lock:
        _rows_cache[window] = (time.time(), rows)
    return rows


async def _to_thread_timeout(func, *args, default, timeout_s: float = 3.0):
    try:
        return await asyncio.wait_for(asyncio.to_thread(func, *args), timeout=timeout_s)
    except Exception:
        return default


async def app_rows_async(window: str = "6h") -> list[dict[str, Any]]:
    now = time.time()
    with _rows_lock:
        cached = _rows_cache.get(window)
        if cached and now - cached[0] < _ROWS_TTL_S:
            return cached[1]

    rows = await asyncio.to_thread(_build_app_rows, window, [], [], [])
    with _rows_lock:
        _rows_cache[window] = (time.time(), rows)
    return rows


def _app_flow(app: str, window: str = "6h", step: str = "1m") -> dict[str, Any]:
    from app.api.system import _parse_step

    window_s = _parse_window(window)
    step_s = max(1, _parse_step(step))
    now = int(time.time())
    out: dict[str, Any] = {
        "window": window,
        "step": step,
        "step_s": step_s,
        "keys": {},
    }
    for key in _APP_FLOW_KEYS:
        rows = sdb.app_history(app, key, now - window_s, now, step_s)
        out["keys"][key] = {"t": [int(ts) for ts, _ in rows], "v": [float(value) for _, value in rows]}
    return out


async def _app_flow_async(app: str, window: str = "6h", step: str = "1m") -> dict[str, Any]:
    from app.api.system import _parse_step

    window_s = _parse_window(window)
    step_s = max(1, _parse_step(step))
    now = int(time.time())
    history_rows = await asyncio.gather(
        *[
            asyncio.to_thread(sdb.app_history, app, key, now - window_s, now, step_s)
            for key in _APP_FLOW_KEYS
        ]
    )
    return {
        "window": window,
        "step": step,
        "step_s": step_s,
        "keys": {
            key: {"t": [int(ts) for ts, _ in rows], "v": [float(value) for _, value in rows]}
            for key, rows in zip(_APP_FLOW_KEYS, history_rows)
        },
    }


def _njmon_app_flow(row: dict[str, Any], window: str = "6h", step: str = "1m") -> dict[str, Any]:
    flow = _app_flow(str(row["name"]), window=window, step=step)
    return _njmon_from_flow(row, flow, window)


def _njmon_from_flow(row: dict[str, Any], flow: dict[str, Any], window: str) -> dict[str, Any]:
    keys = flow["keys"]
    return {
        "identity": {
            "app": row["name"],
            "label": row["label"],
            "service": row.get("service"),
        },
        "timestamp": {
            "window": window,
            "snapshot_seconds": flow["step_s"],
            "poll_seconds": settings.app_monitor_tick_s,
        },
        "app_cpu": {
            "pct": row.get("cpu"),
            "history": keys["cpu"],
        },
        "app_memory": {
            "rss_bytes": row.get("rss"),
            "rss_mb": row.get("rss_mb"),
            "history": keys["rss"],
        },
        "app_process": {
            "pid": row.get("pid"),
            "threads": row.get("threads"),
            "process_count": int(keys["procs"]["v"][-1]) if keys["procs"]["v"] else 0,
            "thread_history": keys["threads"],
            "process_history": keys["procs"],
        },
        "app_io": {
            "read_bps_history": keys["io_read_bps"],
            "write_bps_history": keys["io_write_bps"],
        },
        "app_network": {
            "connection_history": keys["net_conn"],
        },
        "app_events": {
            "errors": row.get("errors", 0),
            "warns": row.get("warns", 0),
            "crashes": row.get("crashes", 0),
            "restarts": row.get("restarts", 0),
            "error_history": keys["errors"],
            "warn_history": keys["warns"],
            "crash_history": keys["crashes"],
        },
    }


async def _njmon_app_flow_async(row: dict[str, Any], window: str = "6h", step: str = "1m") -> dict[str, Any]:
    flow = await _app_flow_async(str(row["name"]), window=window, step=step)
    return _njmon_from_flow(row, flow, window)


@router.get("")
async def list_apps(window: str = Query("6h")) -> list[dict[str, Any]]:
    return await app_rows_async(window)


@router.get("/{name}")
async def app_detail(name: str, window: str = Query("6h"), step: str = Query("1m")) -> dict[str, Any]:
    rows = await app_rows_async(window)
    row = _pick_best(name, rows, "name") or _pick_best(name, rows, "label")
    if not row:
        raise HTTPException(404, f"unknown app: {name}")
    pid = row.get("pid")
    history = {"t": [], "v": []}
    if pid:
        since = int(time.time()) - _parse_window(window)
        rss_rows = await asyncio.to_thread(sdb.proc_rss_history, int(pid), since)
        history = {"t": [r[0] for r in rss_rows], "v": [r[1] for r in rss_rows]}
    flow = await _app_flow_async(str(row["name"]), window=window, step=step)
    return {
        "app": row,
        "rss_history": history,
        "flow": flow,
        "njmon": _njmon_from_flow(row, flow, window),
        "polling_s": settings.app_monitor_tick_s,
    }


@router.get("/{name}/history")
async def app_history(name: str, window: str = Query("6h"), step: str = Query("1m")) -> dict[str, Any]:
    rows = await app_rows_async(window)
    row = _pick_best(name, rows, "name") or _pick_best(name, rows, "label")
    if not row:
        raise HTTPException(404, f"unknown app: {name}")
    flow = await _app_flow_async(str(row["name"]), window=window, step=step)
    njmon = await _njmon_app_flow_async(row, window=window, step=step)
    return {
        "app": row["name"],
        "label": row["label"],
        "polling_s": settings.app_monitor_tick_s,
        "flow": flow,
        "njmon": njmon,
    }


@router.get("/{name}/njmon")
async def app_njmon(
    name: str,
    window: str = Query("6h"),
    step: str = Query("1m"),
    format: str = Query("nested"),
) -> dict[str, Any]:
    rows = await app_rows_async(window)
    row = _pick_best(name, rows, "name") or _pick_best(name, rows, "label")
    if not row:
        raise HTTPException(404, f"unknown app: {name}")
    nested = await _njmon_app_flow_async(row, window=window, step=step)
    if format == "flat":
        return _flatten_njmon(nested)
    return nested


def _flatten_njmon(obj: dict, prefix: str = "") -> dict:
    out: dict[str, Any] = {}
    for k, v in obj.items():
        key = f"{prefix}_{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten_njmon(v, key))
        elif isinstance(v, list):
            if v and isinstance(v[-1], (int, float)):
                out[f"{key}_latest"] = v[-1]
            else:
                out[key] = v
        else:
            out[key] = v
    return out
