import asyncio
import time
from typing import Any

import psutil

from app.collectors.base import Collector
from app.config import settings
from app.db import duckdb as ldb
from app.db import sqlite as sdb
from app.hub import hub
from app.utils.service import match_score, normalize

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
_ERR_LEVELS = {"ERR", "ERROR", "CRIT", "FATAL"}


def _crash_text(row: dict[str, Any]) -> str:
    payload = row.get("payload") or {}
    return str(payload.get("unit") or payload.get("message") or "")


class AppMonitorCollector(Collector):
    name = "app-monitor"
    interval_s = settings.app_monitor_tick_s

    def __init__(self) -> None:
        super().__init__()
        self._last_ts = int(time.time()) - max(1, int(settings.app_monitor_tick_s))
        self._prev_io: dict[int, tuple[int, int]] = {}

    async def tick(self) -> None:
        ts = int(time.time())
        rows = await asyncio.to_thread(self._sample, ts)
        await asyncio.to_thread(sdb.write_app_metrics, rows)
        self._last_ts = ts

    def _sample(self, ts: int) -> list[tuple[int, str, str, float]]:
        start = max(0, self._last_ts - 1)
        procs = (hub.latest("processes") or {}).get("data", {}).get("procs", [])[:200]
        logs = ldb.query_logs(since_s=start, limit=max(500, settings.log_batch_size * 4))
        crashes = sdb.recent_events("crash.", start, limit=500)
        proc_stats = self._process_stats(ts)

        names: list[str] = list(settings.monitored_apps)
        names.extend(sdb.app_names(start))
        for proc in procs:
            name = str(proc.get("name") or "")
            norm = normalize(name)
            if norm and norm not in _NOISE:
                names.append(name)
        for row in logs[:200]:
            service = str(row.get("service") or "")
            if normalize(service):
                names.append(service)
        for row in crashes[:200]:
            names.append(_crash_text(row))

        apps: list[str] = []
        seen: set[str] = set()
        for name in names:
            norm = normalize(name)
            if not norm or norm in _NOISE or norm in seen:
                continue
            seen.add(norm)
            apps.append(norm)

        out: list[tuple[int, str, str, float]] = []
        for app in apps:
            matched = [p for p in procs if match_score(app, str(p.get("name") or "")) >= 20]
            matched_stats = [p for p in proc_stats if match_score(app, str(p.get("name") or "")) >= 20]
            cpu = sum(float(p.get("cpu") or 0.0) for p in matched)
            rss = sum(float(p.get("rss") or 0.0) for p in matched)
            threads = sum(float(p.get("threads") or 0.0) for p in matched)
            proc_count = float(len(matched))
            io_read_bps = sum(float(p.get("io_read_bps") or 0.0) for p in matched_stats)
            io_write_bps = sum(float(p.get("io_write_bps") or 0.0) for p in matched_stats)
            net_conn = sum(float(p.get("net_conn") or 0.0) for p in matched_stats)

            errors = 0.0
            warns = 0.0
            for row in logs:
                if match_score(app, str(row.get("service") or "")) < 20:
                    continue
                level = str(row.get("level") or "").upper()
                if level in _ERR_LEVELS:
                    errors += 1.0
                elif level == "WARN":
                    warns += 1.0

            crash_count = sum(1.0 for row in crashes if match_score(app, _crash_text(row)) >= 20)

            out.extend(
                [
                    (ts, app, "cpu", cpu),
                    (ts, app, "rss", rss),
                    (ts, app, "threads", threads),
                    (ts, app, "procs", proc_count),
                    (ts, app, "io_read_bps", io_read_bps),
                    (ts, app, "io_write_bps", io_write_bps),
                    (ts, app, "net_conn", net_conn),
                    (ts, app, "errors", errors),
                    (ts, app, "warns", warns),
                    (ts, app, "crashes", crash_count),
                ]
            )
        return out

    def _process_stats(self, ts: int) -> list[dict[str, Any]]:
        dt = max(1.0, float(ts - self._last_ts))
        next_prev: dict[int, tuple[int, int]] = {}
        out: list[dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pid = int(proc.pid)
                name = str(proc.info.get("name") or pid)
                io = proc.io_counters() if hasattr(proc, "io_counters") else None
                read_bytes = int(getattr(io, "read_bytes", 0) or 0)
                write_bytes = int(getattr(io, "write_bytes", 0) or 0)
                prev_read, prev_write = self._prev_io.get(pid, (read_bytes, write_bytes))
                read_bps = max(0.0, (read_bytes - prev_read) / dt)
                write_bps = max(0.0, (write_bytes - prev_write) / dt)
                try:
                    net_conn = float(len(proc.net_connections(kind="inet")))
                except Exception:
                    net_conn = 0.0
                next_prev[pid] = (read_bytes, write_bytes)
                out.append(
                    {
                        "pid": pid,
                        "name": name,
                        "io_read_bps": read_bps,
                        "io_write_bps": write_bps,
                        "net_conn": net_conn,
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        self._prev_io = next_prev
        return out
