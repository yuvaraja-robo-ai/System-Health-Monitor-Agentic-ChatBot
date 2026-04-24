import time

from fastapi import APIRouter, Query

from app.analytics import cluster
from app.db import duckdb as ldb
from app.utils.service import WINDOW_MAP

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _since(window: str | None) -> int | None:
    if not window:
        return None
    if window in WINDOW_MAP:
        return int(time.time()) - WINDOW_MAP[window]
    try:
        return int(time.time()) - int(window)
    except ValueError:
        return None


@router.get("")
def query_logs(
    level: str | None = None,
    service: str | None = None,
    regex: str | None = None,
    since: str | None = None,
    limit: int = Query(500, ge=1, le=5000),
) -> list[dict]:
    return ldb.query_logs(level=level, service=service, regex=regex, since_s=_since(since), limit=limit)


@router.get("/cluster")
def clusters(since: str = "5m", limit: int = Query(40, ge=1, le=200)) -> list[dict]:
    s = _since(since) or int(time.time()) - 300
    return cluster.summarize(s, limit=limit)


@router.get("/histogram")
def histogram(bucket: str = "1m", window: str = "1h") -> list[dict]:
    w = _since(window) or int(time.time()) - 3600
    return cluster.histogram(w, bucket)
