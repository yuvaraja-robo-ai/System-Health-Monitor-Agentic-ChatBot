import time

from fastapi import APIRouter, HTTPException, Query

from app.db import sqlite as sdb
from app.hub import hub
from app.utils.service import WINDOW_MAP

router = APIRouter(prefix="/api/system", tags=["system"])


def _parse_window(s: str) -> int:
    if s in WINDOW_MAP:
        return WINDOW_MAP[s]
    try:
        return int(s)
    except ValueError:
        raise HTTPException(400, f"bad window: {s}")


def _parse_step(s: str) -> int:
    if s.endswith("s"):
        return int(s[:-1])
    if s.endswith("m"):
        return int(s[:-1]) * 60
    if s.endswith("h"):
        return int(s[:-1]) * 3600
    return int(s)


@router.get("/current")
def current() -> dict:
    sys_env = hub.latest("system")
    jetson_env = hub.latest("jetson")
    payload = (sys_env or {}).get("data") or {}
    if jetson_env:
        payload = dict(payload)
        payload["jetson"] = jetson_env["data"]
    return payload


@router.get("/history")
def history(
    field: str = Query(..., description="e.g. cpu.total, mem.used, gpu.load"),
    window: str = Query("1h"),
    step: str = Query("10s"),
) -> dict:
    window_s = _parse_window(window)
    step_s = max(1, _parse_step(step))
    now = int(time.time())
    rows = sdb.history(field, now - window_s, now, step_s)
    return {"field": field, "t": [r[0] for r in rows], "v": [r[1] for r in rows]}
