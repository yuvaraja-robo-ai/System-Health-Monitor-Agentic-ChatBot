# SystemHealth — Implementation Roadmap

**Status:** Design doc. Research done. Ready for step-by-step implementation.
**Purpose:** Durable record so any future session can resume from any checkpoint without re-research.
**Created:** 2026-04-23
**Based on research:** jtop docs, njmon/nmon, RED/USE methods, Netdata ML patterns, Prometheus/Grafana edge, Karpathy LLM-wiki pattern, LLMLogAnalyzer paper.

---

## Table of Contents

1. [Current State (What Exists)](#current-state)
2. [Research Summary (Best Practices)](#research-summary)
3. [Gap Analysis](#gap-analysis)
4. [Priority-Ordered Implementation Plan](#priority-ordered-implementation-plan)
5. [Feature Specs (Step-by-Step)](#feature-specs)
6. [File-Level Change Plan](#file-level-change-plan)
7. [Testing Checklist](#testing-checklist)
8. [Future Ideas (P4+)](#future-ideas)

---

## Current State

### What Already Works (Verified 2026-04-23)

**Backend (`app/`):**
- `PsutilCollector` — CPU, mem, disk, net (1s interval)
- `ProcessCollector` — per-process CPU/RSS/threads (2s)
- `AppMonitorCollector` — app-group roll-up (5s)
- `JtopCollector` — GPU, power rails, thermal, engines, EMC, swap (1s) [**extended**]
- `JournaldCollector` — systemd journal ingest (60s)
- `FileLogCollector` — custom file tails via `SH_LOG_APP_DIRS`
- `CrashCollector` — coredump events

**Analytics:**
- `detector.py` — leak detection via linear regression on RSS slope
- `scorer.py` — basic health score (leak + error + thermal weighted)

**Storage:**
- SQLite (`metrics.sqlite`) — raw + 10s + 1m downsampled, auto-prune
- DuckDB (`logs.duckdb`) — structured logs
- FAISS index — KB semantic search

**API Endpoints:**
- `/api/system/current|history` — metrics
- `/api/apps|apps/{name}|apps/{name}/njmon` — app roll-up
- `/api/processes` — process table
- `/api/units` — systemd state
- `/api/logs` — log search
- `/api/leaks` — detected leaks
- `/api/crashes` — crash events
- `/api/diagnose` — LLM-backed diagnostics
- `/api/kb/reload` — hot-reload KB [**new**]
- `/api/config/polling` — tick intervals
- `/api/config/apps` — pinned apps CRUD [**new**]
- `/ws/system|jetson|processes|logs|health` — WebSocket streams

**Dashboard (`dashboard.jsx`):**
- Tabs: overview, jetson [**new**], nmon, focus, terminal, briefing, hunter, processes, services, leaks, logs, crashes, diagnose
- Hooks: `useWS` (reconnect), `usePoll`, `useSeries` (ring buffer)
- Components: TopBar, Overview (KPI + CPU cores), JetsonDetail [**new**], NmonView (with app pinning), AppFocus, Processes, Services, Logs, Diagnose

**Knowledge Base (`data/kb/`):**
- 6 entries: high_cpu, memory_leak, thermal, gpu_overload, high_errors, log_analysis
- Format: `# Title`, `tags:`, `## Steps` parsed into FAISS

**Tools:**
- `tools/gen_kb_stubs.py` — auto-generate KB from live log clusters

---

## Research Summary

Key findings from 2026 industry best practices:

### RED Method (Rate, Errors, Duration)
- Rate: requests/sec
- Errors: error count or rate
- Duration: latency p50/p95/p99
- **Use for:** user-facing / service-level health
- Source: [betterstack RED/USE](https://betterstack.com/community/guides/monitoring/red-use-metrics/)

### USE Method (Utilization, Saturation, Errors)
- Utilization: % busy (CPU%, mem%, GPU%)
- Saturation: queue depth (load avg, PSI, run-queue)
- Errors: hardware/driver errors
- **Use for:** resource / infrastructure health
- **Key insight:** Most dashboards have Utilization + Errors but miss **Saturation** — which is the early warning.

### Netdata Pattern (ML anomaly)
- 18 unsupervised ML models per metric (lightweight)
- z-score / quantile / CUSUM
- Consensus detection = 99% false positive reduction
- 10-min baseline warmup
- Source: [Netdata ML](https://learn.netdata.cloud/docs/netdata-ai/anomaly-detection)

### Netdata Metric Correlation
- On alert, compare current window to baseline (4x length)
- KS2 statistical test OR Volume heuristic
- Rank all metrics by how much they deviated
- Top 30-50 = likely root cause signals
- Source: [Netdata Correlations](https://learn.netdata.cloud/docs/machine-learning-and-anomaly-detection/metric-correlations)

### njmon JSON (Single-level flat)
- Default single-level (Splunk/ELK prefer)
- Key: value pairs, no nesting
- Example: `{"cpu_user_pct": 12.3, "mem_used_mb": 4567}`
- Source: [njmon JSON](https://www.ibm.com/support/pages/nmon-json-plus-new-direct-json-monitor)

### jtop Jetson-Specific
- All metrics flat dict via `j.stats`
- Power rails per-component
- Temperature per-sensor
- Engine utilization (NVENC, NVDEC, DLA, VIC)
- NVP model
- Source: [jetson-stats GitHub](https://github.com/rbonghi/jetson_stats)
- [Reference Grafana dashboard](https://github.com/svcavallar/jetson-stats-grafana-dashboard)

### LLM Wiki Pattern (Karpathy)
- Markdown-first KB instead of pure vector RAG
- LLM writes/compiles its own wiki pages from raw data
- Explicit backlinks + summaries
- Already compatible with SystemHealth's `data/kb/*.md` approach
- Source: [Karpathy LLM Wiki](https://levelup.gitconnected.com/beyond-rag-how-andrej-karpathys-llm-wiki-pattern-builds-knowledge-that-actually-compounds-31a08528665e)

### LLMLogAnalyzer Architecture
- Router + log recognizer + log parser + search tools
- Cluster logs first (reduce token count), then LLM analyzes clusters
- Already implemented in `ldb.cluster_logs()` + `agent/diagnose.py`
- Source: [LLMLogAnalyzer paper](https://arxiv.org/html/2510.24031v1)

---

## Gap Analysis

Current vs. industry best-practice:

| Best Practice | Current | Gap | Severity |
|---------------|---------|-----|----------|
| USE Saturation metrics | Missing | **No load/queue/PSI metrics** | HIGH |
| Anomaly detection (ML/statistical) | Only leak regression | **No baseline z-score per metric** | HIGH |
| Metric correlation on incident | Missing | **No "what else spiked" view** | HIGH |
| RED service metrics | Error counts only | **No request rate/duration** | MEDIUM |
| Unified health score (USE+RED weighted) | Simple score | **Score doesn't reflect saturation/anomalies** | MEDIUM |
| Flat njmon JSON | Nested only | **Not Splunk/ELK ready** | LOW |
| Prometheus scrape endpoint | Missing | **Can't plug into fleet** | LOW |
| Alert routing (webhook/MQTT) | Missing | **No out-of-band notifications** | LOW |
| Dmesg kernel log collection | Code exists, not wired | **Optional collector not enabled** | LOW |
| Unified "Health" dashboard tab | Split across many tabs | **No single pane of glass** | MEDIUM |

---

## Priority-Ordered Implementation Plan

### P0 — Critical (highest ROI, do first)

| # | Feature | Est. Effort | File(s) |
|---|---------|-------------|---------|
| P0-1 | Saturation metrics (load avg, PSI, IO wait) | 1 hr | `psutil_collector.py` |
| P0-2 | Anomaly detector (rolling z-score) | 2 hr | `app/analytics/anomaly.py` (new) |
| P0-3 | Unified Health tab on dashboard | 2 hr | `dashboard.jsx`, `dashboard.css` |

### P1 — High value

| # | Feature | Est. Effort | File(s) |
|---|---------|-------------|---------|
| P1-1 | Metric correlation engine | 3 hr | `app/analytics/correlate.py` (new) |
| P1-2 | Weighted health score (USE+RED) | 1 hr | `app/analytics/health/scorer.py` |
| P1-3 | Wire DmesgCollector in main.py | 15 min | `app/main.py` |
| P1-4 | Correlation display in Diagnose tab | 1 hr | `dashboard.jsx` |

### P2 — Medium value

| # | Feature | Est. Effort | File(s) |
|---|---------|-------------|---------|
| P2-1 | Flat njmon JSON `?format=flat` | 30 min | `app/api/apps.py` |
| P2-2 | Prometheus `/metrics` endpoint | 1 hr | `app/api/prometheus.py` (new) |
| P2-3 | Alert thresholds UI (settings panel) | 2 hr | `dashboard.jsx` |
| P2-4 | RED-style request metrics for app services | 2 hr | `app/collectors/app_monitor_collector.py` |

### P3 — Low priority / polish

| # | Feature | Est. Effort | File(s) |
|---|---------|-------------|---------|
| P3-1 | Webhook/MQTT alert routing | 2 hr | `app/alerts/router.py` (new) |
| P3-2 | Alert cooldown + dedup | 1 hr | `app/alerts/router.py` |
| P3-3 | Fleet dashboard (multi-host) | 8 hr | Major — separate design |

---

## Feature Specs

### P0-1: Saturation Metrics

**Goal:** USE method — add queue-depth signals to detect early congestion.

**Metrics to add:**

| Metric | Source | Meaning |
|--------|--------|---------|
| `cpu.load_1m` | `os.getloadavg()[0]` | Runnable + running tasks |
| `cpu.saturation_pct` | `100 * load_1m / cpu_count` | >100% = saturated |
| `mem.pressure_some` | `/proc/pressure/memory` field `some avg10` | PSI memory pressure |
| `io.pressure_some` | `/proc/pressure/io` field `some avg10` | PSI I/O pressure |
| `cpu.pressure_some` | `/proc/pressure/cpu` field `some avg10` | PSI CPU pressure |
| `cpu.ctx_switch_rate` | delta of `psutil.cpu_stats().ctx_switches` | Rate of context switches |

**PSI (Pressure Stall Information):** Linux kernel 4.20+ feature. `/proc/pressure/{cpu,memory,io}` returns lines like `some avg10=0.05 avg60=0.02 avg300=0.01 total=12345`.

**Implementation sketch** (add to `psutil_collector.py`):

```python
import os
import time

class PsutilCollector:
    def __init__(self):
        self._prev_ctx = psutil.cpu_stats().ctx_switches
        self._prev_ts = time.time()

    def _sample_saturation(self) -> dict:
        out = {}
        try:
            out["cpu.load_1m"] = os.getloadavg()[0]
            out["cpu.saturation_pct"] = 100.0 * out["cpu.load_1m"] / (os.cpu_count() or 1)
        except OSError:
            pass

        # PSI — Linux 4.20+
        for kind in ("cpu", "memory", "io"):
            try:
                with open(f"/proc/pressure/{kind}") as f:
                    for line in f:
                        if line.startswith("some "):
                            parts = dict(p.split("=") for p in line.split()[1:])
                            out[f"{kind}.pressure_some"] = float(parts.get("avg10", 0))
                            break
            except (OSError, ValueError):
                pass

        # Context switch rate
        now = time.time()
        cur = psutil.cpu_stats().ctx_switches
        dt = max(0.1, now - self._prev_ts)
        out["cpu.ctx_switch_rate"] = (cur - self._prev_ctx) / dt
        self._prev_ctx = cur
        self._prev_ts = now

        return out
```

**Persistence:** Add these to `sdb.write_metrics()` rows list.

**Dashboard display:** Add "Saturation" card to Overview tab — 3 mini-bars for CPU/mem/IO PSI.

---

### P0-2: Anomaly Detector

**Goal:** Auto-flag any metric deviating from rolling baseline (Netdata pattern, lightweight).

**Design:**
- Per-metric rolling buffer (60 samples @ 1s = 1 min baseline)
- When 30+ samples collected: compute z-score for new value
- z > 3 = anomaly → emit event to hub
- Dashboard shows list of currently anomalous metrics

**New file:** `app/analytics/anomaly.py`

```python
"""Lightweight anomaly detection via rolling z-score.

Inspired by Netdata's per-metric ML approach but simplified:
- Maintain 60-sample rolling buffer per metric
- Flag values > 3 sigma as anomalies
- No training phase required — warmup = first 30 samples
"""

import asyncio
import logging
import statistics
from collections import deque
from typing import Any

from app.hub import hub

log = logging.getLogger(__name__)

_WINDOW = 60       # samples
_MIN_SAMPLES = 30  # before flagging
_Z_THRESHOLD = 3.0


class AnomalyDetector:
    def __init__(self):
        self.buffers: dict[str, deque] = {}
        self.active: dict[str, dict[str, Any]] = {}  # metric → {ts, value, z}
        self._task = None

    def observe(self, metric: str, value: float, ts: int) -> bool:
        """Return True if value is anomalous."""
        buf = self.buffers.setdefault(metric, deque(maxlen=_WINDOW))
        if len(buf) < _MIN_SAMPLES:
            buf.append(value)
            return False
        try:
            mean = statistics.mean(buf)
            stdev = statistics.stdev(buf)
        except statistics.StatisticsError:
            buf.append(value)
            return False
        if stdev < 1e-6:  # constant metric — no anomaly possible
            buf.append(value)
            return False
        z = abs(value - mean) / stdev
        buf.append(value)
        if z > _Z_THRESHOLD:
            self.active[metric] = {"ts": ts, "value": value, "mean": mean, "z": z}
            return True
        # Clear active if back to normal
        self.active.pop(metric, None)
        return False

    def current(self) -> list[dict[str, Any]]:
        return [{"metric": k, **v} for k, v in self.active.items()]

    async def start(self):
        """Subscribe to system metric stream, observe each."""
        async def run():
            while True:
                await asyncio.sleep(2)
                snap = hub.latest("system")
                if not snap:
                    continue
                data = snap.get("data", {})
                ts = data.get("ts", 0)
                # Flatten top metrics
                flat = {
                    "cpu.total": data.get("cpu", {}).get("total", 0),
                    "mem.used": data.get("mem", {}).get("used", 0),
                    "net.rx_bps": data.get("net", {}).get("rx_bps", 0),
                    "net.tx_bps": data.get("net", {}).get("tx_bps", 0),
                }
                jetson = hub.latest("jetson")
                if jetson:
                    j = jetson.get("data", {})
                    flat["gpu.load"] = j.get("gpu_load", 0)
                    flat["soc.temp"] = j.get("soc_temp", 0)
                    flat["power.total_w"] = j.get("power_w", 0)
                for k, v in flat.items():
                    if self.observe(k, float(v), ts):
                        log.info(f"anomaly: {k}={v:.2f} z={self.active[k]['z']:.2f}")
                hub.publish("anomalies", {"current": self.current()})

        self._task = asyncio.create_task(run(), name="anomaly-detector")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try: await self._task
            except (asyncio.CancelledError, Exception): pass


detector = AnomalyDetector()
```

**Register in `app/main.py` lifespan:**
```python
from app.analytics.anomaly import detector as anomaly_detector
# In setup:
await anomaly_detector.start()
# In shutdown:
await anomaly_detector.stop()
```

**API endpoint** (add to `app/api/derived.py` or new file):
```python
@router.get("/api/anomalies")
def get_anomalies():
    from app.analytics.anomaly import detector
    return {"current": detector.current()}
```

**Dashboard display:** Anomaly chip on Health tab + small banner when any active.

---

### P0-3: Unified Health Tab

**Goal:** Single-pane-of-glass combining jtop + top + nmon + logs into one view.

**Layout** (new React component `<HealthView />`):

```
┌───────────────────────────────────────────────────────────────┐
│  HEALTH SCORE: 73 / 100   [warn]                              │
│  Drivers: cpu_saturation(-12) · leak(-10) · thermal(-5)       │
├───────────────────────────────────────────────────────────────┤
│  ┌──────────────────┬───────────────────┬────────────────┐    │
│  │ UTILIZATION      │ SATURATION        │ ERRORS         │    │
│  │ CPU 67% ████     │ Load 3.2 / 4 cores│ Errors: 12/hr  │    │
│  │ MEM 45% ███      │ PSI mem 0.05      │ Crashes: 1     │    │
│  │ GPU 89% ███████  │ PSI io 0.18 ⚠     │ Leaks: 2       │    │
│  └──────────────────┴───────────────────┴────────────────┘    │
├───────────────────────────────────────────────────────────────┤
│  🚨 ACTIVE ANOMALIES (3)                                      │
│  • soc.temp         82°C  z=4.2  (baseline 65°C)              │
│  • net.tx_bps       12MB/s z=3.8  (baseline 2MB/s)            │
│  • gpu.load         98%   z=3.1  (baseline 45%)               │
├───────────────────────────────────────────────────────────────┤
│  🔗 CORRELATED METRICS (last 5 min incident)                  │
│  soc.temp ↔ gpu.load      r=0.94                              │
│  soc.temp ↔ power.total_w r=0.87                              │
│  gpu.load ↔ net.tx_bps    r=0.65                              │
├───────────────────────────────────────────────────────────────┤
│  🔥 THERMAL HEATMAP (all Jetson sensors)                      │
│  [grid of sensor chips with color by temp]                    │
├───────────────────────────────────────────────────────────────┤
│  📊 TOP PROCESSES                 📜 RECENT ERRORS             │
│  (top 5 by CPU + RSS)             (top 5 log clusters)         │
└───────────────────────────────────────────────────────────────┘
```

**Implementation:** Add `<HealthView>` component reading from:
- `/api/health` (score + drivers)
- `/api/anomalies` (current anomalies, new)
- `/api/correlate` (correlations, P1-1)
- `/ws/system`, `/ws/jetson` (live metrics)
- `/api/processes`, `/api/logs?severity=ERR&limit=5`

**Add to tabs:** Insert `"health"` as first tab after `"overview"`.

---

### P1-1: Metric Correlation Engine

**Goal:** When incident (leak/crash/anomaly), show which other metrics spiked in same window.

**New file:** `app/analytics/correlate.py`

```python
"""Metric correlation during incidents.

When an event triggers (anomaly, crash, leak), compute Pearson correlation
between all metrics in the incident window vs. baseline window.
"""

import time
import numpy as np
from app.db import sqlite as sdb


# Metrics to consider in correlation
_METRICS = [
    "cpu.total", "cpu.load_1m", "cpu.saturation_pct", "cpu.pressure_some",
    "mem.used", "mem.pressure_some",
    "net.rx_bps", "net.tx_bps",
    "io.pressure_some",
    "gpu.load", "soc.temp", "power.total_w", "fan.pct",
    "emc.load",
]


def correlate(incident_ts: int, window_s: int = 300) -> list[dict]:
    """Return list of metrics ranked by correlation with incident.

    Compares incident window (last N sec before incident_ts) to
    baseline window (4x longer, preceding incident window).
    """
    incident_start = incident_ts - window_s
    baseline_start = incident_start - (4 * window_s)

    results = []
    for metric in _METRICS:
        incident_rows = sdb.history(metric, incident_start, incident_ts, 10)
        baseline_rows = sdb.history(metric, baseline_start, incident_start, 10)
        if not incident_rows or not baseline_rows:
            continue
        incident_vals = [r[1] for r in incident_rows]
        baseline_vals = [r[1] for r in baseline_rows]

        # Volume-based score (simpler than KS2)
        base_mean = np.mean(baseline_vals)
        inc_mean = np.mean(incident_vals)
        if abs(base_mean) < 1e-6:
            delta_pct = 0.0 if abs(inc_mean) < 1e-6 else 1.0
        else:
            delta_pct = abs(inc_mean - base_mean) / abs(base_mean)

        results.append({
            "metric": metric,
            "baseline_mean": round(base_mean, 3),
            "incident_mean": round(inc_mean, 3),
            "delta_pct": round(delta_pct * 100, 1),
        })

    # Sort by magnitude of change
    results.sort(key=lambda x: x["delta_pct"], reverse=True)
    return results[:15]


def pairwise_correlate(ts: int, window_s: int = 300) -> list[dict]:
    """Return top-N metric pairs with highest Pearson correlation in window."""
    start = ts - window_s
    series = {}
    for metric in _METRICS:
        rows = sdb.history(metric, start, ts, 10)
        if len(rows) < 10:
            continue
        series[metric] = np.array([r[1] for r in rows])

    # Align lengths
    min_len = min(len(v) for v in series.values()) if series else 0
    if min_len < 10:
        return []
    for k in list(series):
        series[k] = series[k][-min_len:]

    pairs = []
    keys = list(series.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = series[keys[i]], series[keys[j]]
            if np.std(a) < 1e-6 or np.std(b) < 1e-6:
                continue
            r = float(np.corrcoef(a, b)[0, 1])
            pairs.append({
                "a": keys[i],
                "b": keys[j],
                "r": round(r, 3),
            })

    pairs.sort(key=lambda x: abs(x["r"]), reverse=True)
    return pairs[:10]
```

**API endpoint:**
```python
@router.get("/api/correlate")
def correlate_endpoint(ts: int | None = None, window: int = 300):
    from app.analytics import correlate as cor
    ts = ts or int(time.time())
    return {
        "volume": cor.correlate(ts, window),
        "pairs": cor.pairwise_correlate(ts, window),
    }
```

---

### P1-2: Weighted Health Score (USE+RED)

**Current:** Simple additive score based on leak/error/thermal.

**Replace in `app/analytics/health/scorer.py`** (need to read current file first; sketch):

```python
def compute_score(system, jetson, anomalies, leaks, crashes_24h, error_rate) -> dict:
    score = 100
    drivers = []

    # USE — Utilization
    cpu = system.get("cpu", {}).get("total", 0)
    if cpu > 90:
        score -= 10; drivers.append({"factor": "cpu_util", "weight": -10})

    mem_used = system.get("mem", {}).get("used", 0)
    mem_total = system.get("mem", {}).get("total", 1)
    mem_pct = 100 * mem_used / mem_total
    if mem_pct > 90:
        score -= 15; drivers.append({"factor": "mem_util", "weight": -15})

    # USE — Saturation
    load = system.get("cpu", {}).get("load", [0])[0]
    cpu_count = system.get("cpu", {}).get("cores", 1)
    if load > cpu_count * 1.5:
        score -= 15; drivers.append({"factor": "cpu_saturation", "weight": -15})

    # PSI checks
    psi_mem = system.get("pressure", {}).get("memory_some", 0)
    if psi_mem > 0.1:
        score -= 10; drivers.append({"factor": "mem_pressure", "weight": -10})

    # Errors
    if leaks:
        score -= 20; drivers.append({"factor": "leak", "weight": -20, "count": len(leaks)})
    if crashes_24h > 3:
        score -= 15; drivers.append({"factor": "crashes", "weight": -15, "count": crashes_24h})
    if error_rate > 10:  # errors/min
        score -= 10; drivers.append({"factor": "error_rate", "weight": -10})

    # Anomalies
    n_anom = len(anomalies)
    if n_anom > 0:
        delta = min(20, 5 * n_anom)
        score -= delta
        drivers.append({"factor": "anomalies", "weight": -delta, "count": n_anom})

    # Jetson-specific
    if jetson:
        soc_temp = jetson.get("soc_temp", 0)
        if soc_temp > 80:
            score -= 15; drivers.append({"factor": "thermal", "weight": -15})
        elif soc_temp > 70:
            score -= 5; drivers.append({"factor": "thermal_warning", "weight": -5})

    score = max(0, score)
    drivers.sort(key=lambda d: d["weight"])  # Most negative first
    return {"score": score, "drivers": drivers}
```

---

### P1-3: Wire DmesgCollector

**File:** `app/main.py`

**Change:**
```python
from app.collectors.dmesg_collector import DmesgCollector  # add import

def _build_collectors() -> list:
    cap = detect()
    cs: list = [PsutilCollector(), ProcessCollector(), AppMonitorCollector()]
    if cap.has_jtop:
        cs.append(JtopCollector())
    if cap.has_journald:
        cs.append(JournaldCollector())
        cs.append(CrashCollector())
    if settings.log_app_dirs:
        cs.append(FileLogCollector())
    # ADD:
    if os.environ.get("SH_ENABLE_DMESG", "0") == "1":
        cs.append(DmesgCollector())
    return cs
```

**Add config flag** to `app/config.py`:
```python
enable_dmesg: bool = False
```

---

### P1-4: Correlation Display on Diagnose Tab

**File:** `dashboard.jsx` — in `<Diagnose />` component.

**Add after KB matches section:**
```jsx
{out?.correlations && (
  <>
    <h4>correlated metrics</h4>
    <table style={{ fontSize: 11 }}>
      <thead><tr><th>Metric</th><th className="num">Baseline</th><th className="num">Incident</th><th className="num">Δ%</th></tr></thead>
      <tbody>
        {out.correlations.volume.slice(0, 8).map((c, i) => (
          <tr key={i}>
            <td>{c.metric}</td>
            <td className="num">{c.baseline_mean}</td>
            <td className="num">{c.incident_mean}</td>
            <td className="num" style={{ color: c.delta_pct > 50 ? "var(--err)" : "var(--fg)" }}>
              {c.delta_pct}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </>
)}
```

**Backend:** Include correlation in diagnose response. Edit `app/agent/diagnose.py` `diagnose()`:
```python
from app.analytics import correlate as cor
# Before return:
incident_ts = int(time.time())
correlations = {
    "volume": cor.correlate(incident_ts, ctx["window_s"]),
    # pairs omitted to keep response small
}
return {..., "correlations": correlations}
```

---

### P2-1: Flat njmon JSON

**File:** `app/api/apps.py` — modify `/api/apps/{name}/njmon` endpoint.

**Add query param:**
```python
@router.get("/{name}/njmon")
def app_njmon(
    name: str,
    window: str = Query("6h"),
    step: str = Query("1m"),
    format: str = Query("nested", regex="^(nested|flat)$"),
) -> dict[str, Any]:
    rows = app_rows(window)
    row = _pick_best(name, rows, "name") or _pick_best(name, rows, "label")
    if not row:
        raise HTTPException(404, f"unknown app: {name}")
    nested = _njmon_app_flow(row, window=window, step=step)
    if format == "nested":
        return nested
    # Flatten
    flat = _flatten_njmon(nested)
    return flat


def _flatten_njmon(obj: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in obj.items():
        key = f"{prefix}_{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten_njmon(v, key))
        elif isinstance(v, list):
            # Take latest value from history arrays
            if v and isinstance(v[-1], (int, float)):
                out[f"{key}_latest"] = v[-1]
            else:
                out[key] = v  # keep as-is if not numeric
        else:
            out[key] = v
    return out
```

---

### P2-2: Prometheus Scrape Endpoint

**New file:** `app/api/prometheus.py`

```python
"""Prometheus scrape endpoint.

Exposes all collected metrics in Prometheus text format:
    # HELP cpu_total CPU utilization percent
    # TYPE cpu_total gauge
    cpu_total{host="jetson"} 67.2
"""

import time
from fastapi import APIRouter, Response

from app.hub import hub
from app.host import detect

router = APIRouter(tags=["prometheus"])


def _escape_label(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


@router.get("/metrics", response_class=Response)
def prometheus_metrics() -> Response:
    host = detect().host
    lines = []

    sys_snap = hub.latest("system") or {}
    sys = sys_snap.get("data", {})

    def gauge(name: str, value: float, help_text: str, **labels):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        label_str = ",".join(f'{k}="{_escape_label(str(v))}"' for k, v in labels.items())
        if label_str:
            lines.append(f"{name}{{{label_str}}} {value}")
        else:
            lines.append(f"{name} {value}")

    if sys:
        gauge("sh_cpu_total_pct", sys.get("cpu", {}).get("total", 0), "CPU utilization %", host=host)
        gauge("sh_mem_used_bytes", sys.get("mem", {}).get("used", 0), "Memory used", host=host)
        gauge("sh_mem_total_bytes", sys.get("mem", {}).get("total", 0), "Memory total", host=host)
        gauge("sh_net_rx_bps", sys.get("net", {}).get("rx_bps", 0), "Network rx bps", host=host)
        gauge("sh_net_tx_bps", sys.get("net", {}).get("tx_bps", 0), "Network tx bps", host=host)
        for disk in sys.get("disks", []):
            gauge("sh_disk_pct", disk.get("pct", 0), "Disk usage %", host=host, mount=disk.get("mount", "?"))

    jetson_snap = hub.latest("jetson") or {}
    j = jetson_snap.get("data", {})
    if j:
        gauge("sh_gpu_load_pct", j.get("gpu_load", 0), "GPU utilization %", host=host)
        gauge("sh_soc_temp_c", j.get("soc_temp", 0), "SoC temperature C", host=host)
        gauge("sh_power_total_w", j.get("power_w", 0), "Total power W", host=host)
        gauge("sh_fan_pct", j.get("fan_pct", 0), "Fan percent", host=host)
        for sensor, temp in (j.get("temps") or {}).items():
            gauge("sh_temp_c", temp, "Temp sensor", host=host, sensor=sensor)
        for rail, w in (j.get("power_rails") or {}).items():
            gauge("sh_power_rail_w", w, "Power rail watts", host=host, rail=rail)

    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")
```

**Register in `main.py`:**
```python
from app.api import prometheus
app.include_router(prometheus.router)
```

**Verify:** `curl http://localhost:9999/metrics`

---

### P2-3: Alert Thresholds UI

**Design:**
- Gear icon on Overview tab → opens settings panel
- Fields: CPU warn/err %, Mem warn/err %, Temp warn/err °C, PSI warn/err
- Save to localStorage + POST to `/api/config/thresholds`
- Backend stores in `data/thresholds.json`, applied at score calculation

**New file:** `app/api/thresholds.py` (pattern similar to `config.py` apps endpoint)

**Dashboard:** Add small `<ThresholdSettings />` popover component on Overview.

---

### P2-4: RED Request Metrics

Only relevant if app is HTTP service. Skipped for now unless user requests.

**Later idea:** Hook into systemd journal looking for "200 OK"/"500 Error"/latency patterns in app logs.

---

### P3-1: Webhook/MQTT Alert Routing

**New file:** `app/alerts/router.py`

```python
import asyncio
import json
import logging
import time

import httpx
from app.config import settings

log = logging.getLogger(__name__)


class AlertRouter:
    def __init__(self):
        self._sent_cache = {}  # key → last_sent_ts (dedup)
        self._cooldown_s = 300  # 5 min

    async def send(self, severity: str, source: str, message: str, context: dict = None):
        key = f"{source}:{message[:80]}"
        now = time.time()
        last = self._sent_cache.get(key, 0)
        if now - last < self._cooldown_s:
            return  # dedup
        self._sent_cache[key] = now

        payload = {
            "ts": int(now),
            "severity": severity,
            "source": source,
            "message": message,
            "context": context or {},
            "host": settings.host or "jetson",
        }

        if settings.alert_webhook_url:
            try:
                async with httpx.AsyncClient(timeout=5) as c:
                    await c.post(settings.alert_webhook_url, json=payload)
            except Exception as e:
                log.warning(f"alert webhook failed: {e}")


router = AlertRouter()
```

**Config additions:**
```python
alert_webhook_url: str | None = None
alert_mqtt_url: str | None = None
alert_cooldown_s: int = 300
```

**Hook into** anomaly detector, scorer, and leak detector — call `router.send()` on trigger.

---

## File-Level Change Plan

Summary of what to modify for each priority level:

### P0 changes

| File | Type | Changes |
|------|------|---------|
| `app/collectors/psutil_collector.py` | modify | Add saturation metric sampling |
| `app/analytics/anomaly.py` | new | Anomaly detector class + task |
| `app/api/derived.py` | modify | Add `/api/anomalies` endpoint |
| `app/main.py` | modify | Start/stop anomaly detector in lifespan |
| `dashboard.jsx` | modify | Add `<HealthView />` component + "health" tab |
| `dashboard.css` | modify | Styles for Health tab layout |

### P1 changes

| File | Type | Changes |
|------|------|---------|
| `app/analytics/correlate.py` | new | Correlation engine |
| `app/api/derived.py` | modify | Add `/api/correlate` endpoint |
| `app/analytics/health/scorer.py` | modify | USE+RED weighted score |
| `app/agent/diagnose.py` | modify | Include correlation in response |
| `app/main.py` | modify | Conditionally wire DmesgCollector |
| `app/config.py` | modify | Add `enable_dmesg` flag |
| `dashboard.jsx` | modify | Add correlation table in Diagnose |

### P2 changes

| File | Type | Changes |
|------|------|---------|
| `app/api/apps.py` | modify | Add `format=flat` param to njmon |
| `app/api/prometheus.py` | new | `/metrics` endpoint |
| `app/main.py` | modify | Register prometheus router |
| `app/api/thresholds.py` | new | Threshold config CRUD |
| `app/config.py` | modify | Threshold defaults |
| `dashboard.jsx` | modify | Threshold settings popover |

### P3 changes

| File | Type | Changes |
|------|------|---------|
| `app/alerts/router.py` | new | Alert routing with dedup |
| `app/config.py` | modify | Webhook/MQTT config |
| `app/analytics/anomaly.py` | modify | Call router on anomaly |

---

## Testing Checklist

Per feature, minimum verification:

### P0-1 (Saturation)
- [ ] `curl /api/system/current` includes `cpu.load_1m`, `cpu.saturation_pct`
- [ ] PSI fields present on Linux ≥ 4.20 (check `/proc/pressure/memory` exists)
- [ ] Metrics persist in SQLite: `SELECT * FROM metrics WHERE field LIKE 'cpu.pressure%' LIMIT 5`

### P0-2 (Anomaly)
- [ ] `/api/anomalies` returns `{"current": []}` initially
- [ ] After 30+ samples, sudden spike triggers anomaly in response
- [ ] Anomaly cleared when metric returns to baseline

### P0-3 (Health Tab)
- [ ] New "health" tab appears in dashboard
- [ ] Shows score + drivers + utilization + saturation + errors cards
- [ ] Anomaly list populates when any metric anomalous
- [ ] Correlation section populates (once P1-1 done)

### P1-1 (Correlation)
- [ ] `curl /api/correlate?window=300` returns volume + pairs arrays
- [ ] Results ordered by magnitude
- [ ] Excludes constant/zero-variance metrics

### P1-2 (Weighted Score)
- [ ] Score reacts to saturation (load > cores) by -15
- [ ] Score reacts to anomalies by -5 per anomaly (max -20)
- [ ] Drivers list ordered by weight (most negative first)

### P1-3 (Dmesg)
- [ ] `SH_ENABLE_DMESG=1` enables collector
- [ ] `curl "/api/logs?service=kernel-thermal&limit=5"` returns entries
- [ ] Severity correctly categorized (CRIT for panic, WARN for throttle)

### P2-1 (Flat JSON)
- [ ] `/api/apps/myapp/njmon?format=flat` returns flat keys
- [ ] Values are single-level (no nesting)
- [ ] Compatible with Splunk/ELK ingestion format

### P2-2 (Prometheus)
- [ ] `curl /metrics` returns 200 with text/plain
- [ ] Contains HELP/TYPE headers
- [ ] Labels properly escaped
- [ ] Works with `prometheus-client` scrape

### P2-3 (Thresholds UI)
- [ ] Settings gear visible on Overview
- [ ] Changes persist to localStorage
- [ ] POST to `/api/config/thresholds` updates server
- [ ] Score recalculates with new thresholds

### P3-1 (Alerts)
- [ ] Webhook receives POST on anomaly
- [ ] Dedup prevents re-send within cooldown window
- [ ] Payload includes severity, source, message, context

---

## Future Ideas (P4+)

Not yet scoped, for later consideration:

1. **Fleet dashboard** — multi-host view, needs separate design (P3-3)
2. **Auto-tune thresholds** — use anomaly z-score history to suggest thresholds
3. **KB auto-refinement** — when diagnose runs and KB match fails, prompt LLM to write new KB entry
4. **GraphRAG upgrade** — move KB from flat FAISS to entity graph (per 2026 research)
5. **Latency p50/p95/p99** — needs request instrumentation (RED complete)
6. **Alerting silence windows** — maintenance mode to suppress alerts
7. **SLA tracking** — uptime %, incident count per week
8. **Incident timeline** — reconstruct event sequence during incident
9. **Auto-remediation** — pre-approved action execution (restart service on crash)
10. **Edge-to-cloud sync** — stream metrics to remote aggregator for long-term storage

---

## Implementation Order (Recommended)

For step-by-step execution across multiple sessions:

**Session 1 (P0-1, P0-2):** ~3 hours
- Add saturation metrics
- Add anomaly detector
- Verify via API

**Session 2 (P0-3):** ~2 hours
- Build Health dashboard tab
- Wire saturation + anomaly display

**Session 3 (P1-1, P1-4):** ~4 hours
- Correlation engine
- Display in Diagnose tab

**Session 4 (P1-2, P1-3):** ~1.5 hours
- Weighted health score
- Enable dmesg collector

**Session 5 (P2-1, P2-2):** ~1.5 hours
- Flat njmon JSON
- Prometheus endpoint

**Session 6 (P2-3, P3-1):** ~4 hours
- Threshold settings UI
- Alert router

**Total est:** ~16 hours distributed across 6 focused sessions.

---

## Resume Instructions (for future sessions)

If this doc is being read in a new session:

1. **Check current status:** grep this file for `[x]` vs `[ ]` in testing checklists to see what's done
2. **Start from lowest unchecked priority** — always P0 before P1, P1 before P2
3. **Read the relevant Feature Spec** section for full implementation details
4. **Check referenced file paths exist** before editing (code may have shifted)
5. **Test each feature individually** before moving to next (use curl + dashboard)
6. **Update this roadmap** with `[x]` checkmarks as features complete

---

## Reference Links (for future research)

- [jetson-stats](https://github.com/rbonghi/jetson_stats)
- [jetson-stats Grafana reference](https://github.com/svcavallar/jetson-stats-grafana-dashboard)
- [RED+USE Methods](https://betterstack.com/community/guides/monitoring/red-use-metrics/)
- [Netdata Correlations](https://learn.netdata.cloud/docs/machine-learning-and-anomaly-detection/metric-correlations)
- [Netdata ML Anomaly](https://learn.netdata.cloud/docs/netdata-ai/anomaly-detection)
- [njmon JSON](https://www.ibm.com/support/pages/nmon-json-plus-new-direct-json-monitor)
- [LLMLogAnalyzer paper](https://arxiv.org/html/2510.24031v1)
- [Karpathy LLM Wiki](https://levelup.gitconnected.com/beyond-rag-how-andrej-karpathys-llm-wiki-pattern-builds-knowledge-that-actually-compounds-31a08528665e)
- [Linux PSI docs](https://www.kernel.org/doc/html/latest/accounting/psi.html)
- [Prometheus text format](https://prometheus.io/docs/instrumenting/exposition_formats/)

---

**END OF ROADMAP**

Edit this file to track progress. Never delete — this is the durable design record.
