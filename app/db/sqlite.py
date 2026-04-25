import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable

from app.config import settings

_LOCAL = threading.local()
_SCHEMA = Path(__file__).parent / "schema.sql"
_WRITE_LOCK = threading.RLock()


def _configure(c: sqlite3.Connection) -> None:
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=30000")


def _conn() -> sqlite3.Connection:
    c = getattr(_LOCAL, "conn", None)
    if c is None:
        c = sqlite3.connect(
            settings.metrics_db,
            isolation_level=None,
            check_same_thread=False,
            timeout=30.0,
        )
        _configure(c)
        _LOCAL.conn = c
    return c


def init() -> None:
    with sqlite3.connect(settings.metrics_db) as c:
        _configure(c)
        c.executescript(_SCHEMA.read_text())


def write_metrics(rows: Iterable[tuple[int, str, float]]) -> None:
    batch = list(rows)
    if not batch:
        return
    c = _conn()
    with _WRITE_LOCK:
        c.executemany("INSERT OR REPLACE INTO metric(ts,key,value) VALUES(?,?,?)", batch)


def write_procs(rows: Iterable[tuple[int, int, str, int, float, int]]) -> None:
    batch = list(rows)
    if not batch:
        return
    c = _conn()
    with _WRITE_LOCK:
        c.executemany(
            "INSERT OR REPLACE INTO proc_rss(ts,pid,name,rss,cpu,threads) VALUES(?,?,?,?,?,?)",
            batch,
        )


def write_app_metrics(rows: Iterable[tuple[int, str, str, float]]) -> None:
    batch = list(rows)
    if not batch:
        return
    c = _conn()
    with _WRITE_LOCK:
        c.executemany(
            "INSERT OR REPLACE INTO app_metric(ts,app,key,value) VALUES(?,?,?,?)",
            batch,
        )


def log_event(kind: str, payload: dict) -> None:
    c = _conn()
    with _WRITE_LOCK:
        c.execute(
            "INSERT INTO event(ts,kind,payload) VALUES(?,?,?)",
            (int(time.time()), kind, json.dumps(payload)),
        )


def history(key: str, since_s: int, until_s: int, step_s: int) -> list[tuple[int, float]]:
    c = _conn()
    if step_s <= 1:
        rows = c.execute(
            "SELECT ts, value FROM metric WHERE key=? AND ts BETWEEN ? AND ? ORDER BY ts",
            (key, since_s, until_s),
        ).fetchall()
        return rows
    rows = c.execute(
        """
        SELECT (ts/?)*? AS bucket, AVG(value) FROM metric
        WHERE key=? AND ts BETWEEN ? AND ?
        GROUP BY bucket ORDER BY bucket
        """,
        (step_s, step_s, key, since_s, until_s),
    ).fetchall()
    return [(int(b), float(v)) for b, v in rows]


def proc_rss_history(pid: int, since_s: int) -> list[tuple[int, int]]:
    c = _conn()
    return c.execute(
        "SELECT ts, rss FROM proc_rss WHERE pid=? AND ts>=? ORDER BY ts",
        (pid, since_s),
    ).fetchall()


def proc_rss_range(pid: int, start_s: int, end_s: int) -> tuple[int | None, int | None]:
    c = _conn()
    row = c.execute(
        """
        SELECT
            (SELECT rss FROM proc_rss WHERE pid=? AND ts>=? ORDER BY ts LIMIT 1),
            (SELECT rss FROM proc_rss WHERE pid=? AND ts<=? ORDER BY ts DESC LIMIT 1)
        """,
        (pid, start_s, pid, end_s),
    ).fetchone()
    return row or (None, None)


