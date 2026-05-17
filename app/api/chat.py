"""Agent chat endpoint.

Answer priority (no LLM required for first two):
  1. Direct metric answer — live hub data, instant, zero deps
  2. KB search answer  — runbook steps from local markdown files
  3. LLM answer        — reasoning, only if SH_OLLAMA_URL / SH_LLAMA_URL set

POST /api/chat
  {"messages": [{"role": "user", "content": "what is the CPU usage?"}],
   "scope": {"window": "5m"}}
→ {"answer": "...", "backend": "direct|kb|ollama|none", "latency_ms": 123}
"""

from __future__ import annotations

import json
import inspect
import asyncio
import re
import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.agent import kb, llm
from app.agent import keywords as kw_cfg
from app.agent.diagnose import collect_context_async, _digest_text
from app.db import duckdb as ldb
from app.hub import hub

router = APIRouter(prefix="/api", tags=["chat"])

_SYSTEM_PROMPT = (
    "You are an embedded ops assistant on a Linux/Jetson device. "
    "Live system context is already injected. Be concise, name specific processes/services. "
    "No markdown headers. Max 6 lines."
)

_AGENT_CONTEXT_ACK = "Understood. I have the live system context. I will use tools for specific queries."

_AGENT_SYSTEM_PROMPT = """You are an embedded ops agent for Linux/Jetson system monitoring.

You can inspect current system state with tools before answering.

Available tools:
1. get_direct_answer(question: str)
   Returns a direct live-metric answer for CPU, memory, disk, GPU, health, processes, crashes, leaks, anomalies, and related metrics.
2. get_live_context(window: str | optional, services: list[str] | optional, pids: list[int] | optional)
   Returns a compact live diagnostic digest for the selected scope.
3. search_kb(query: str, window: str | optional, services: list[str] | optional, pids: list[int] | optional)
   Returns the most relevant local KB/runbook matches and steps.
4. get_log_status(window: str | optional, level: str | optional, service: str | optional, regex: str | optional)
   Returns whether logs are actually present in storage, plus recent counts and examples.
5. get_log_clusters(window: str | optional, limit: int | optional)
   Returns grouped repeated error signatures from stored logs.

Respond in exactly one JSON object:
- Tool use: {"tool_name":"...", "tool_arguments": {...}}
- Final answer: {"answer":"..."}

Rules:
- Return JSON only. No markdown fences.
- Use tools for live metrics, diagnostics, and runbook steps. Do not invent data.
- You may call multiple tools across turns.
- Keep the final answer concise and actionable, max 6 lines.
"""


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _fmtb(b: float | None) -> str:
    if b is None:
        return "—"
    for unit, thresh in [("GB", 1e9), ("MB", 1e6), ("KB", 1e3)]:
        if b >= thresh:
            return f"{b/thresh:.1f}{unit}"
    return f"{b:.0f}B"


def _fmts(s: float | None) -> str:
    if s is None:
        return "—"
    s = int(s)
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


def _kw(q: str, *words: str) -> bool:
    q = q.lower()
    return any(re.search(r'\b' + re.escape(w) + r'\b', q) for w in words)


def _kw_metric(q: str, metric: str) -> bool:
    """Match query against a named keyword group from keywords.json."""
    kws = kw_cfg.metric_keywords(metric)
    excl = kw_cfg.metric_exclude(metric)
    return bool(kws) and _kw(q, *kws) and (not excl or not _kw(q, *excl))


def _wants_process_list(q: str) -> bool:
    """Detect questions asking which apps/processes are using a resource.

    This must be broader than the plain "process" metric keyword because users
    often ask for "apps consuming CPU" without saying "process".
    """
    if (
        _kw_metric(q, "leak")
        or _kw_metric(q, "crash")
        or _kw_metric(q, "anomaly")
        or _kw_metric(q, "logs")
        or _kw_metric(q, "timeline")
        or _kw_metric(q, "sla")
        or _kw_metric(q, "services")
        or _kw_metric(q, "summary")
    ):
        return False

    target = _kw(
        q,
        "process", "processes", "pid",
        "application", "applications", "app", "apps",
        "service", "services",
    )
    asks_for_ranked_items = _kw(
        q,
        "top", "list", "show", "which", "what", "who", "each",
        "consuming", "using", "eating", "highest", "most", "more",
        "biggest", "largest", "check",
    )
    resource_metric = (
        _kw_metric(q, "cpu")
        or _kw_metric(q, "memory")
        or _kw(q, "usage", "utilization", "resource", "resources")
    )
    return target and (asks_for_ranked_items or resource_metric)


