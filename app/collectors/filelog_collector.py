import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.collectors.base import Collector
from app.config import settings
from app.db import duckdb as ldb
from app.hub import hub

log = logging.getLogger(__name__)


class FileLogCollector(Collector):
    name = "filelog"
    interval_s = 1.0

    def __init__(self) -> None:
        super().__init__()
        self._positions: dict[str, tuple[int, int]] = {}
        self._buffer: list[dict[str, Any]] = []

    def _discover(self) -> list[Path]:
        files: list[Path] = []
        for d in settings.log_app_dirs:
            p = Path(d)
            if p.is_file():
                files.append(p)
            elif p.is_dir():
                files.extend(p.rglob("*.log"))
                files.extend(p.rglob("*.ndjson"))
        return files

    async def tick(self) -> None:
        if not settings.log_app_dirs:
            return
        batches = await asyncio.to_thread(self._read_all)
        for r in batches:
            hub.publish("logs", r)
        self._buffer.extend(batches)
        if self._buffer and len(self._buffer) >= settings.log_batch_size:
            batch, self._buffer = self._buffer, []
            await asyncio.to_thread(ldb.insert_logs, batch)
        elif self._buffer:
            batch, self._buffer = self._buffer, []
            await asyncio.to_thread(ldb.insert_logs, batch)

    def _read_all(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for f in self._discover():
            try:
                st = f.stat()
            except OSError:
                continue
            key = str(f)
            ino, off = self._positions.get(key, (st.st_ino, 0))
            if st.st_ino != ino:
                off = 0
                ino = st.st_ino
            if st.st_size < off:
                off = 0
            try:
                with f.open("rb") as fh:
                    fh.seek(off)
                    chunk = fh.read(1_000_000)
                    new_off = fh.tell()
            except OSError:
                continue
            self._positions[key] = (ino, new_off)
            if not chunk:
                continue
            for line in chunk.splitlines():
                s = line.decode("utf-8", errors="replace").strip()
                if not s:
                    continue
                out.append(self._parse(s, f.name))
        return out

    def _parse(self, line: str, source_name: str) -> dict[str, Any]:
        if line.startswith("{") and line.endswith("}"):
            try:
                j = json.loads(line)
                ts_raw = j.get("ts") or j.get("time") or j.get("timestamp")
                ts = (
                    datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                    if ts_raw
                    else datetime.fromtimestamp(time.time())
                )
                return {
                    "ts": ts,
                    "level": (j.get("level") or j.get("lvl") or "INFO").upper(),
                    "service": j.get("service") or j.get("svc") or source_name,
                    "host": j.get("host") or os.uname().nodename,
                    "message": j.get("msg") or j.get("message") or line,
                    "fields": {k: v for k, v in j.items() if k not in ("ts", "time", "timestamp", "level", "lvl", "service", "svc", "host", "msg", "message")},
                    "source": "filelog",
                }
            except (json.JSONDecodeError, ValueError):
                pass
        return {
            "ts": datetime.fromtimestamp(time.time()),
            "level": "INFO",
            "service": source_name,
            "host": os.uname().nodename,
            "message": line,
            "fields": {},
            "source": "filelog",
        }
