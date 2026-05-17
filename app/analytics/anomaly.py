"""Rolling z-score anomaly detection.

Lightweight per-metric anomaly detection inspired by Netdata's ML pattern,
simplified for Jetson-class edge devices:
- Maintain rolling buffer per metric (default 60 samples)
- After warmup (30 samples), flag values > 3 sigma as anomalies
- No training phase, no external ML deps
- Active anomalies surfaced via hub.publish('anomalies', ...)

Configuration via env/settings (see app/config.py):
    SH_ANOMALY_WINDOW=60      # samples per rolling buffer
    SH_ANOMALY_MIN_SAMPLES=30 # required before flagging
    SH_ANOMALY_Z_THRESHOLD=3.0
    SH_ANOMALY_INTERVAL_S=2.0 # how often to sample from hub
"""

from __future__ import annotations

import asyncio
import logging
import os
import statistics
import time
from collections import deque
from typing import Any

from app.hub import hub

log = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


_WINDOW = _env_int("SH_ANOMALY_WINDOW", 60)
_MIN_SAMPLES = _env_int("SH_ANOMALY_MIN_SAMPLES", 30)
_Z_THRESHOLD = _env_float("SH_ANOMALY_Z_THRESHOLD", 3.0)
_INTERVAL_S = _env_float("SH_ANOMALY_INTERVAL_S", 2.0)

# z above this is treated as a regime change (workload loaded/unloaded),
# not a point anomaly — buffer is reset to the new baseline instead of flagging.
_REGIME_Z = _env_float("SH_ANOMALY_REGIME_Z", 12.0)

# Per-metric stdev floor prevents hypersensitive baselines when a metric is
# briefly stable (e.g. mem.pct constant at 77% → stdev≈0 → z=170 on any drop).
# Unit matches the metric value (%, bps, etc.).
_STDEV_FLOOR: dict[str, float] = {
    "mem.pct": 2.0,
    "swap.pct": 1.0,
    "cpu.total": 3.0,
    "cpu.saturation_pct": 3.0,
    "cpu.load1": 0.2,
    "io.wait": 0.5,
    "net.rx_bps": 10_000.0,
    "net.tx_bps": 10_000.0,
    "jetson.gpu_load": 3.0,
    "jetson.soc_temp": 1.0,
    "jetson.power_w": 0.5,
}
_STDEV_FLOOR_DEFAULT = _env_float("SH_ANOMALY_STDEV_FLOOR", 0.5)