def _process_list_answer(q: str, procs: list[dict[str, Any]]) -> str:
    if not procs:
        return "No process data available."

    by_mem = _kw_metric(q, "memory") and not _kw_metric(q, "cpu")
    sort_key = (lambda p: p.get("rss", 0)) if by_mem else (lambda p: p.get("cpu", 0))
    label = "memory (RSS)" if by_mem else "CPU"
    top = sorted(procs, key=sort_key, reverse=True)[:8]
    lines = [
        f"{p['name']} (pid {p['pid']}): cpu {p.get('cpu',0):.1f}%  mem {_fmtb(p.get('rss',0))}"
        for p in top
    ]
    return f"Top processes by {label}:\n" + "\n".join(lines)


def _jetson_gpu_power_answer(q: str, jetson: dict[str, Any]) -> str:
    if not jetson:
        return "No GPU/power data (Jetson not detected or jtop not running)."

    wants_gpu = _kw_metric(q, "gpu")
    wants_power = _kw_metric(q, "power")
    wants_process_attribution = _kw(q, "process", "processes", "application", "applications", "app", "apps", "pid")
    parts = []

    if wants_process_attribution and wants_gpu:
        parts.append("Per-process GPU attribution is not available from the current Jetson collector.")

    if wants_gpu:
        load = jetson.get("gpu_load")
        if load is not None:
            parts.append(f"GPU load: {load:.1f}%")
        ram_used = jetson.get("gpu_ram_used")
        ram_total = jetson.get("gpu_ram_total")
        if ram_used is not None:
            parts.append(f"GPU RAM: {_fmtb(ram_used)} / {_fmtb(ram_total or 0)}")
        for eng, pct in (jetson.get("engines") or {}).items():
            parts.append(f"{eng}: {pct:.0f}%")

    if wants_power:
        power_mode = jetson.get("power_mode")
        if power_mode:
            parts.append(f"Power mode: {power_mode}")
        pw = jetson.get("power_w")
        if pw is not None:
            parts.append(f"Total power: {pw:.1f}W")
        for rail, w in (jetson.get("power_rails") or {}).items():
            parts.append(f"  {rail}: {w:.2f}W")

    if parts:
        return "\n".join(parts)
    return "GPU/power data not available."


def _sanitize_scope(scope: dict[str, Any] | None) -> dict[str, Any]:
    scope = scope or {}
    out: dict[str, Any] = {}
    window = scope.get("window")
    if isinstance(window, str) and window.strip():
        out["window"] = window.strip()
    services = scope.get("services")
    if isinstance(services, list):
        out["services"] = [str(s) for s in services if str(s).strip()]
    pids = scope.get("pids")
    if isinstance(pids, list):
        cleaned: list[int] = []
        for pid in pids:
            try:
                cleaned.append(int(pid))
            except (TypeError, ValueError):
                continue
        out["pids"] = cleaned
    return out


def _merge_scope(base_scope: dict[str, Any] | None, overrides: dict[str, Any] | None) -> dict[str, Any]:
    merged = _sanitize_scope(base_scope)
    extra = _sanitize_scope(overrides)
    for key in ("window", "services", "pids"):
        if key in extra:
            merged[key] = extra[key]
    return merged


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines:
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    text = "\n".join(lines).strip()
    if text.lower().startswith("json"):
        text = text[4:].strip()
    return text


def _parse_agent_response(text: str) -> dict[str, Any]:
    text = _strip_code_fences(text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"Could not parse agent response: {text[:200]}")


def _normalize_tool_arguments(parsed: dict[str, Any], tool_name: str, tools: dict[str, Any]) -> dict[str, Any]:
    candidate_keys = (
        "tool_arguments",
        "tool_args",
        "arguments",
        "args",
        "parameters",
        "params",
        "input",
        "inputs",
    )

    raw = None
    for key in candidate_keys:
        if key in parsed:
            raw = parsed[key]
            break

    if raw is None:
        extras = {k: v for k, v in parsed.items() if k not in {"tool_name", "answer", "name"}}
        if extras:
            raw = extras

    if isinstance(raw, dict):
        return raw

    tool = tools.get(tool_name)
    if raw is not None and tool:
        params = [p for p in inspect.signature(tool).parameters if p != "self"]
        if len(params) == 1:
            return {params[0]: raw}

    return {}


def _window_to_seconds(window: str | None) -> int:
    from app.utils.service import parse_window

    if not window:
        return int(time.time()) - 900
    try:
        fallback = int(window)
    except (TypeError, ValueError):
        fallback = 900
    try:
        return int(time.time()) - parse_window(window, default=fallback)
    except (TypeError, ValueError):
        return int(time.time()) - 900


