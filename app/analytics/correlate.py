"""Metric correlation during incidents.

When an event triggers (anomaly / leak / crash), compute how much each
metric deviated in the incident window vs. a baseline window (4x longer,
immediately preceding). Inspired by Netdata Metric Correlations:
https://learn.netdata.cloud/docs/machine-learning-and-anomaly-detection/metric-correlations

Two outputs:
  - volume: per-metric % change from baseline (volume heuristic)
  - pairs:  pairwise Pearson correlation coefficient over the incident window
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.db import sqlite as sdb

log = logging.getLogger(__name__)


# Core system metrics always checked
_SYSTEM_METRICS = [
    "cpu.total",
    "cpu.load1",
    "cpu.saturation_pct",
    "cpu.ctx_switch_rate",
    "cpu.intr_rate",
    "mem.used",
    "mem.available",
    "mem.swap_used",
    "net.rx",
    "net.tx",
    "io.wait",
    "pressure.cpu.some_avg10",
    "pressure.memory.some_avg10",
    "pressure.io.some_avg10",
]

# Jetson-specific metrics checked when available
_JETSON_METRICS = [
    "gpu.load",
    "gpu.ram_used",
    "soc.temp",
    "power.total_w",
    "fan.pct",
    "emc.load",
    "swap.used",
]


def _pearson(a: list[float], b: list[float]) -> float | None:
    """Pearson correlation coefficient between two equal-length lists."""
    n = len(a)
    if n < 3 or n != len(b):
        return None
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    num = 0.0
    ssa = 0.0
    ssb = 0.0
    for x, y in zip(a, b):
        dx = x - mean_a
        dy = y - mean_b
        num += dx * dy
        ssa += dx * dx
        ssb += dy * dy
    if ssa < 1e-12 or ssb < 1e-12:
        return None
    return num / ((ssa * ssb) ** 0.5)


def _all_metrics() -> list[str]:
    return list(_SYSTEM_METRICS) + list(_JETSON_METRICS)


def _fetch_series(metric: str, start: int, end: int, step: int) -> list[float]:
    try:
        rows = sdb.history(metric, start, end, step)
    except Exception:
        return []
    return [float(v) for _, v in rows if v is not None]


def volume_rank(incident_ts: int, window_s: int = 300) -> list[dict[str, Any]]:
    """Rank metrics by magnitude of change in incident window vs. baseline.

    Args:
        incident_ts: epoch seconds at which the incident was detected
        window_s: length of the incident window in seconds

    Returns:
        list of dicts: {metric, baseline_mean, incident_mean, delta_pct, n_incident, n_baseline}
        sorted by abs(delta_pct) descending
    """
    incident_start = incident_ts - window_s
    baseline_start = incident_start - (4 * window_s)
    step = max(1, window_s // 20)

    results: list[dict[str, Any]] = []
    for metric in _all_metrics():
        incident_vals = _fetch_series(metric, incident_start, incident_ts, step)
        baseline_vals = _fetch_series(metric, baseline_start, incident_start, step)

        if not incident_vals or not baseline_vals:
            continue

        base_mean = sum(baseline_vals) / len(baseline_vals)
        inc_mean = sum(incident_vals) / len(incident_vals)

        if abs(base_mean) < 1e-6:
            delta_pct = 0.0 if abs(inc_mean) < 1e-6 else 100.0
        else:
            delta_pct = 100.0 * (inc_mean - base_mean) / abs(base_mean)

        results.append({
            "metric": metric,
            "baseline_mean": round(base_mean, 3),
            "incident_mean": round(inc_mean, 3),
            "delta_pct": round(delta_pct, 2),
            "abs_delta_pct": round(abs(delta_pct), 2),
            "n_incident": len(incident_vals),
            "n_baseline": len(baseline_vals),
        })

    results.sort(key=lambda r: r["abs_delta_pct"], reverse=True)
    return results


def pair_correlations(ts: int, window_s: int = 300, min_abs_r: float = 0.6) -> list[dict[str, Any]]:
    """Return top metric pairs with strong Pearson correlation in the window."""
    start = ts - window_s
    step = max(1, window_s // 30)

    series: dict[str, list[float]] = {}
    for metric in _all_metrics():
        vals = _fetch_series(metric, start, ts, step)
        if len(vals) >= 10:
            series[metric] = vals

    # Align lengths (use min length)
    if not series:
        return []
    min_len = min(len(v) for v in series.values())
    if min_len < 10:
        return []
    for k in list(series):
        series[k] = series[k][-min_len:]

    pairs: list[dict[str, Any]] = []
    keys = list(series.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a = series[keys[i]]
            b = series[keys[j]]
            r = _pearson(a, b)
            if r is None or abs(r) < min_abs_r:
                continue
            pairs.append({
                "a": keys[i],
                "b": keys[j],
                "r": round(r, 3),
                "abs_r": round(abs(r), 3),
            })

    pairs.sort(key=lambda p: p["abs_r"], reverse=True)
    return pairs


def correlate(
    incident_ts: int | None = None,
    window_s: int = 300,
    top: int = 15,
) -> dict[str, Any]:
    """Convenience — compute both volume rank and pair correlation for an incident.

    Returns:
        {
            "ts": ...,
            "window_s": ...,
            "volume": [...],   # top N metrics by % change
            "pairs":  [...],   # top pairs by |r|
        }
    """
    if incident_ts is None:
        incident_ts = int(time.time())

    volume = volume_rank(incident_ts, window_s)[:top]
    pairs = pair_correlations(incident_ts, window_s)[:top]

    return {
        "ts": incident_ts,
        "window_s": window_s,
        "volume": volume,
        "pairs": pairs,
    }
