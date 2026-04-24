import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats

from app.config import settings
from app.db import sqlite as sdb
from app.hub import hub

log = logging.getLogger(__name__)


@dataclass
class LeakResult:
    pid: int
    name: str
    slope_mb_min: float
    r2: float
    ttl_oom_s: float | None
    delta_6h_mb: float | None
    rss_mb: float
    samples: int
    span_s: int
    flagged: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "slope_mb_min": round(self.slope_mb_min, 4),
            "r2": round(self.r2, 3),
            "ttl_oom_s": int(self.ttl_oom_s) if self.ttl_oom_s is not None else None,
            "delta_6h_mb": round(self.delta_6h_mb, 2) if self.delta_6h_mb is not None else None,
            "rss_mb": round(self.rss_mb, 2),
            "samples": self.samples,
            "span_s": self.span_s,
            "flagged": self.flagged,
        }


class LeakDetector:
    def __init__(self) -> None:
        self._buffers: dict[int, deque] = defaultdict(lambda: deque(maxlen=settings.leak_window_s))
        self._names: dict[int, str] = {}
        self._last: dict[int, LeakResult] = {}
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def ingest(self, snapshot: dict[str, Any]) -> None:
        ts = snapshot.get("ts")
        if ts is None:
            return
        for p in snapshot.get("procs", []):
            pid = p["pid"]
            self._names[pid] = p["name"]
            self._buffers[pid].append((ts, p["rss"]))

    def _snapshot_buffers(self) -> tuple[dict[int, list], dict[int, str]]:
        return (
            {pid: list(buf) for pid, buf in self._buffers.items()},
            dict(self._names),
        )

    async def start(self) -> None:
        queue = hub.subscribe("processes")
        self._stop.clear()

        async def pump() -> None:
            while not self._stop.is_set():
                try:
                    env = await asyncio.wait_for(queue.get(), timeout=1.0)
                    self.ingest(env["data"])
                except asyncio.TimeoutError:
                    continue

        async def analyze() -> None:
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=settings.leak_update_s)
                    return
                except asyncio.TimeoutError:
                    pass
                try:
                    buffers, names = self._snapshot_buffers()
                    await asyncio.to_thread(self._analyze, buffers, names)
                except Exception:
                    log.exception("leak analysis failed")

        self._task = asyncio.gather(pump(), analyze())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

    def _analyze(self, buffers: dict[int, list], names: dict[int, str]) -> None:
        import psutil

        vm = psutil.virtual_memory()
        avail = vm.available
        results: list[LeakResult] = []
        changed = False

        dead = [p for p in list(buffers.keys()) if not psutil.pid_exists(p)]
        for d in dead:
            buffers.pop(d, None)
            self._last.pop(d, None)

        for pid in list(buffers.keys()):
            buf = buffers[pid]
            if len(buf) < settings.leak_min_samples:
                continue
            ts = np.fromiter((t for t, _ in buf), dtype=np.float64)
            rss = np.fromiter((r for _, r in buf), dtype=np.float64) / (1024 * 1024)
            span = int(ts[-1] - ts[0])
            if span < 60:
                continue
            t_min = (ts - ts[0]) / 60.0
            try:
                reg = stats.linregress(t_min, rss)
            except ValueError:
                continue
            slope = float(reg.slope)
            r2 = float(reg.rvalue ** 2)
            flagged = (
                slope >= settings.leak_slope_mb_min
                and r2 >= settings.leak_min_r2
                and span >= settings.leak_min_span_s
            )
            ttl = None
            if flagged and slope > 0:
                headroom_mb = max(0.0, (avail - rss[-1] * 1024 * 1024) / (1024 * 1024))
                ttl = (headroom_mb / slope) * 60.0
            delta_6h = None
            try:
                since = int(time.time()) - 6 * 3600
                first, last = sdb.proc_rss_range(pid, since, int(time.time()))
                if first and last:
                    delta_6h = (last - first) / (1024 * 1024)
            except Exception:
                pass
            res = LeakResult(
                pid=pid,
                name=names.get(pid, str(pid)),
                slope_mb_min=slope,
                r2=r2,
                ttl_oom_s=ttl,
                delta_6h_mb=delta_6h,
                rss_mb=float(rss[-1]),
                samples=len(buf),
                span_s=span,
                flagged=flagged,
            )
            prev = self._last.get(pid)
            if prev is None or prev.flagged != res.flagged or abs(prev.slope_mb_min - slope) > 0.1:
                changed = True
            self._last[pid] = res
            results.append(res)

        results.sort(key=lambda r: (not r.flagged, -r.slope_mb_min))
        payload = {"ts": int(time.time()), "results": [r.to_dict() for r in results[:50]]}
        if changed or not results:
            hub.publish("leaks", payload)

    def current(self) -> list[dict[str, Any]]:
        items = sorted(self._last.values(), key=lambda r: (not r.flagged, -r.slope_mb_min))
        return [r.to_dict() for r in items[:50]]


detector = LeakDetector()