def _log_status(window: str = "15m", level: str | None = None, service: str | None = None, regex: str | None = None) -> str:
    since_s = _window_to_seconds(window)
    rows = ldb.query_logs(level=level, service=service, regex=regex, since_s=since_s, limit=20)
    clusters = ldb.cluster_logs(since_s, limit=5)
    if not rows:
        return (
            f"Logs available check: no stored log rows found for window {window}."
            + (f" service={service}." if service else "")
            + (f" level={level}." if level else "")
            + " API is reachable but ingestion may be empty, filters may be too narrow, or the source is inactive."
        )

    services = sorted({r.get("service") for r in rows if r.get("service")})
    levels: dict[str, int] = {}
    for row in rows:
        lvl = str(row.get("level") or "INFO").upper()
        levels[lvl] = levels.get(lvl, 0) + 1

    lines = [
        f"Logs available check: {len(rows)} stored row(s) found in {window}.",
        "Levels: " + ", ".join(f"{k}={v}" for k, v in sorted(levels.items())),
    ]
    if services:
        lines.append("Services: " + ", ".join(services[:5]))
    if clusters:
        top = clusters[0]
        lines.append(
            f"Top cluster: {top.get('service') or '—'} {top.get('level') or 'LOG'} x{top.get('count', 0)}"
        )
    sample = rows[0]
    lines.append(f"Latest sample: [{sample.get('level')}] {sample.get('service') or '—'} {sample.get('message')}")
    return "\n".join(lines)


def _log_clusters(window: str = "15m", limit: int = 10) -> str:
    rows = ldb.cluster_logs(_window_to_seconds(window), limit=limit)
    if not rows:
        return f"No log clusters found for window {window}."
    lines = [f"{len(rows)} log cluster(s) in {window}:"]
    for row in rows[:limit]:
        lines.append(
            f"{row.get('service') or '—'} {row.get('level') or 'LOG'} x{row.get('count', 0)}: {row.get('sample')}"
        )
    return "\n".join(lines)


def _wants_recent_log_errors(q: str) -> bool:
    return _kw(q, "error", "errors", "err", "fatal", "critical", "crit", "warning", "warnings", "warn")


def _extract_window(q: str, default: str = "15m") -> str:
    match = re.search(r"\b(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\b", q)
    if not match:
        if _kw(q, "today", "24h", "day"):
            return "24h"
        if _kw(q, "week", "7d"):
            return "7d"
        return default
    value = match.group(1)
    unit = match.group(2)
    suffix = "s"
    if unit.startswith("m"):
        suffix = "m"
    elif unit.startswith("h"):
        suffix = "h"
    elif unit.startswith("d"):
        suffix = "d"
    return f"{value}{suffix}"


def _system_summary_answer(sys: dict[str, Any], jetson: dict[str, Any], health_data: dict[str, Any]) -> str:
    parts = []
    score = health_data.get("score")
    if score is not None:
        label = "healthy" if score >= 80 else ("degraded" if score >= 60 else "critical")
        parts.append(f"Health score: {score}/100 ({label})")

    cpu = sys.get("cpu") or {}
    total = cpu.get("total")
    if total is not None:
        load = cpu.get("load") or []
        load_txt = f" load {load[0]:.2f}" if load else ""
        parts.append(f"CPU: {total:.1f}%{load_txt}")

    mem = sys.get("mem") or {}
    used = mem.get("used")
    total_mem = mem.get("total")
    if used is not None and total_mem:
        parts.append(f"RAM: {_fmtb(used)} / {_fmtb(total_mem)} ({100 * used / total_mem:.1f}%)")

    disks = sys.get("disks") or []
    if disks:
        hottest_disk = max(disks, key=lambda d: float(d.get("pct") or 0))
        parts.append(f"Disk {hottest_disk.get('mount','?')}: {hottest_disk.get('pct','?')}% used")

    net = sys.get("net") or {}
    if net.get("rx_bps") is not None or net.get("tx_bps") is not None:
        parts.append(f"Network: RX {_fmtb(net.get('rx_bps'))}/s TX {_fmtb(net.get('tx_bps'))}/s")

    if jetson:
        gpu = jetson.get("gpu_load")
        power = jetson.get("power_w")
        gpu_part = f"GPU {gpu:.1f}%" if gpu is not None else "GPU n/a"
        power_part = f"power {power:.1f}W" if power is not None else "power n/a"
        parts.append(f"Jetson: {gpu_part}, {power_part}")

    drivers = health_data.get("drivers") or []
    if drivers:
        parts.append("Top issues: " + ", ".join(f"{d.get('factor')}({d.get('weight')})" for d in drivers[:3]))

    return "\n".join(parts) if parts else "No live system summary available yet."


def _timeline_answer(window: str = "1h") -> str:
    from app.api.timeline import timeline
    from app.utils.service import parse_window

    try:
        data = timeline(window=parse_window(window, default=3600), limit=8)
    except Exception as e:
        return f"Timeline unavailable: {e}"
    events = data.get("events") or []
    if not events:
        return f"No incidents/events found in {window}."
    lines = [f"{len(events)} recent incident/event(s) in {window}:"]
    for event in events[:8]:
        lines.append(f"{event.get('kind')} {event.get('source')}: {event.get('message')}")
    return "\n".join(lines)