class AnomalyDetector:
    """Rolling z-score anomaly detector.

    Usage:
        detector = AnomalyDetector()
        await detector.start()
        ...
        await detector.stop()

    Read current anomalies:
        detector.current()  # list[dict] with metric, value, mean, z, ts
    """

    def __init__(self) -> None:
        self.buffers: dict[str, deque] = {}
        self.active: dict[str, dict[str, Any]] = {}
        self._task: asyncio.Task | None = None
        self._history: deque = deque(maxlen=500)  # last 500 flagged events for history

    def observe(self, metric: str, value: float, ts: int) -> bool:
        """Push value into metric buffer; return True if value is anomalous."""
        if value is None or not isinstance(value, (int, float)):
            return False
        try:
            value_f = float(value)
        except (TypeError, ValueError):
            return False

        buf = self.buffers.setdefault(metric, deque(maxlen=_WINDOW))

        if len(buf) < _MIN_SAMPLES:
            buf.append(value_f)
            return False

        try:
            mean = statistics.mean(buf)
            stdev = statistics.stdev(buf)
        except statistics.StatisticsError:
            buf.append(value_f)
            return False

        buf.append(value_f)

        if stdev < 1e-6:
            # Constant metric: no anomaly possible
            self.active.pop(metric, None)
            return False

        # Apply per-metric stdev floor to prevent hypersensitive baselines.
        # A very stable period (e.g. mem flat at 77% → stdev≈0.1) would otherwise
        # produce z=170 on a normal workload shift. The floor ensures z stays sane.
        stdev_eff = max(stdev, _STDEV_FLOOR.get(metric, _STDEV_FLOOR_DEFAULT))
        z = abs(value_f - mean) / stdev_eff

        if z > _REGIME_Z:
            # Regime change (e.g. Ollama loaded/unloaded, reboot, collector restart).
            # Reset buffer to new baseline so future samples get a fresh mean.
            buf.clear()
            buf.append(value_f)
            self.active.pop(metric, None)
            return False

        if z > _Z_THRESHOLD:
            entry = {
                "metric": metric,
                "value": round(value_f, 4),
                "mean": round(mean, 4),
                "stdev": round(stdev_eff, 4),
                "z": round(z, 2),
                "ts": int(ts),
            }
            is_new = metric not in self.active
            self.active[metric] = entry
            self._history.append(entry)
            if is_new:
                try:
                    from app.alerts.router import alert_router
                    alert_router.send_sync(
                        "warn",
                        "anomaly",
                        f"{metric} z={round(z,2)} value={round(value_f,4)}",
                        context=entry,
                    )
                except Exception:
                    pass
            # Return True only on transition into anomalous state so the caller
            # logs once per event, not once per sample for the entire duration.
            return is_new

        # Back to normal
        self.active.pop(metric, None)
        return False

    def current(self) -> list[dict[str, Any]]:
        return sorted(
            list(self.active.values()),
            key=lambda e: e.get("z", 0),
            reverse=True,
        )

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._history)[-limit:]

    @staticmethod
    def _flatten_snapshot(snap: dict[str, Any]) -> dict[str, float]:
        """Extract scalar metrics from live snapshots for observation."""
        out: dict[str, float] = {}
        data = snap.get("data") or {}

        cpu = data.get("cpu") or {}
        if isinstance(cpu, dict):
            for k in ("total", "saturation_pct", "ctx_switch_rate", "intr_rate"):
                if k in cpu and isinstance(cpu[k], (int, float)):
                    out[f"cpu.{k}"] = float(cpu[k])
            load = cpu.get("load") or []
            if isinstance(load, list) and load:
                out["cpu.load1"] = float(load[0])

        mem = data.get("mem") or {}
        if isinstance(mem, dict):
            total = mem.get("total") or 0
            used = mem.get("used") or 0
            if total:
                out["mem.pct"] = 100.0 * float(used) / float(total)
            if "swap_used" in mem and "swap_total" in mem and mem["swap_total"]:
                out["swap.pct"] = 100.0 * float(mem["swap_used"]) / float(mem["swap_total"])

        net = data.get("net") or {}
        for k in ("rx_bps", "tx_bps"):
            if k in net and isinstance(net[k], (int, float)):
                out[f"net.{k}"] = float(net[k])

        if "io_wait" in data and isinstance(data["io_wait"], (int, float)):
            out["io.wait"] = float(data["io_wait"])

        pressure = data.get("pressure") or {}
        for kind, fields in pressure.items():
            if isinstance(fields, dict):
                some_avg10 = fields.get("some_avg10")
                if isinstance(some_avg10, (int, float)):
                    out[f"pressure.{kind}.some_avg10"] = float(some_avg10)

        for k in ("gpu_load", "soc_temp", "power_w", "fan_pct", "emc_load"):
            if k in data and isinstance(data[k], (int, float)):
                out[f"jetson.{k}"] = float(data[k])

        return out

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(_INTERVAL_S)
                ts = int(time.time())
                for channel in ("system", "jetson"):
                    snap = hub.latest(channel)
                    if not snap:
                        continue
                    flat = self._flatten_snapshot(snap)
                    for metric, value in flat.items():
                        if self.observe(metric, value, ts):
                            log.info(
                                "anomaly detected: %s value=%.3f mean=%.3f z=%.2f",
                                metric,
                                value,
                                self.active[metric]["mean"],
                                self.active[metric]["z"],
                            )
                hub.publish("anomalies", {"current": self.current(), "count": len(self.active)})
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("anomaly detector loop error")

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="anomaly-detector")

    async def stop(self) -> None:
        t = self._task
        self._task = None
        if t is None:
            return
        t.cancel()
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass


detector = AnomalyDetector()