def app_history(app: str, key: str, since_s: int, until_s: int, step_s: int) -> list[tuple[int, float]]:
    c = _conn()
    table = "app_metric"
    bucket_s = step_s
    if step_s >= 60:
        table = "app_metric_1m"
        bucket_s = 60
    elif step_s >= 10:
        table = "app_metric_10s"
        bucket_s = 10

    if table != "app_metric" and step_s == bucket_s:
        rows = c.execute(
            f"""
            SELECT ts, value
            FROM {table}
            WHERE app=? AND key=? AND ts BETWEEN ? AND ?
            ORDER BY ts
            """,
            (app, key, since_s, until_s),
        ).fetchall()
        return [(int(ts), float(value)) for ts, value in rows]

    rows = c.execute(
        f"""
        SELECT (ts/?)*? AS bucket, AVG(value)
        FROM {table}
        WHERE app=? AND key=? AND ts BETWEEN ? AND ?
        GROUP BY bucket
        ORDER BY bucket
        """,
        (step_s, step_s, app, key, since_s, until_s),
    ).fetchall()
    return [(int(ts), float(value)) for ts, value in rows]


def app_names(since_s: int | None = None) -> list[str]:
    c = _conn()
    if since_s is None:
        rows = c.execute("SELECT DISTINCT app FROM app_metric ORDER BY app").fetchall()
    else:
        rows = c.execute(
            "SELECT DISTINCT app FROM app_metric WHERE ts >= ? ORDER BY app",
            (since_s,),
        ).fetchall()
    return [str(row[0]) for row in rows if row and row[0]]


def recent_events(kind_prefix: str | None, since_s: int, limit: int = 200) -> list[dict]:
    c = _conn()
    if kind_prefix:
        rows = c.execute(
            "SELECT ts,kind,payload FROM event WHERE kind LIKE ? AND ts>=? ORDER BY ts DESC LIMIT ?",
            (kind_prefix + "%", since_s, limit),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT ts,kind,payload FROM event WHERE ts>=? ORDER BY ts DESC LIMIT ?",
            (since_s, limit),
        ).fetchall()
    return [{"ts": ts, "kind": k, "payload": json.loads(p)} for ts, k, p in rows]


def prune() -> None:
    c = _conn()
    now = int(time.time())
    with _WRITE_LOCK:
        c.execute("DELETE FROM metric WHERE ts < ?", (now - settings.history_raw_retention_s,))
        c.execute("DELETE FROM metric_10s WHERE ts < ?", (now - settings.history_10s_retention_s,))
        c.execute("DELETE FROM metric_1m WHERE ts < ?", (now - settings.history_1m_retention_s,))
        c.execute("DELETE FROM proc_rss WHERE ts < ?", (now - 86400,))
        c.execute("DELETE FROM app_metric WHERE ts < ?", (now - settings.history_raw_retention_s,))
        c.execute("DELETE FROM app_metric_10s WHERE ts < ?", (now - settings.history_10s_retention_s,))
        c.execute("DELETE FROM app_metric_1m WHERE ts < ?", (now - settings.history_1m_retention_s,))
        c.execute("DELETE FROM event WHERE ts < ?", (now - 7 * 86400,))


def downsample() -> None:
    c = _conn()
    now = int(time.time())
    cut = now - 120
    with _WRITE_LOCK:
        c.execute(
            """
            INSERT OR REPLACE INTO metric_10s(ts,key,value)
            SELECT (ts/10)*10, key, AVG(value) FROM metric
            WHERE ts < ? AND ts >= ?
            GROUP BY (ts/10), key
            """,
            (cut, cut - 600),
        )
        c.execute(
            """
            INSERT OR REPLACE INTO metric_1m(ts,key,value)
            SELECT (ts/60)*60, key, AVG(value) FROM metric_10s
            WHERE ts < ? AND ts >= ?
            GROUP BY (ts/60), key
            """,
            (now - 1200, now - 3600),
        )
        c.execute(
            """
            INSERT OR REPLACE INTO app_metric_10s(ts,app,key,value)
            SELECT (ts/10)*10, app, key, AVG(value) FROM app_metric
            WHERE ts < ? AND ts >= ?
            GROUP BY (ts/10), app, key
            """,
            (cut, cut - 600),
        )
        c.execute(
            """
            INSERT OR REPLACE INTO app_metric_1m(ts,app,key,value)
            SELECT (ts/60)*60, app, key, AVG(value) FROM app_metric_10s
            WHERE ts < ? AND ts >= ?
            GROUP BY (ts/60), app, key
            """,
            (now - 1200, now - 3600),
        )