def _sla_answer(window: str = "7d") -> str:
    from app.api.sla import sla

    try:
        data = sla(window=window)
    except Exception as e:
        return f"SLA unavailable: {e}"
    if data.get("samples", 0) == 0 or data.get("uptime_pct") is None:
        return f"SLA: no health-score history available for {window}."
    mttr = _fmts(data.get("mttr_s")) if data.get("mttr_s") is not None else "n/a"
    return (
        f"SLA {window}: uptime {data.get('uptime_pct')}%, "
        f"downtime {_fmts(data.get('downtime_s'))}, "
        f"incidents {data.get('incident_count')}, MTTR {mttr}"
    )


def _services_answer(window: str = "24h") -> str:
    from app.api.derived import units

    try:
        rows = units(window=window, limit=8)
    except Exception as e:
        return f"Service status unavailable: {e}"
    if not rows:
        return "No service/unit status data available."
    bad = [r for r in rows if r.get("status") in {"err", "warn"}]
    selected = bad or rows[:5]
    lines = [f"{len(bad)} service(s) need attention in {window}:" if bad else "Top services are OK:"]
    for row in selected[:8]:
        lines.append(
            f"{row.get('name')}: {row.get('status')} {row.get('active_state')}/{row.get('sub_state')} "
            f"errors={row.get('errors', 0)} warns={row.get('warns', 0)} crashes={row.get('crashes', 0)}"
        )
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Layer 1: direct live-data answers
# ──────────────────────────────────────────────────────────────

