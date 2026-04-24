import asyncio
import logging
import time
from collections import deque
from typing import Any

from app.api.thresholds import get_thresholds
from app.db import sqlite as sdb
from app.hub import hub

log = logging.getLogger(__name__)


def _compute_score(
    sys_snap: dict[str, Any],
    jetson: dict[str, Any],
    anomalies: list[dict[str, Any]],
    leaks: list[dict[str, Any]],
    crashes: dict[str, int],
) -> dict[str, Any]:
    score = 100.0
    drivers: list[dict[str, Any]] = []
    t = get_thresholds()

    cpu = sys_snap.get("cpu", {}) or {}
    mem = sys_snap.get("mem", {}) or {}
    pressure = sys_snap.get("pressure", {}) or {}

    # USE — Utilization
    cpu_total = cpu.get("total", 0.0) or 0.0
    if cpu_total > t["cpu_err"]:
        score -= 10; drivers.append({"factor": "cpu_util", "weight": -10, "value": round(cpu_total, 1)})
    elif cpu_total > t["cpu_warn"]:
        score -= 4; drivers.append({"factor": "cpu_util", "weight": -4, "value": round(cpu_total, 1)})

    mem_total = mem.get("total") or 0
    mem_used = mem.get("used") or 0
    if mem_total > 0:
        mem_pct = 100.0 * mem_used / mem_total
        if mem_pct > t["mem_err"]:
            score -= 15; drivers.append({"factor": "mem_util", "weight": -15, "value": round(mem_pct, 1)})
        elif mem_pct > t["mem_warn"]:
            score -= 6; drivers.append({"factor": "mem_util", "weight": -6, "value": round(mem_pct, 1)})

    # USE — Saturation (load vs cores)
    load = cpu.get("load") or []
    cores = cpu.get("cores") or 1
    load1 = load[0] if load else 0.0
    sat_pct = cpu.get("saturation_pct") or (100.0 * load1 / cores if cores else 0.0)
    if sat_pct > 150:
        score -= 15; drivers.append({"factor": "cpu_saturation", "weight": -15, "value": round(sat_pct, 1)})
    elif sat_pct > 100:
        score -= 7; drivers.append({"factor": "cpu_saturation", "weight": -7, "value": round(sat_pct, 1)})

    # USE — Errors (PSI pressure)
    psi_cpu = (pressure.get("cpu") or {}).get("some_avg10") or 0.0
    psi_mem = (pressure.get("memory") or {}).get("some_avg10") or 0.0
    psi_io = (pressure.get("io") or {}).get("some_avg10") or 0.0
    if psi_mem > t["psi_mem_err"]:
        score -= 10; drivers.append({"factor": "mem_pressure", "weight": -10, "value": round(psi_mem, 1)})
    elif psi_mem > t["psi_mem_warn"]:
        score -= 4; drivers.append({"factor": "mem_pressure", "weight": -4, "value": round(psi_mem, 1)})
    if psi_io > t["psi_io_err"]:
        score -= 8; drivers.append({"factor": "io_pressure", "weight": -8, "value": round(psi_io, 1)})
    elif psi_io > t["psi_io_warn"]:
        score -= 3; drivers.append({"factor": "io_pressure", "weight": -3, "value": round(psi_io, 1)})
    if psi_cpu > t["psi_mem_err"]:
        score -= 5; drivers.append({"factor": "cpu_pressure", "weight": -5, "value": round(psi_cpu, 1)})

    # Disk
    for d in sys_snap.get("disks", []) or []:
        dpct = d.get("pct") or 0
        if dpct > t["disk_err"]:
            score -= 10; drivers.append({"factor": "disk", "weight": -10, "value": dpct, "mount": d.get("mount")})
        elif dpct > t["disk_warn"]:
            score -= 4; drivers.append({"factor": "disk", "weight": -4, "value": dpct, "mount": d.get("mount")})

    # Temperature (non-Jetson host sensors)
    if not jetson:
        temps = sys_snap.get("temps") or {}
        hottest = max((v for v in temps.values() if v is not None), default=0.0)
        if hottest > t["temp_err"]:
            score -= 12; drivers.append({"factor": "thermal", "weight": -12, "value": round(hottest, 1)})
        elif hottest > t["temp_warn"]:
            score -= 5; drivers.append({"factor": "thermal", "weight": -5, "value": round(hottest, 1)})

    # Jetson-specific
    if jetson:
        soc_temp = jetson.get("soc_temp") or 0.0
        if soc_temp > t["temp_err"]:
            score -= 15; drivers.append({"factor": "thermal", "weight": -15, "value": round(soc_temp, 1)})
        elif soc_temp > t["temp_warn"]:
            score -= 5; drivers.append({"factor": "thermal", "weight": -5, "value": round(soc_temp, 1)})
        gpu_load = jetson.get("gpu_load") or 0.0
        if gpu_load > t["gpu_err"]:
            score -= 8; drivers.append({"factor": "gpu_util", "weight": -8, "value": round(gpu_load, 1)})
        elif gpu_load > t["gpu_warn"]:
            score -= 3; drivers.append({"factor": "gpu_util", "weight": -3, "value": round(gpu_load, 1)})
        power_w = jetson.get("power_w") or 0.0
        if power_w > t["power_err"]:
            score -= 8; drivers.append({"factor": "power", "weight": -8, "value": round(power_w, 1)})
        elif power_w > t["power_warn"]:
            score -= 3; drivers.append({"factor": "power", "weight": -3, "value": round(power_w, 1)})

    # Leaks
    leak_flags = [l for l in leaks if l.get("flagged")]
    if leak_flags:
        delta = min(20, 5 * len(leak_flags))
        score -= delta; drivers.append({"factor": "leaks", "weight": -delta, "count": len(leak_flags)})

    # Crashes
    crash_total = sum(crashes.values())
    if crash_total >= 3:
        score -= 15; drivers.append({"factor": "crashes", "weight": -15, "count": crash_total})
    elif crash_total:
        score -= 5; drivers.append({"factor": "crashes", "weight": -5, "count": crash_total})

    # Anomalies
    n_anom = len(anomalies)
    if n_anom:
        delta = min(20, 5 * n_anom)
        score -= delta; drivers.append({"factor": "anomalies", "weight": -delta, "count": n_anom})

    score = max(0, min(100, int(round(score))))
    drivers.sort(key=lambda d: d["weight"])
    return {"score": score, "drivers": drivers}


