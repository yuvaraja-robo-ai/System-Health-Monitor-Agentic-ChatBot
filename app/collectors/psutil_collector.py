import asyncio
import os
import time
from typing import Any

import psutil

from app.collectors.base import Collector
from app.config import settings
from app.db import sqlite as sdb
from app.hub import hub


def _read_psi(kind: str) -> dict[str, float]:
    """Parse /proc/pressure/{kind}. Returns {'some_avg10', 'some_avg60', 'full_avg10'}.

    Linux 4.20+ feature. Returns empty dict on older kernels or error.
    """
    out: dict[str, float] = {}
    try:
        with open(f"/proc/pressure/{kind}", "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 2:
                    continue
                label = parts[0]
                kv = {}
                for p in parts[1:]:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        try:
                            kv[k] = float(v)
                        except ValueError:
                            pass
                for field in ("avg10", "avg60", "avg300"):
                    if field in kv:
                        out[f"{label}_{field}"] = kv[field]
    except (FileNotFoundError, PermissionError, OSError):
        pass
    return out


class PsutilCollector(Collector):
    name = "psutil"
    interval_s = settings.system_tick_s

    def __init__(self) -> None:
        super().__init__()
        self._prev_net = psutil.net_io_counters()
        self._prev_net_t = time.time()
        psutil.cpu_percent(percpu=False)
        psutil.cpu_percent(percpu=True)
        try:
            self._prev_ctx = psutil.cpu_stats().ctx_switches
            self._prev_intr = psutil.cpu_stats().interrupts
        except (AttributeError, OSError):
            self._prev_ctx = 0
            self._prev_intr = 0
        self._prev_sat_t = time.time()
        self._cpu_count = os.cpu_count() or 1

    async def tick(self) -> None:
        snap = await asyncio.to_thread(self._snapshot)
        hub.publish("system", snap)
        await asyncio.to_thread(self._persist, snap)

    def _snapshot(self) -> dict[str, Any]:
        ts = int(time.time())
        cpu_total = psutil.cpu_percent(interval=None)
        cpu_per = psutil.cpu_percent(interval=None, percpu=True)
        try:
            load1, load5, load15 = psutil.getloadavg()
        except (OSError, AttributeError):
            load1 = load5 = load15 = 0.0
        vm = psutil.virtual_memory()
        sm = psutil.swap_memory()
        disks = []
        for p in psutil.disk_partitions(all=False):
            if p.fstype in ("", "squashfs", "tmpfs"):
                continue
            try:
                u = psutil.disk_usage(p.mountpoint)
                disks.append(
                    {
                        "device": p.device,
                        "mount": p.mountpoint,
                        "pct": u.percent,
                        "used": u.used,
                        "total": u.total,
                    }
                )
            except OSError:
                continue
        net = psutil.net_io_counters()
        now = time.time()
        dt = max(0.001, now - self._prev_net_t)
        rx = (net.bytes_recv - self._prev_net.bytes_recv) / dt
        tx = (net.bytes_sent - self._prev_net.bytes_sent) / dt
        self._prev_net = net
        self._prev_net_t = now
        try:
            io = psutil.cpu_times_percent(interval=None)
            iowait = getattr(io, "iowait", 0.0)
        except Exception:
            iowait = 0.0
        temps: dict[str, float] = {}
        try:
            raw = psutil.sensors_temperatures() or {}
        except (OSError, AttributeError, TypeError):
            raw = {}
        for name, arr in raw.items():
            try:
                for e in arr:
                    cur = getattr(e, "current", None)
                    if cur is None:
                        continue
                    try:
                        temps[f"{name}.{e.label or 'cur'}"] = float(cur)
                    except (TypeError, ValueError):
                        continue
            except (TypeError, ValueError):
                continue
        boot = psutil.boot_time()

        # Saturation (USE method)
        pressure = {
            "cpu": _read_psi("cpu"),
            "memory": _read_psi("memory"),
            "io": _read_psi("io"),
        }
        saturation_pct = 100.0 * load1 / self._cpu_count if self._cpu_count else 0.0

        # Context-switch rate
        try:
            cur_ctx = psutil.cpu_stats().ctx_switches
            cur_intr = psutil.cpu_stats().interrupts
        except (AttributeError, OSError):
            cur_ctx = self._prev_ctx
            cur_intr = self._prev_intr
        now = time.time()
        dt_sat = max(0.001, now - self._prev_sat_t)
        ctx_rate = max(0.0, (cur_ctx - self._prev_ctx) / dt_sat)
        intr_rate = max(0.0, (cur_intr - self._prev_intr) / dt_sat)
        self._prev_ctx = cur_ctx
        self._prev_intr = cur_intr
        self._prev_sat_t = now

        return {
            "ts": ts,
            "cpu": {
                "total": cpu_total,
                "per_core": cpu_per,
                "load": [load1, load5, load15],
                "cores": self._cpu_count,
                "saturation_pct": round(saturation_pct, 2),
                "ctx_switch_rate": round(ctx_rate, 1),
                "intr_rate": round(intr_rate, 1),
            },
            "mem": {
                "total": vm.total,
                "used": vm.used,
                "available": vm.available,
                "cached": getattr(vm, "cached", 0),
                "buffers": getattr(vm, "buffers", 0),
                "swap_used": sm.used,
                "swap_total": sm.total,
            },
            "disks": disks,
            "net": {"rx_bps": rx, "tx_bps": tx},
            "io_wait": iowait,
            "temps": temps,
            "pressure": pressure,
            "uptime_s": int(time.time() - boot),
        }

    def _persist(self, s: dict[str, Any]) -> None:
        ts = s["ts"]
        rows: list[tuple[int, str, float]] = [
            (ts, "cpu.total", s["cpu"]["total"]),
            (ts, "cpu.load1", s["cpu"]["load"][0]),
            (ts, "cpu.load5", s["cpu"]["load"][1]),
            (ts, "cpu.load15", s["cpu"]["load"][2]),
            (ts, "cpu.saturation_pct", s["cpu"]["saturation_pct"]),
            (ts, "cpu.ctx_switch_rate", s["cpu"]["ctx_switch_rate"]),
            (ts, "cpu.intr_rate", s["cpu"]["intr_rate"]),
            (ts, "mem.used", s["mem"]["used"]),
            (ts, "mem.available", s["mem"]["available"]),
            (ts, "mem.swap_used", s["mem"]["swap_used"]),
            (ts, "net.rx", s["net"]["rx_bps"]),
            (ts, "net.tx", s["net"]["tx_bps"]),
            (ts, "io.wait", s["io_wait"]),
        ]
        for i, v in enumerate(s["cpu"]["per_core"]):
            rows.append((ts, f"cpu.c{i}", v))
        for d in s["disks"]:
            rows.append((ts, f"disk.{d['mount']}.pct", d["pct"]))
        for k, v in s["temps"].items():
            rows.append((ts, f"temp.{k}", v))
        for kind, fields in (s.get("pressure") or {}).items():
            for field_name, value in fields.items():
                rows.append((ts, f"pressure.{kind}.{field_name}", float(value)))
        sdb.write_metrics(rows)


class ProcessCollector(Collector):
    name = "processes"
    interval_s = settings.process_tick_s

    async def tick(self) -> None:
        rows, snap = await asyncio.to_thread(self._snapshot)
        hub.publish("processes", snap)
        await asyncio.to_thread(sdb.write_procs, rows)

    def _snapshot(self) -> tuple[list[tuple[int, int, str, int, float, int]], dict[str, Any]]:
        ts = int(time.time())
        procs = []
        rows = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "num_threads", "status", "create_time"]):
            try:
                info = p.info
                rss = int(info["memory_info"].rss) if info.get("memory_info") else 0
                cpu = float(info.get("cpu_percent") or 0.0)
                name = info.get("name") or str(info["pid"])
                pid = int(info["pid"])
                threads = int(info.get("num_threads") or 0)
                time_plus = int(ts - (info.get("create_time") or ts))
                procs.append(
                    {
                        "pid": pid,
                        "name": name,
                        "cpu": cpu,
                        "rss": rss,
                        "threads": threads,
                        "time_plus": time_plus,
                        "status": info.get("status"),
                    }
                )
                rows.append((ts, pid, name, rss, cpu, threads))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: x["rss"], reverse=True)
        return rows, {"ts": ts, "procs": procs[:200]}