def _direct_answer(question: str) -> str | None:
    q = question.lower().strip()
    sys = (hub.latest("system") or {}).get("data") or {}
    jetson = (hub.latest("jetson") or {}).get("data") or {}
    health_data = (hub.latest("health") or {}) or {}
    # health may be published as plain dict (not wrapped in "data")
    if "score" not in health_data:
        health_data = health_data.get("data") or health_data

    cpu = sys.get("cpu") or {}
    mem = sys.get("mem") or {}
    net = sys.get("net") or {}
    disks = sys.get("disks") or []
    temps = sys.get("temps") or {}
    pressure = sys.get("pressure") or {}

    # ── Named process / service query (must run before generic CPU/mem blocks) ──
    # If a running process name appears verbatim in the question, answer for that process only.
    procs_snap = (hub.latest("processes") or {}).get("data", {}).get("procs") or []
    if procs_snap and not _kw(q, *kw_cfg.process_scope_keywords()):
        matched = [p for p in procs_snap if p.get("name") and p["name"].lower() in q]
        is_reasoning = any(w in q for w in kw_cfg.reasoning_keywords())
        if matched and _kw(q, *kw_cfg.process_metric_keywords()) and not is_reasoning:
            lines = [
                f"{p['name']} (pid {p['pid']}): cpu {p.get('cpu', 0):.1f}%  mem {_fmtb(p.get('rss', 0))}"
                for p in matched[:5]
            ]
            return "\n".join(lines)

    # ── Jetson GPU/power query ──
    # Keep this before process-list routing so "GPU process using and power"
    # does not get treated as a generic CPU process request.
    if _kw_metric(q, "gpu") or _kw_metric(q, "power"):
        return _jetson_gpu_power_answer(q, jetson)

    # ── Incident timeline / SLA ──
    if _kw_metric(q, "timeline"):
        return _timeline_answer(_extract_window(q, default="1h"))

    if _kw_metric(q, "sla") and not _kw_metric(q, "logs"):
        return _sla_answer(_extract_window(q, default="7d"))

    if _kw_metric(q, "services"):
        return _services_answer(_extract_window(q, default="24h"))

    # ── Logs / recent errors ──
    # Keep this before process-list routing so "errors from applications" is
    # treated as log intent, not as a generic "applications" process query.
    if _kw_metric(q, "logs"):
        window = _extract_window(q, default="15m")
        if _kw_metric(q, "log_availability"):
            return _log_status(window=window)
        if _wants_recent_log_errors(q):
            return _log_clusters(window=window)
        return _log_status(window=window)

    # ── System summary / overview ──
    specific_metric = any(
        _kw_metric(q, metric)
        for metric in (
            "cpu", "memory", "swap", "disk", "temperature", "network",
            "uptime", "pressure", "io_wait", "anomaly", "leak", "crash",
            "process", "load_average", "emc",
        )
    )
    if _kw_metric(q, "summary") and not specific_metric:
        return _system_summary_answer(sys, jetson, health_data)

    # ── Ranked app/process resource query ──
    # Run this before generic CPU/RAM summaries so "apps consuming CPU" returns
    # the process list instead of repeating the total CPU snapshot.
    if _wants_process_list(q):
        return _process_list_answer(q, procs_snap)

    # ── CPU ──
    if _kw_metric(q, "cpu"):
        parts = []
        total = cpu.get("total")
        if total is not None:
            parts.append(f"CPU: {total:.1f}%")
        load = cpu.get("load") or []
        if load:
            parts.append(f"load avg {' / '.join(f'{v:.2f}' for v in load[:3])}")
        cores = cpu.get("cores")
        if cores:
            parts.append(f"{cores} cores")
        sat = cpu.get("saturation_pct")
        if sat is not None:
            parts.append(f"saturation {sat:.0f}%")
        per_core = cpu.get("per_core") or []
        if per_core:
            core_str = "  ".join(f"c{i}:{v:.0f}%" for i, v in enumerate(per_core))
            parts.append(f"per-core: {core_str}")
        ctx_rate = cpu.get("ctx_switch_rate")
        if ctx_rate:
            parts.append(f"ctx-switches {ctx_rate:.0f}/s")
        intr_rate = cpu.get("intr_rate")
        if intr_rate:
            parts.append(f"interrupts {intr_rate:.0f}/s")
        return "\n".join(parts) if parts else None

    # ── Applications consuming memory (RSS-sorted process list) ──
    if _kw_metric(q, "memory") and _kw_metric(q, "memory_consumers") and not _kw_metric(q, "leak"):
        return _process_list_answer(q, procs_snap)

    # ── Memory / RAM ──
    if _kw_metric(q, "memory") and not _kw_metric(q, "leak"):
        parts = []
        used = mem.get("used")
        total = mem.get("total")
        if used is not None and total:
            pct = 100 * used / total
            parts.append(f"RAM: {_fmtb(used)} / {_fmtb(total)} ({pct:.1f}%)")
        avail = mem.get("available")
        if avail is not None:
            parts.append(f"available: {_fmtb(avail)}")
        swap_used = mem.get("swap_used")
        swap_total = mem.get("swap_total")
        if swap_used is not None:
            parts.append(f"swap: {_fmtb(swap_used)} / {_fmtb(swap_total or 0)}")
        if jetson:
            j_swap = jetson.get("swap_used")
            j_swap_t = jetson.get("swap_total")
            if j_swap is not None:
                parts.append(f"Jetson swap: {_fmtb(j_swap)} / {_fmtb(j_swap_t or 0)}")
        psi_mem = (pressure.get("memory") or {}).get("some_avg10")
        if psi_mem is not None:
            parts.append(f"memory pressure PSI avg10: {psi_mem:.1f}%")
        return "\n".join(parts) if parts else None

    # ── Swap ──
    if _kw_metric(q, "swap"):
        parts = []
        swap_used = mem.get("swap_used")
        swap_total = mem.get("swap_total")
        if swap_used is not None:
            parts.append(f"Swap: {_fmtb(swap_used)} used / {_fmtb(swap_total or 0)} total")
        if jetson:
            j_swap = jetson.get("swap_used")
            j_swap_t = jetson.get("swap_total")
            if j_swap is not None:
                parts.append(f"Jetson swap: {_fmtb(j_swap)} / {_fmtb(j_swap_t or 0)}")
        return "\n".join(parts) if parts else "No swap data available."

    # ── Disk ──
    if _kw_metric(q, "disk"):
        if not disks:
            return "No disk data available."
        lines = []
        for d in disks:
            lines.append(
                f"{d.get('mount','?')}: {d.get('pct','?')}% used "
                f"({_fmtb(d.get('used'))} / {_fmtb(d.get('total'))})"
            )
        return "\n".join(lines)

    # ── Temperature ──
    if _kw_metric(q, "temperature"):
        parts = []
        if jetson:
            soc = jetson.get("soc_temp")
            if soc is not None:
                parts.append(f"SoC temp: {soc:.1f}°C")
            for sensor, val in (jetson.get("temps") or {}).items():
                parts.append(f"{sensor}: {val:.1f}°C")
        if temps:
            for sensor, val in temps.items():
                parts.append(f"{sensor}: {val:.1f}°C")
        if not parts:
            return "No temperature data available."
        hottest = max((v for v in list(temps.values()) + ([jetson.get("soc_temp")] if jetson else []) if v is not None), default=None)
        if hottest is not None:
            parts.insert(0, f"Hottest: {hottest:.1f}°C")
        return "\n".join(parts)

    # ── GPU ──
    if _kw_metric(q, "gpu"):
        return _jetson_gpu_power_answer(q, jetson)

    # ── Power ──
    if _kw_metric(q, "power"):
        return _jetson_gpu_power_answer(q, jetson)

    # ── Fan ──
    if _kw_metric(q, "fan"):
        if not jetson:
            return "No fan data (Jetson not detected)."
        fan = jetson.get("fan_pct")
        if fan is not None:
            return f"Fan speed: {fan:.1f}%"
        return "Fan data not available."

    # ── Network ──
    if _kw_metric(q, "network"):
        parts = []
        rx = net.get("rx_bps")
        tx = net.get("tx_bps")
        if rx is not None:
            parts.append(f"RX: {_fmtb(rx)}/s")
        if tx is not None:
            parts.append(f"TX: {_fmtb(tx)}/s")
        return "\n".join(parts) if parts else "No network data."

    # ── Uptime ──
    if _kw_metric(q, "uptime"):
        uptime = sys.get("uptime_s")
        return f"Uptime: {_fmts(uptime)}" if uptime else "Uptime data not available."

    # ── Health / Score ──
    if _kw_metric(q, "health"):
        score = health_data.get("score")
        drivers = health_data.get("drivers") or []
        if score is None:
            return "Health score not available yet."
        label = "healthy" if score >= 80 else ("degraded" if score >= 60 else "critical")
        parts = [f"Health score: {score}/100 ({label})"]
        if drivers:
            top = drivers[:3]
            parts.append("Top issues: " + ", ".join(
                f"{d['factor']}({d['weight']})" for d in top
            ))
        return "\n".join(parts)

    # ── Pressure / PSI ──
    if _kw_metric(q, "pressure"):
        if not pressure:
            return "No PSI data (Linux 4.20+ required, /proc/pressure may be absent)."
        lines = []
        for kind, fields in pressure.items():
            if isinstance(fields, dict):
                for field, val in fields.items():
                    lines.append(f"{kind}.{field}: {val:.2f}%")
        return "\n".join(lines) if lines else "No PSI data."

    # ── I/O wait ──
    if _kw_metric(q, "io_wait"):
        parts = []
        io_wait = sys.get("io_wait")
        if io_wait is not None:
            parts.append(f"I/O wait: {io_wait:.1f}%")
        io_pressure = pressure.get("io") or {}
        for field in ("some_avg10", "full_avg10"):
            val = io_pressure.get(field)
            if val is not None:
                parts.append(f"io pressure {field}: {val:.2f}%")
        return "\n".join(parts) if parts else "I/O wait data not available."

    # ── Anomalies ──
    if _kw_metric(q, "anomaly"):
        from app.analytics.anomaly import detector as adet
        cur = adet.current()
        if not cur:
            return "No active anomalies."
        lines = [f"{a['metric']}: z={a['z']} value={a['value']} (mean {a['mean']})" for a in cur[:10]]
        return f"{len(cur)} active anomaly/anomalies:\n" + "\n".join(lines)

    # ── Leaks ──
    if _kw_metric(q, "leak"):
        from app.analytics.leak import detector as ldet
        leaks = [l for l in ldet.current() if l.get("flagged")]
        if not leaks:
            return "No memory leaks detected."
        lines = [
            f"{l['name']} (pid {l['pid']}): {l['slope_mb_min']:.2f}MB/min, "
            f"r²={l['r2']:.2f}, OOM in ~{_fmts(l.get('ttl_oom_s'))}"
            for l in leaks[:5]
        ]
        return f"{len(leaks)} leak(s) detected:\n" + "\n".join(lines)

    # ── Crashes ──
    if _kw_metric(q, "crash"):
        crashes = (hub.latest("crashes") or {}).get("data") or {}
        counts = crashes.get("counts") or {}
        if not counts:
            return "No crashes recorded."
        lines = [f"{k}: {v}" for k, v in counts.items()]
        return "Crashes (24h):\n" + "\n".join(lines)

    # ── Processes ──
    if _kw_metric(q, "process"):
        return _process_list_answer(q, procs_snap)

    # ── Load average ──
    if _kw_metric(q, "load_average"):
        load = cpu.get("load") or []
        if not load:
            return "Load average not available."
        labels = ["1m", "5m", "15m"]
        return "Load average: " + "  ".join(f"{l}: {v:.2f}" for l, v in zip(labels, load))

    # ── EMC / Jetson engines ──
    if _kw_metric(q, "emc"):
        if not jetson:
            return "No Jetson data."
        parts = []
        emc = jetson.get("emc_load")
        if emc is not None:
            parts.append(f"EMC (memory controller): {emc:.1f}%")
        for eng, pct in (jetson.get("engines") or {}).items():
            parts.append(f"{eng}: {pct:.0f}%")
        return "\n".join(parts) if parts else "Engine data not available."

    return None  # not a direct-answer question