class HealthScorer:
    def __init__(self) -> None:
        self._history: deque[tuple[int, float]] = deque(maxlen=1440)
        self._last_score: int | None = None
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._latest: dict[str, Any] = {"score": 100, "history": [], "drivers": []}

    def score(
        self,
        sys_snap: dict[str, Any],
        leaks: list[dict[str, Any]],
        crashes: dict[str, int],
        anomalies: list[dict[str, Any]] | None = None,
        jetson: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = _compute_score(sys_snap, jetson or {}, anomalies or [], leaks, crashes)
        ts = int(time.time())
        self._history.append((ts, result["score"]))
        sdb.write_metrics([(ts, "health.score", float(result["score"]))])
        result["history"] = list(self._history)
        return result

    def latest(self) -> dict[str, Any]:
        return self._latest

    async def start(self) -> None:
        self._stop.clear()

        async def run() -> None:
            from app.analytics.anomaly import detector as anomaly_detector
            from app.analytics.leak import detector

            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=5.0)
                    return
                except asyncio.TimeoutError:
                    pass
                sys_snap = (hub.latest("system") or {}).get("data") or {}
                crashes = (hub.latest("crashes") or {}).get("data", {}).get("counts") or {}
                leaks = detector.current()
                anomalies = anomaly_detector.current()
                jetson = (hub.latest("jetson") or {}).get("data") or {}
                result = self.score(sys_snap, leaks, crashes, anomalies=anomalies, jetson=jetson or None)
                self._latest = result
                prev = self._last_score
                if prev is None or abs(result["score"] - prev) >= 1:
                    self._last_score = result["score"]
                    hub.publish("health", result)
                    if prev is not None and result["score"] <= 60 and result["score"] < prev - 10:
                        try:
                            from app.alerts.router import alert_router
                            top = result["drivers"][0] if result["drivers"] else {}
                            alert_router.send_sync(
                                "err" if result["score"] <= 40 else "warn",
                                "health",
                                f"health score dropped to {result['score']} (was {prev})",
                                context={"score": result["score"], "top_driver": top},
                            )
                        except Exception:
                            pass

        self._task = asyncio.create_task(run(), name="health-scorer")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass


scorer = HealthScorer()
