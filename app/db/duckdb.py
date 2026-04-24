import json
import threading
import time
from datetime import datetime
from typing import Any, Iterable

import duckdb

from app.config import settings

_LOCK = threading.Lock()
_CONN: duckdb.DuckDBPyConnection | None = None


def _conn() -> duckdb.DuckDBPyConnection:
    global _CONN
    if _CONN is None:
        _CONN = duckdb.connect(str(settings.logs_db))
        _init(_CONN)
    return _CONN


def _init(c: duckdb.DuckDBPyConnection) -> None:
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            ts      TIMESTAMP NOT NULL,
            level   VARCHAR,
            service VARCHAR,
            host    VARCHAR,
            message VARCHAR,
            fields  JSON,
            source  VARCHAR
        )
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_logs_service ON logs(service)")
    c.execute(
        """
        CREATE OR REPLACE VIEW errors_by_minute AS
          SELECT date_trunc('minute', ts) AS bucket, COUNT(*) AS n
          FROM logs WHERE level IN ('ERR','ERROR','CRIT','FATAL')
          GROUP BY 1 ORDER BY 1
        """
    )
    c.execute(
        """
        CREATE OR REPLACE VIEW clusters AS
          SELECT
            regexp_replace(regexp_replace(message, '\\d+', 'N', 'g'), '0x[0-9a-f]+', 'H', 'g') AS signature,
            level, service,
            COUNT(*) AS n,
            MIN(ts) AS first_seen,
            MAX(ts) AS last_seen,
            ANY_VALUE(message) AS sample
          FROM logs
          GROUP BY 1,2,3
        """
    )


def insert_logs(rows: Iterable[dict[str, Any]]) -> None:
    batch = [
        (
            r["ts"] if isinstance(r["ts"], datetime) else datetime.fromtimestamp(r["ts"]),
            r.get("level"),
            r.get("service"),
            r.get("host"),
            r.get("message", ""),
            json.dumps(r.get("fields") or {}),
            r.get("source", "journald"),
        )
        for r in rows
    ]
    if not batch:
        return
    with _LOCK:
        _conn().executemany(
            "INSERT INTO logs(ts,level,service,host,message,fields,source) VALUES(?,?,?,?,?,?,?)",
            batch,
        )


def query_logs(
    level: str | None = None,
    service: str | None = None,
    regex: str | None = None,
    since_s: int | None = None,
    limit: int = 500,
) -> list[dict]:
    q = "SELECT ts, level, service, host, message, fields, source FROM logs WHERE 1=1"
    params: list[Any] = []
    if level:
        q += " AND upper(level) = upper(?)"
        params.append(level)
    if service:
        q += " AND service = ?"
        params.append(service)
    if regex:
        q += " AND regexp_matches(message, ?)"
        params.append(regex)
    if since_s:
        q += " AND ts >= to_timestamp(?)"
        params.append(since_s)
    q += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with _LOCK:
        rows = _conn().execute(q, params).fetchall()
    return [
        {
            "ts": r[0].isoformat(),
            "level": r[1],
            "service": r[2],
            "host": r[3],
            "message": r[4],
            "fields": json.loads(r[5]) if r[5] else {},
            "source": r[6],
        }
        for r in rows
    ]


def cluster_logs(since_s: int, limit: int = 40) -> list[dict]:
    with _LOCK:
        rows = _conn().execute(
            """
            SELECT signature, level, service, n, first_seen, last_seen, sample
            FROM clusters
            WHERE last_seen >= to_timestamp(?)
            ORDER BY n DESC LIMIT ?
            """,
            [since_s, limit],
        ).fetchall()
    return [
        {
            "signature": r[0],
            "level": r[1],
            "service": r[2],
            "count": r[3],
            "first": r[4].isoformat(),
            "last": r[5].isoformat(),
            "sample": r[6],
        }
        for r in rows
    ]


def service_log_summary(since_s: int, limit: int = 500) -> list[dict]:
    with _LOCK:
        rows = _conn().execute(
            """
            SELECT
                service,
                SUM(CASE WHEN upper(level) IN ('ERR', 'ERROR', 'CRIT', 'FATAL') THEN 1 ELSE 0 END) AS errors,
                SUM(CASE WHEN upper(level) = 'WARN' THEN 1 ELSE 0 END) AS warns,
                MAX(ts) AS last_seen,
                ANY_VALUE(message) AS sample
            FROM logs
            WHERE ts >= to_timestamp(?) AND service IS NOT NULL AND service <> ''
            GROUP BY service
            ORDER BY errors DESC, warns DESC, last_seen DESC
            LIMIT ?
            """,
            [since_s, limit],
        ).fetchall()
    return [
        {
            "service": r[0],
            "errors": int(r[1] or 0),
            "warns": int(r[2] or 0),
            "last_seen": r[3].isoformat() if r[3] else None,
            "sample": r[4] or "",
        }
        for r in rows
    ]


def histogram(bucket: str, window_s: int) -> list[dict]:
    unit = {"1m": "minute", "5m": "minute", "1h": "hour"}.get(bucket, "minute")
    with _LOCK:
        rows = _conn().execute(
            f"""
            SELECT date_trunc('{unit}', ts) AS bucket, level, COUNT(*) AS n
            FROM logs WHERE ts >= to_timestamp(?)
            GROUP BY 1,2 ORDER BY 1
            """,
            [window_s],
        ).fetchall()
    return [{"bucket": r[0].isoformat(), "level": r[1], "count": r[2]} for r in rows]


def prune(keep_s: int = 7 * 86400) -> None:
    cutoff = time.time() - keep_s
    with _LOCK:
        _conn().execute("DELETE FROM logs WHERE ts < to_timestamp(?)", [cutoff])


def close() -> None:
    global _CONN
    with _LOCK:
        if _CONN is not None:
            try:
                _CONN.close()
            except Exception:
                pass
            _CONN = None