# ──────────────────────────────────────────────────────────────
# Layer 2: KB search answer
# ──────────────────────────────────────────────────────────────

def _kb_answer(question: str, digest: str) -> str | None:
    try:
        matches = kb.query(question + "\n" + digest, k=3)
        if not matches:
            return None
        top = matches[0]
        if top.get("score", 0) < 0.3:
            return None
        steps = top.get("steps") or []
        lines = [f"KB: {top['title']} (score {top['score']:.2f})"]
        if steps:
            lines.append("Steps:")
            lines.extend(f"  {i+1}. {s}" for i, s in enumerate(steps[:6]))
        return "\n".join(lines)
    except Exception:
        return None



async def _kb_search_async(question: str, scope: dict[str, Any] | None = None) -> str:
    ctx = await collect_context_async(_merge_scope(scope, None) or {"window": "5m"})
    digest = _digest_text(ctx)
    matches = await asyncio.to_thread(kb.query, question + "\n" + digest, 3)
    if not matches:
        return "No KB matches found."
    lines = []
    for m in matches[:3]:
        lines.append(f"{m['title']} (score {m['score']:.2f})")
        for idx, step in enumerate((m.get("steps") or [])[:5], start=1):
            lines.append(f"{idx}. {step}")
    return "\n".join(lines)


