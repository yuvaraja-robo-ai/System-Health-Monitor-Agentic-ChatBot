import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.collectors.base import Collector
from app.config import settings
from app.db import duckdb as ldb
from app.host import detect
from app.hub import hub

log = logging.getLogger(__name__)

_PRIO = {0: "EMERG", 1: "ALERT", 2: "CRIT", 3: "ERR", 4: "WARN", 5: "NOTICE", 6: "INFO", 7: "DEBUG"}


class JournaldCollector(Collector):
    name = "journald"
    interval_s = 0.5

    def __init__(self) -> None:
        super().__init__()
        self._reader = None
        self._buffer: list[dict[str, Any]] = []
        self._last_flush = time.time()

    async def setup(self) -> None:
        if not detect().has_journald:
            return
        from systemd import journal  # type: ignore

        r = journal.Reader()
        r.seek_realtime(datetime.now(timezone.utc))
        r.get_previous()
        self._reader = r

    async def teardown(self) -> None:
        r = self._reader
        self._reader = None
        if r is not None:
            try:
                r.close()
            except Exception:
                pass

    async def tick(self) -> None:
        if self._reader is None:
            return
        rows = await asyncio.to_thread(self._read_batch)
        if rows:
            for r in rows:
                hub.publish("logs", r)
            self._buffer.extend(rows)
        if self._buffer and (len(self._buffer) >= settings.log_batch_size or time.time() - self._last_flush > 2.0):
            batch, self._buffer = self._buffer, []
            self._last_flush = time.time()
            await asyncio.to_thread(ldb.insert_logs, batch)

    def _read_batch(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        r = self._reader
        r.wait(0.2)
        for _ in range(500):
            e = r.get_next()
            if not e:
                break
            msg = e.get("MESSAGE")
            if isinstance(msg, bytes):
                try:
                    msg = msg.decode("utf-8", errors="replace")
                except Exception:
                    msg = str(msg)
            fields: dict[str, Any] = {}
            parsed_fields = None
            if isinstance(msg, str) and msg.startswith("{") and msg.endswith("}"):
                try:
                    parsed_fields = json.loads(msg)
                except json.JSONDecodeError:
                    parsed_fields = None
            ts = e.get("__REALTIME_TIMESTAMP")
            prio = e.get("PRIORITY")
            try:
                prio_i = int(prio) if prio is not None else 6
            except (TypeError, ValueError):
                prio_i = 6
            out.append(
                {
                    "ts": ts if isinstance(ts, datetime) else datetime.fromtimestamp(time.time()),
                    "level": _PRIO.get(prio_i, "INFO"),
                    "service": e.get("_SYSTEMD_UNIT") or e.get("SYSLOG_IDENTIFIER") or e.get("_COMM"),
                    "host": e.get("_HOSTNAME"),
                    "message": msg if isinstance(msg, str) else str(msg),
                    "fields": parsed_fields or fields,
                    "source": "journald",
                }
            )
        return out
