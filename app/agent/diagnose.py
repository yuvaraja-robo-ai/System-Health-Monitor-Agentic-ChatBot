import asyncio
import time
from typing import Any

from app.agent import kb, llm
from app.analytics.leak import detector
from app.db import duckdb as ldb
from app.db import sqlite as sdb
from app.hub import hub
from app.utils.service import parse_window, service_match


def _parse_window(s: str | int | None) -> int:
    return parse_window(s, default=300)


def _service_match(scope_services: list[str], candidate: str | None) -> bool:
    return service_match(scope_services, candidate)


def collect_context(scope: dict[str, Any]) -> dict[str, Any]:
    window_s = _parse_window(scope.get("window", "5m"))
    now = int(time.time())
    since = now - window_s

    sys_cur = (hub.latest("system") or {}).get("data") or {}
    health = (hub.latest("health") or {}).get("data") or {}
    crashes = (hub.latest("crashes") or {}).get("data") or {"counts": {}, "recent": []}
    leaks = [l for l in detector.current() if l["flagged"]]

    pids = scope.get("pids") or []
    services = scope.get("services") or []
    scoped = bool(pids or services)

    top_procs = []
    procs_snap = (hub.latest("processes") or {}).get("data", {}).get("procs", [])
    scoped_procs = [
        p for p in procs_snap
        if (not pids or p["pid"] in pids) or _service_match(services, p.get("name"))
    ]
    proc_source = scoped_procs if scoped else procs_snap
    for p in proc_source[:15]:
        top_procs.append(
            {
                "pid": p["pid"],
                "name": p["name"],
                "cpu": p["cpu"],
                "rss_mb": round(p["rss"] / (1024 * 1024), 1),
            }
        )

    err_clusters = ldb.cluster_logs(since, limit=15)
    if services:
        err_clusters = [c for c in err_clusters if _service_match(services, c.get("service"))]

    leaks_source = leaks
    if scoped:
        leaks_source = [
            l for l in leaks
            if (not pids or l["pid"] in pids) or _service_match(services, l.get("name"))
        ]

    unit_events = sdb.recent_events("unit.", since, limit=50)
    if services:
        unit_events = [
            e for e in unit_events
            if _service_match(services, (e.get("payload") or {}).get("unit"))
        ]

    crash_events = sdb.recent_events("crash.", since, limit=50)
    if scoped:
        crash_events = [
            e for e in crash_events
            if (not pids or int((e.get("payload") or {}).get("pid") or 0) in pids)
            or _service_match(services, (e.get("payload") or {}).get("unit"))
            or _service_match(services, (e.get("payload") or {}).get("message"))
        ]

    try:
        cpu_hist = sdb.history("cpu.total", since, now, max(1, window_s // 60))
        mem_hist = sdb.history("mem.used", since, now, max(1, window_s // 60))
    except Exception:
        cpu_hist = mem_hist = []

    return {
        "window_s": window_s,
        "now": now,
        "system": sys_cur,
        "health": health,
        "crashes": {
            "counts": crashes.get("counts", {}) if not scoped else {},
            "recent_n": len(crash_events) if scoped else len(crashes.get("recent", [])),
            "recent": crash_events[:10],
        },
        "leaks": leaks_source,
        "top_procs": top_procs,
        "log_clusters": err_clusters,
        "unit_events": unit_events,
        "cpu_series": cpu_hist,
        "mem_series": mem_hist,
        "scope": {"pids": pids, "services": services, "scoped": scoped},
    }


async def collect_context_async(scope: dict[str, Any]) -> dict[str, Any]:
    window_s = _parse_window(scope.get("window", "5m"))
    now = int(time.time())
    since = now - window_s
    step = max(1, window_s // 60)

    sys_cur = (hub.latest("system") or {}).get("data") or {}
    health = (hub.latest("health") or {}).get("data") or {}
    crashes = (hub.latest("crashes") or {}).get("data") or {"counts": {}, "recent": []}
    leaks = [l for l in detector.current() if l["flagged"]]

    pids = scope.get("pids") or []
    services = scope.get("services") or []
    scoped = bool(pids or services)

    procs_snap = (hub.latest("processes") or {}).get("data", {}).get("procs", [])
    scoped_procs = [
        p for p in procs_snap
        if (not pids or p["pid"] in pids) or _service_match(services, p.get("name"))
    ]
    proc_source = scoped_procs if scoped else procs_snap
    top_procs = [
        {
            "pid": p["pid"],
            "name": p["name"],
            "cpu": p["cpu"],
            "rss_mb": round(p["rss"] / (1024 * 1024), 1),
        }
        for p in proc_source[:15]
    ]

    err_task = asyncio.to_thread(ldb.cluster_logs, since, 15)
    unit_task = asyncio.to_thread(sdb.recent_events, "unit.", since, 50)
    crash_task = asyncio.to_thread(sdb.recent_events, "crash.", since, 50)
    cpu_task = asyncio.to_thread(sdb.history, "cpu.total", since, now, step)
    mem_task = asyncio.to_thread(sdb.history, "mem.used", since, now, step)
    results = await asyncio.gather(
        err_task,
        unit_task,
        crash_task,
        cpu_task,
        mem_task,
        return_exceptions=True,
    )

    err_clusters = [] if isinstance(results[0], Exception) else results[0]
    unit_events = [] if isinstance(results[1], Exception) else results[1]
    crash_events = [] if isinstance(results[2], Exception) else results[2]
    cpu_hist = [] if isinstance(results[3], Exception) else results[3]
    mem_hist = [] if isinstance(results[4], Exception) else results[4]

    if services:
        err_clusters = [c for c in err_clusters if _service_match(services, c.get("service"))]
        unit_events = [
            e for e in unit_events
            if _service_match(services, (e.get("payload") or {}).get("unit"))
        ]

    leaks_source = leaks
    if scoped:
        leaks_source = [
            l for l in leaks
            if (not pids or l["pid"] in pids) or _service_match(services, l.get("name"))
        ]
        crash_events = [
            e for e in crash_events
            if (not pids or int((e.get("payload") or {}).get("pid") or 0) in pids)
            or _service_match(services, (e.get("payload") or {}).get("unit"))
            or _service_match(services, (e.get("payload") or {}).get("message"))
        ]

    return {
        "window_s": window_s,
        "now": now,
        "system": sys_cur,
        "health": health,
        "crashes": {
            "counts": crashes.get("counts", {}) if not scoped else {},
            "recent_n": len(crash_events) if scoped else len(crashes.get("recent", [])),
            "recent": crash_events[:10],
        },
        "leaks": leaks_source,
        "top_procs": top_procs,
        "log_clusters": err_clusters,
        "unit_events": unit_events,
        "cpu_series": cpu_hist,
        "mem_series": mem_hist,
        "scope": {"pids": pids, "services": services, "scoped": scoped},
    }


def _digest_text(ctx: dict[str, Any]) -> str:
    parts = [f"Host window: last {ctx['window_s']}s. Health score: {ctx['health'].get('score','?')}/100."]
    scope = ctx.get("scope") or {}
    if scope.get("scoped"):
        named = ", ".join(scope.get("services") or []) or "selected processes"
        parts.append(f"Scoped analysis for: {named}.")
    sys = ctx["system"]
    if sys:
        mem = sys.get("mem", {})
        cpu = sys.get("cpu", {})
        parts.append(
            f"CPU {cpu.get('total',0):.1f}% load {cpu.get('load',[0])[0]:.2f}. "
            f"Mem used {mem.get('used',0)/1e9:.2f}/{mem.get('total',0)/1e9:.2f}G."
        )
    if ctx["leaks"]:
        for l in ctx["leaks"][:5]:
            parts.append(
                f"Leak: {l['name']} pid={l['pid']} slope={l['slope_mb_min']}MB/min r2={l['r2']} ttl={l['ttl_oom_s']}s"
            )
    if ctx["crashes"]["counts"]:
        parts.append("Crashes 24h: " + ", ".join(f"{k}={v}" for k, v in ctx["crashes"]["counts"].items()))
    elif ctx["crashes"].get("recent_n"):
        parts.append(f"Scoped crashes/events: {ctx['crashes']['recent_n']}.")
    if ctx["log_clusters"]:
        parts.append("Top error clusters:")
        for c in ctx["log_clusters"][:5]:
            parts.append(f"- [{c['level']}] {c['service']} ×{c['count']}: {c['sample'][:120]}")
    if ctx["top_procs"]:
        procs = ", ".join(f"{p['name']}({p['rss_mb']}M)" for p in ctx["top_procs"][:5])
        parts.append("Top RSS: " + procs)
    return "\n".join(parts)


async def diagnose(scope: dict[str, Any], question: str | None = None) -> dict[str, Any]:
    t0 = time.time()
    ctx = await collect_context_async(scope or {})
    digest = _digest_text(ctx)
    matches = []
    try:
        matches = kb.query(digest + ("\nQuestion: " + question if question else ""), k=5)
    except Exception:
        matches = []
    kb_text = "\n".join(f"[{m['title']}] score={m['score']:.2f}\nSteps: " + "; ".join(m.get("steps", [])) for m in matches)
    system = (
        "You are an ops assistant diagnosing a Linux system. Use the provided digest and KB matches. "
        "Be concise, name specific processes/services, and recommend the next concrete action."
    )
    prompt = (
        f"Digest:\n{digest}\n\nKB matches:\n{kb_text or '(none)'}\n\n"
        f"Question: {question or 'What is wrong and what should I do next?'}\n\n"
        "Answer in <=6 lines."
    )
    try:
        ans = await llm.complete(prompt, system=system)
    except Exception as e:
        ans = {"text": f"(LLM error: {e})", "backend": "error"}
    summary_bits = [f"score={ctx['health'].get('score','?')}"]
    if ctx["leaks"]:
        summary_bits.append(f"leaks={len(ctx['leaks'])}")
    if ctx["crashes"]["counts"]:
        summary_bits.append(f"crashes={sum(ctx['crashes']['counts'].values())}")
    summary = " ".join(summary_bits)
    return {
        "summary": summary,
        "matches": [{"title": m["title"], "score": m["score"], "steps": m.get("steps", [])} for m in matches],
        "llm_answer": ans,
        "context_digest": digest,
        "latency_ms": int((time.time() - t0) * 1000),
    }