def _prefer_direct_answer(question: str, direct: str | None, needs_llm: bool | None = None) -> bool:
    if not direct:
        return False
    if needs_llm is None:
        needs_llm = _needs_llm(question)
    if not needs_llm:
        return True
    q = question.lower()
    return "log" in q and _kw_metric(q, "log_availability")


def _build_agent_messages(
    conversation: list[ChatMessage],
    scope: dict[str, Any] | None,
    context_digest: str = "",
) -> list[llm.Message]:
    compact_scope = _merge_scope(scope, None) or {"window": "5m"}
    messages: list[llm.Message] = []
    if context_digest:
        messages.append({
            "role": "user",
            "content": (
                f"[Live system context — scope: {json.dumps(compact_scope)}]\n"
                f"{context_digest}\n\n"
                "Use tools to get more specific data when needed."
            ),
        })
        messages.append({"role": "assistant", "content": _AGENT_CONTEXT_ACK})
    for m in conversation:
        messages.append({"role": m.role, "content": m.content})
    return messages


async def _run_agentic_chat(
    body: ChatRequest,
    ctx: dict[str, Any],
    max_iterations: int = 5,
) -> dict[str, Any] | None:
    base_scope = _merge_scope(body.scope, None) or {"window": "5m"}

    async def get_live_context(window="5m", services=None, pids=None) -> str:
        return _digest_text(
            await collect_context_async(_merge_scope(base_scope, {"window": window, "services": services, "pids": pids}))
        )

    async def search_kb(query, window="5m", services=None, pids=None) -> str:
        return await _kb_search_async(
            str(query),
            _merge_scope(base_scope, {"window": window, "services": services, "pids": pids}),
        )

    tools = {
        "get_direct_answer": lambda question: _direct_answer(str(question)) or "No direct live metric match.",
        "get_live_context": get_live_context,
        "search_kb": search_kb,
        "get_log_status": lambda window="15m", level=None, service=None, regex=None: _log_status(
            window=str(window),
            level=str(level) if level is not None else None,
            service=str(service) if service is not None else None,
            regex=str(regex) if regex is not None else None,
        ),
        "get_log_clusters": lambda window="15m", limit=10: _log_clusters(
            window=str(window),
            limit=int(limit),
        ),
    }

    digest = _digest_text(ctx)
    messages = _build_agent_messages(body.messages, base_scope, context_digest=digest)

    for iteration in range(max_iterations):
        result = await llm.chat(messages, system=_AGENT_SYSTEM_PROMPT, response_format="json")
        text = result.get("text", "")

        try:
            parsed = _parse_agent_response(text)
        except (ValueError, json.JSONDecodeError):
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": "Return valid JSON only. No markdown, no extra text."})
            continue

        answer = parsed.get("answer")
        if isinstance(answer, str) and answer.strip():
            return {
                "answer": answer.strip(),
                "backend": f"{result.get('backend', 'none')}+agent",
                "model": result.get("model"),
            }

        tool_name = parsed.get("tool_name")
        if not isinstance(tool_name, str) or tool_name not in tools:
            return None

        tool_args = _normalize_tool_arguments(parsed, tool_name, tools)
        try:
            tool_output = tools[tool_name](**tool_args)
            if inspect.isawaitable(tool_output):
                tool_output = await tool_output
        except TypeError:
            return None
        except Exception as e:
            tool_output = f"Tool error: {e}"

        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": f"Tool result for {tool_name}:\n{tool_output}"})

    return None


# ──────────────────────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    scope: dict[str, Any] | None = None


# ──────────────────────────────────────────────────────────────
# Endpoint
# ──────────────────────────────────────────────────────────────

def _llm_configured() -> bool:
    from app.config import settings
    provider = (settings.llm_provider or "auto").strip()
    if provider == "none":
        return False
    if provider == "auto":
        return bool(
            settings.ollama_url
            or settings.llama_url
            or settings.openai_api_key
            or settings.anthropic_api_key
            or settings.gemini_api_key
        )
    if provider == "ollama":
        return bool(settings.ollama_url)
    if provider == "llama_cpp":
        return bool(settings.llama_url)
    if provider in {"openai", "openai_compatible"}:
        return bool(settings.openai_api_key)
    if provider == "anthropic":
        return bool(settings.anthropic_api_key)
    if provider == "gemini":
        return bool(settings.gemini_api_key)
    return False


