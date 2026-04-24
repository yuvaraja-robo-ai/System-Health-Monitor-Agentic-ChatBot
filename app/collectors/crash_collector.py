import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.collectors.base import Collector
from app.db import sqlite as sdb
from app.host import detect
from app.hub import hub

log = logging.getLogger(__name__)

_SIGNALS = re.compile(r"\b(SIGSEGV|SIGKILL|SIGTERM|SIGABRT|SIGBUS|SIGFPE)\b")
_EXIT = re.compile(r"exit(?:ed)?(?:\s+(?:code|status|with))?\s*[=:]?\s*(-?\d+)", re.I)


class CrashCollector(Collector):
    name = "crash"
    interval_s = 30.0

    def __init__(self) -> None:
        super().__init__()
        self._seen: set[tuple[int, str]] = set()

    async def tick(self) -> None:
        if not detect().has_journald:
            hub.publish("crashes", {"ts": int(time.time()), "counts": {}, "recent": []})
            return
        events = await asyncio.to_thread(self._scan)
        counts: dict[str, int] = {}
        recent: list[dict[str, Any]] = []
        for ev in events:
            counts[ev["signal"]] = counts.get(ev["signal"], 0) + 1
            recent.append(ev)
            key = (ev["ts"], ev.get("unit") or ev.get("message", "")[:60])
            if key not in self._seen:
                self._seen.add(key)
                sdb.log_event(f"crash.{ev['signal']}", ev)
        hub.publish(
            "crashes",
            {"ts": int(time.time()), "counts": counts, "recent": recent[-50:]},
        )

    def _scan(self) -> list[dict[str, Any]]:
        from systemd import journal  # type: ignore

        r = journal.Reader()
        r.seek_realtime(datetime.now(timezone.utc) - timedelta(hours=24))
        out: list[dict[str, Any]] = []
        while True:
            e = r.get_next()
            if not e:
                break
            msg = e.get("MESSAGE")
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8", errors="replace")
            if not isinstance(msg, str):
                continue
            sig_match = _SIGNALS.search(msg)
            exit_match = _EXIT.search(msg)
            if not (sig_match or (exit_match and exit_match.group(1) not in ("0",))):
                continue
            sig = sig_match.group(1) if sig_match else f"exit{exit_match.group(1)}"
            ts = e.get("__REALTIME_TIMESTAMP")
            out.append(
                {
                    "ts": int(ts.timestamp()) if isinstance(ts, datetime) else int(time.time()),
                    "signal": sig,
                    "unit": e.get("_SYSTEMD_UNIT") or e.get("SYSLOG_IDENTIFIER"),
                    "message": msg[:240],
                }
            )
        r.close()
        return out
