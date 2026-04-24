import asyncio
import logging
import time
from typing import Any

from app.collectors.base import Collector
from app.db import sqlite as sdb
from app.hub import hub
from app.host import detect

log = logging.getLogger(__name__)


class JtopCollector(Collector):
    """Jetson GPU/power/temp/fan via jetson-stats. Uses j.stats flat dict for
    resilience across jtop 4.x minor versions."""

    name = "jtop"
    interval_s = 1.0

    def __init__(self) -> None:
        super().__init__()
        self._jtop = None

    async def setup(self) -> None:
        if not detect().has_jtop:
            return
        from jtop import jtop
        j = jtop()
        j.start()
        self._jtop = j

    async def teardown(self) -> None:
        j = self._jtop
        self._jtop = None
        if j is None:
            return

        def _close():
            try:
                j.close()
            except Exception:
                pass

        try:
            await asyncio.wait_for(asyncio.to_thread(_close), timeout=2.0)
        except asyncio.TimeoutError:
            log.warning("jtop.close() timed out — leaving to daemon thread")

    async def tick(self) -> None:
        if self._jtop is None:
            return
        snap = await asyncio.to_thread(self._snapshot)
        if snap is None:
            return
        hub.publish("jetson", snap)
        await asyncio.to_thread(self._persist, snap)

    @staticmethod
    def _as_float(v: Any) -> float:
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict):
            for k in ("val", "value", "cur", "current", "power", "temp", "speed", "load", "online"):
                if k in v:
                    try:
                        return float(v[k])
                    except (TypeError, ValueError):
                        continue
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    def _snapshot(self) -> dict[str, Any] | None:
        j = self._jtop
        if j is None or not j.ok():
            return None
        stats = getattr(j, "stats", {}) or {}

        gpu_load = 0.0
        for k in ("GPU", "GPU1", "gpu"):
            if k in stats:
                gpu_load = self._as_float(stats[k]); break
        if gpu_load == 0.0:
            try:
                for v in (getattr(j, "gpu", {}) or {}).values():
                    gpu_load = self._as_float(v.get("load", v.get("status", {}).get("load", 0)) if isinstance(v, dict) else v)
                    if gpu_load:
                        break
            except (AttributeError, TypeError):
                pass

        mem_used = 0; mem_total = 0
        try:
            memory = getattr(j, "memory", None) or {}
            ram = memory.get("RAM") if isinstance(memory, dict) else None
            if isinstance(ram, dict):
                mem_used = int(ram.get("used", 0))
                mem_total = int(ram.get("tot", ram.get("total", 0)))
        except (AttributeError, TypeError):
            pass

        temps = {}
        try:
            t_map = getattr(j, "temperature", {}) or {}
            for name, val in t_map.items():
                temps[name] = self._as_float(val)
        except (AttributeError, TypeError):
            pass
        for k, v in stats.items():
            if isinstance(k, str) and k.lower().startswith("temp"):
                temps[k] = self._as_float(v)

        soc_temp = 0.0
        for k in ("SOC0", "SOC1", "SOC", "soc0", "soc1", "Temp SOC0", "Temp SOC1", "Temp CPU", "CPU", "tj", "Temp tj"):
            if k in temps and temps[k]:
                soc_temp = temps[k]; break
        if soc_temp == 0.0 and temps:
            soc_temp = max(temps.values())

        power_w = 0.0
        try:
            power = getattr(j, "power", {}) or {}
            tot = power.get("tot") if isinstance(power, dict) else None
            if isinstance(tot, dict):
                power_w = self._as_float(tot.get("power", tot.get("cur", 0))) / 1000.0
            elif tot is not None:
                power_w = self._as_float(tot) / 1000.0
        except (AttributeError, TypeError):
            pass
        for k in ("Power TOT", "Power tot", "power tot"):
            if k in stats:
                power_w = self._as_float(stats[k]) / 1000.0
                break

        fan_pct = 0.0
        try:
            fans = getattr(j, "fan", {}) or {}
            for v in (fans.values() if isinstance(fans, dict) else []):
                fan_pct = self._as_float(v.get("speed", v.get("pwm", 0)) if isinstance(v, dict) else v)
                if fan_pct:
                    break
        except (AttributeError, TypeError):
            pass
        for k, v in stats.items():
            if isinstance(k, str) and k.lower().startswith("fan"):
                fan_pct = self._as_float(v)
                break

        power_mode = ""
        for k in ("nvp_model", "NVP model", "NV Power Mode", "nvp model"):
            if k in stats:
                power_mode = str(stats[k]); break
        if not power_mode:
            try:
                nvp = getattr(j, "nvpmodel", None)
                if nvp is not None:
                    power_mode = str(nvp)
            except AttributeError:
                pass

        emc_load = 0.0
        for k in ("EMC", "emc", "Freq EMC", "EMC1", "EMC_FREQ"):
            if k in stats:
                emc_load = self._as_float(stats[k]); break

        engines: dict[str, float] = {}
        try:
            eng_map = getattr(j, "engines", None) or {}
            if isinstance(eng_map, dict):
                for eng_name, eng_val in eng_map.items():
                    engines[str(eng_name)] = self._as_float(eng_val)
        except (AttributeError, TypeError):
            pass
        for k, v in stats.items():
            if isinstance(k, str) and any(k.upper().startswith(p) for p in ("VIC", "NVENC", "NVDEC", "DLA", "APE")):
                engines.setdefault(k, self._as_float(v))

        swap_used = 0; swap_total = 0
        try:
            memory = getattr(j, "memory", None) or {}
            swap = memory.get("SWAP") if isinstance(memory, dict) else None
            if isinstance(swap, dict):
                swap_used = int(swap.get("used", 0))
                swap_total = int(swap.get("tot", swap.get("total", 0)))
        except (AttributeError, TypeError):
            pass

        power_rails: dict[str, float] = {}
        try:
            power = getattr(j, "power", {}) or {}
            if isinstance(power, dict):
                for rail_name, rail_val in power.items():
                    if rail_name == "tot":
                        continue
                    if isinstance(rail_val, dict):
                        w = self._as_float(rail_val.get("power", rail_val.get("cur", 0))) / 1000.0
                    else:
                        w = self._as_float(rail_val) / 1000.0
                    if w > 0:
                        power_rails[str(rail_name)] = round(w, 3)
        except (AttributeError, TypeError):
            pass

        return {
            "ts": int(time.time()),
            "gpu_load": gpu_load,
            "gpu_ram_used": mem_used,
            "gpu_ram_total": mem_total,
            "soc_temp": soc_temp,
            "power_w": power_w,
            "fan_pct": fan_pct,
            "power_mode": power_mode,
            "temps": temps,
            "emc_load": emc_load,
            "engines": engines,
            "swap_used": swap_used,
            "swap_total": swap_total,
            "power_rails": power_rails,
        }

    def _persist(self, s: dict[str, Any]) -> None:
        ts = s["ts"]
        rows = [
            (ts, "gpu.load", s["gpu_load"]),
            (ts, "gpu.ram_used", float(s["gpu_ram_used"])),
            (ts, "soc.temp", s["soc_temp"]),
            (ts, "power.total_w", s["power_w"]),
            (ts, "fan.pct", s["fan_pct"]),
        ]
        for k, v in (s.get("temps") or {}).items():
            rows.append((ts, f"jetson.temp.{k}", float(v)))
        if s.get("emc_load"):
            rows.append((ts, "emc.load", float(s["emc_load"])))
        if s.get("swap_total"):
            rows.extend([
                (ts, "swap.used", float(s["swap_used"])),
                (ts, "swap.total", float(s["swap_total"])),
            ])
        for eng, pct in (s.get("engines") or {}).items():
            rows.append((ts, f"jetson.engine.{eng}", float(pct)))
        for rail, w in (s.get("power_rails") or {}).items():
            rows.append((ts, f"jetson.power.{rail}", float(w)))
        sdb.write_metrics(rows)