@router.post("/chat")
async def chat_endpoint(body: ChatRequest) -> dict[str, Any]:
    t0 = time.time()

    last_user = next(
        (m.content for m in reversed(body.messages) if m.role == "user"), ""
    )

    # Layer 1: collect live metric data (always runs — instant, no deps)
    direct = _direct_answer(last_user)

    # If LLM not configured: return direct data answer immediately (or explain)
    if not _llm_configured():
        if direct:
            return {
                "answer": direct,
                "backend": "direct",
                "latency_ms": int((time.time() - t0) * 1000),
            }
        # No direct match — try KB then give raw digest
        ctx = await collect_context_async(body.scope or {"window": "5m"})
        digest = _digest_text(ctx)
        kb_ans = await asyncio.to_thread(_kb_answer, last_user, digest)
        if kb_ans:
            return {
                "answer": kb_ans,
                "backend": "kb",
                "latency_ms": int((time.time() - t0) * 1000),
            }
        return {
            "answer": (
                "No LLM configured (choose a provider in LLM settings, or set SH_OLLAMA_URL / SH_LLAMA_URL).\n\n"
                f"Live system snapshot:\n{digest}"
            ),
            "backend": "none",
            "latency_ms": int((time.time() - t0) * 1000),
        }

    needs_llm = _needs_llm(last_user)
    if _prefer_direct_answer(last_user, direct, needs_llm=needs_llm):
        return {
            "answer": direct,
            "backend": "direct",
            "latency_ms": int((time.time() - t0) * 1000),
        }

    # Collect context once — reused by both agentic path and fallback LLM path
    ctx = await collect_context_async(_merge_scope(body.scope, None) or {"window": "5m"})
    digest = _digest_text(ctx)

    if needs_llm or direct is None:
        try:
            agentic = await _run_agentic_chat(body, ctx)
        except Exception:
            agentic = None
        if agentic:
            agentic["latency_ms"] = int((time.time() - t0) * 1000)
            return agentic

    kb_ans = await asyncio.to_thread(_kb_answer, last_user, digest)
    kb_text = kb_ans or ""

    # If direct answer exists, inject as structured data block so LLM reasons over real values
    data_block = f"[Extracted metric data for this question]\n{direct}" if direct else ""
    context_prefix = f"[Live system context]\n{digest}"
    if data_block:
        context_prefix = data_block + "\n\n" + context_prefix
    if kb_text:
        context_prefix += f"\n\n[Relevant KB]\n{kb_text}"

    llm_messages: list[llm.Message] = [
        {"role": "user", "content": context_prefix},
        {"role": "assistant", "content": "Understood. I have the current metric data and system state. Ask away."},
    ]
    for m in body.messages:
        llm_messages.append({"role": m.role, "content": m.content})

    try:
        result = await llm.chat(llm_messages, system=_SYSTEM_PROMPT)
    except Exception as e:
        fallback = direct or kb_ans or digest
        return {
            "answer": fallback,
            "backend": "direct+kb_fallback",
            "note": str(e),
            "latency_ms": int((time.time() - t0) * 1000),
        }

    answer = result.get("text", "")
    backend = result.get("backend", "none")

    if direct and backend not in ("none", "error"):
        backend = f"{backend}+direct"

    if not kb_text and answer and result.get("backend") not in ("none", "error"):
        try:
            _maybe_save_kb_stub(last_user, answer, digest)
        except Exception:
            pass

    return {
        "answer": answer,
        "backend": backend,
        "model": result.get("model"),
        "latency_ms": int((time.time() - t0) * 1000),
    }


def _needs_llm(question: str) -> bool:
    q = question.lower()
    return any(w in q for w in kw_cfg.reasoning_keywords())


def _maybe_save_kb_stub(question: str, answer: str, digest: str) -> None:
    from app.config import settings

    kb_dir = settings.kb_path
    if not kb_dir.exists():
        return

    slug = re.sub(r"[^a-z0-9]+", "_", question.lower().strip())[:40].strip("_")
    if not slug:
        return

    stub_path = kb_dir / f"auto_{slug}.md"
    if stub_path.exists():
        return

    if len(list(kb_dir.glob("auto_*.md"))) >= 50:
        return

    content = (
        f'---\ntitle: "{question[:80]}"\ntags: [auto-generated]\nseverity: info\n---\n\n'
        f"## Question\n{question}\n\n"
        f"## Context\n```\n{digest[:500]}\n```\n\n"
        f"## LLM Answer\n{answer[:1000]}\n\n"
        f"## Steps\n- Review context above\n- Validate against current system state\n"
    )
    stub_path.write_text(content)
