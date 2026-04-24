import time

from fastapi import APIRouter, HTTPException, Query

from app.analytics.leak import detector
from app.db import sqlite as sdb
from app.hub import hub

router = APIRouter(prefix="/api/processes", tags=["processes"])


@router.get("")
def list_procs(
    limit: int = Query(200, ge=1, le=2000),
    sort: str = Query("rss", pattern="^(rss|cpu|pid|name|threads)$"),
) -> list[dict]:
    env = hub.latest("processes")
    procs = (env or {}).get("data", {}).get("procs", [])
    key = sort
    reverse = sort in ("rss", "cpu", "threads")
    procs = sorted(procs, key=lambda p: p.get(key, 0), reverse=reverse)[:limit]
    leaks = {l["pid"]: l for l in detector.current()}
    out = []
    for p in procs:
        state = "ok"
        if p["pid"] in leaks and leaks[p["pid"]]["flagged"]:
            state = "leak"
        elif (p.get("status") or "").lower() in ("zombie", "dead"):
            state = "warn"
        out.append(
            {
                "pid": p["pid"],
                "name": p["name"],
                "cpu": p["cpu"],
                "rss": p["rss"],
                "threads": p["threads"],
                "time_plus": p["time_plus"],
                "state": state,
            }
        )
    return out


@router.get("/{pid}/rss")
def rss_history(pid: int, window: str = Query("6h")) -> dict:
    from app.api.system import _parse_window

    since = int(time.time()) - _parse_window(window)
    rows = sdb.proc_rss_history(pid, since)
    if not rows:
        return {"pid": pid, "t": [], "v": []}
    return {"pid": pid, "t": [r[0] for r in rows], "v": [r[1] for r in rows]}
