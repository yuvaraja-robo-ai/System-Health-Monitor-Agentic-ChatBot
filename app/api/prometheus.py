"""Prometheus text exposition endpoint.

Exposes all collected metrics in Prometheus v0.0.4 text format so existing
fleet monitoring (Prometheus server) can scrape the Jetson device.

Format reference:
  https://prometheus.io/docs/instrumenting/exposition_formats/

Reachable at: GET /metrics
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from starlette.responses import Response

from app.analytics.anomaly import detector as anomaly_detector
from app.analytics.health import scorer
from app.analytics.leak import detector as leak_detector
from app.host import detect
from app.hub import hub

router = APIRouter(tags=["prometheus"])


def _escape_label_value(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _sanitize_metric_name(name: str) -> str:
    """Prometheus metric names must match [a-zA-Z_:][a-zA-Z0-9_:]*."""
    out = []
    for i, ch in enumerate(name):
        if ch.isalnum() or ch == "_" or ch == ":":
            out.append(ch)
        elif ch in (".", "-", "/"):
            out.append("_")
        else:
            out.append("_")
    result = "".join(out)
    if not result or not (result[0].isalpha() or result[0] == "_"):
        result = "_" + result
    return result


class _Emitter:
    def __init__(self, host: str) -> None:
        self.host = host
        self.lines: list[str] = []
        self._declared: set[str] = set()

    def gauge(self, name: str, value: Any, help_text: str, **labels) -> None:
        if value is None:
            return
        try:
            val = float(value)
        except (TypeError, ValueError):
            return
        full_name = f"sh_{_sanitize_metric_name(name)}"
        if full_name not in self._declared:
            self.lines.append(f"# HELP {full_name} {help_text}")
            self.lines.append(f"# TYPE {full_name} gauge")
            self._declared.add(full_name)
        all_labels = {"host": self.host, **labels}
        label_str = ",".join(
            f'{k}="{_escape_label_value(str(v))}"'
            for k, v in all_labels.items()
            if v is not None
        )
        if label_str:
            self.lines.append(f"{full_name}{{{label_str}}} {val}")
        else:
            self.lines.append(f"{full_name} {val}")

    def counter(self, name: str, value: Any, help_text: str, **labels) -> None:
        if value is None:
            return
        try:
            val = float(value)
        except (TypeError, ValueError):
            return
        full_name = f"sh_{_sanitize_metric_name(name)}"
        if full_name not in self._declared:
            self.lines.append(f"# HELP {full_name} {help_text}")
            self.lines.append(f"# TYPE {full_name} counter")
            self._declared.add(full_name)
        all_labels = {"host": self.host, **labels}
        label_str = ",".join(
            f'{k}="{_escape_label_value(str(v))}"'
            for k, v in all_labels.items()
            if v is not None
        )
        if label_str:
            self.lines.append(f"{full_name}{{{label_str}}} {val}")
        else:
            self.lines.append(f"{full_name} {val}")

    def render(self) -> str:
        return "\n".join(self.lines) + "\n"


@router.get("/metrics")
def prometheus_metrics() -> Response:
    cap = detect()
    e = _Emitter(host=cap.host or "unknown")

    sys_snap = hub.latest("system") or {}
    sys = sys_snap.get("data", {}) or {}

    cpu = sys.get("cpu", {}) or {}
    mem = sys.get("mem", {}) or {}
    net = sys.get("net", {}) or {}
    pressure = sys.get("pressure", {}) or {}

    e.gauge("cpu_total_pct", cpu.get("total"), "CPU utilization percent")
    e.gauge("cpu_saturation_pct", cpu.get("saturation_pct"), "CPU saturation percent (load/cores)")
    e.gauge("cpu_ctx_switch_rate", cpu.get("ctx_switch_rate"), "Context switches per second")
    e.gauge("cpu_intr_rate", cpu.get("intr_rate"), "Interrupts per second")
    for i, v in enumerate(cpu.get("per_core") or []):
        e.gauge("cpu_core_pct", v, "Per-core CPU percent", core=str(i))
    load = cpu.get("load") or []
    if len(load) >= 3:
        e.gauge("cpu_load_1m", load[0], "Load average 1 minute")
        e.gauge("cpu_load_5m", load[1], "Load average 5 minutes")
        e.gauge("cpu_load_15m", load[2], "Load average 15 minutes")

    e.gauge("mem_total_bytes", mem.get("total"), "Memory total bytes")
    e.gauge("mem_used_bytes", mem.get("used"), "Memory used bytes")
    e.gauge("mem_available_bytes", mem.get("available"), "Memory available bytes")
    e.gauge("mem_swap_used_bytes", mem.get("swap_used"), "Swap used bytes")
    e.gauge("mem_swap_total_bytes", mem.get("swap_total"), "Swap total bytes")

    e.gauge("net_rx_bps", net.get("rx_bps"), "Network receive bps")
    e.gauge("net_tx_bps", net.get("tx_bps"), "Network transmit bps")

    e.gauge("io_wait_pct", sys.get("io_wait"), "IO wait percent")

    for kind, fields in pressure.items():
        if not isinstance(fields, dict):
            continue
        for field_name, value in fields.items():
            e.gauge(
                "pressure",
                value,
                "Linux PSI pressure stall information",
                kind=kind,
                field=field_name,
            )

    for disk in sys.get("disks", []) or []:
        mount = disk.get("mount") or "?"
        e.gauge("disk_pct", disk.get("pct"), "Disk percent full", mount=mount)
        e.gauge("disk_used_bytes", disk.get("used"), "Disk used bytes", mount=mount)
        e.gauge("disk_total_bytes", disk.get("total"), "Disk total bytes", mount=mount)

    for sensor, temp in (sys.get("temps") or {}).items():
        e.gauge("host_temp_c", temp, "Host temp sensor Celsius", sensor=sensor)

    e.gauge("uptime_seconds", sys.get("uptime_s"), "Host uptime seconds")

    # Jetson-specific
    jetson_snap = hub.latest("jetson") or {}
    j = jetson_snap.get("data") or {}
    if j:
        e.gauge("gpu_load_pct", j.get("gpu_load"), "GPU utilization percent")
        e.gauge("gpu_ram_used_bytes", j.get("gpu_ram_used"), "GPU VRAM used bytes")
        e.gauge("gpu_ram_total_bytes", j.get("gpu_ram_total"), "GPU VRAM total bytes")
        e.gauge("soc_temp_c", j.get("soc_temp"), "SoC temperature Celsius")
        e.gauge("power_total_w", j.get("power_w"), "Total system power watts")
        e.gauge("fan_pct", j.get("fan_pct"), "Fan speed percent")
        e.gauge("emc_load_pct", j.get("emc_load"), "EMC (external memory controller) percent")
        e.gauge("jetson_swap_used_bytes", j.get("swap_used"), "Jetson swap used bytes")
        e.gauge("jetson_swap_total_bytes", j.get("swap_total"), "Jetson swap total bytes")
        for sensor, temp in (j.get("temps") or {}).items():
            e.gauge("jetson_temp_c", temp, "Jetson temp sensor Celsius", sensor=sensor)
        for rail, w in (j.get("power_rails") or {}).items():
            e.gauge("jetson_power_rail_w", w, "Jetson power rail watts", rail=rail)
        for eng_name, pct in (j.get("engines") or {}).items():
            e.gauge("jetson_engine_pct", pct, "Jetson engine utilization", engine=eng_name)

    # Health score
    try:
        h = scorer.latest() or {}
        if "score" in h:
            e.gauge("health_score", h["score"], "Overall health score 0-100")
        for d in h.get("drivers", []) or []:
            factor = d.get("factor")
            weight = d.get("weight")
            if factor is not None and weight is not None:
                e.gauge("health_driver_weight", weight, "Health driver penalty weight", factor=factor)
    except Exception:
        pass

    # Leaks
    try:
        leaks_list = leak_detector.current() or []
        e.gauge("leaks_active_count", len([l for l in leaks_list if l.get("flagged")]), "Active memory leaks")
        for l in leaks_list:
            if l.get("flagged"):
                e.gauge(
                    "leak_slope_mb_min",
                    l.get("slope_mb_min"),
                    "Memory leak slope MB/min",
                    name=str(l.get("name") or "?"),
                    pid=str(l.get("pid") or "?"),
                )
    except Exception:
        pass

    # Anomalies
    try:
        cur = anomaly_detector.current()
        e.gauge("anomalies_active_count", len(cur), "Active anomalies count")
        for a in cur:
            e.gauge(
                "anomaly_z_score",
                a.get("z"),
                "Anomaly z-score",
                metric=a.get("metric") or "?",
            )
    except Exception:
        pass

    return Response(content=e.render(), media_type="text/plain; version=0.0.4; charset=utf-8")
