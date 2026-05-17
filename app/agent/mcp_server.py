"""
SystemHealth MCP server.

Exposes health/metrics/logs/process query tools to an ai_core agent.

Architecture:
  ai_core.run_agent() ──spawn(stdio)──► this MCP server ──HTTP──► SystemHealth FastAPI (port 9090)

Prereqs:
- SystemHealth FastAPI app must be running on http://localhost:9090
  (start with: cd System-Health-Monitor-Agentic-ChatBot && ./start.sh)

Run standalone for a sanity check:
    python -m app.agent.mcp_server
"""

import os
import time
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.getenv("SYSTEMHEALTH_URL", "http://localhost:9090")
# Briefing aggregates over a 6h window and can take >15s on cold caches;
# default raised to 45s. Override with SYSTEMHEALTH_TIMEOUT.
TIMEOUT = float(os.getenv("SYSTEMHEALTH_TIMEOUT", "45"))
CONNECT_TIMEOUT = float(os.getenv("SYSTEMHEALTH_CONNECT_TIMEOUT", "3"))
RETRIES = int(os.getenv("SYSTEMHEALTH_RETRIES", "2"))
HEALTH_PATH = os.getenv("SYSTEMHEALTH_HEALTH_PATH", "/api/health")

mcp = FastMCP("system-health")


def _hint() -> str:
    return (
        f"Is SystemHealth running on {BASE_URL}? "
        f"Start it with `./start.sh`, then verify: "
        f"`curl -sf {BASE_URL}{HEALTH_PATH}`."
    )


def _split_timeout() -> httpx.Timeout:
    # Distinct connect vs read timeouts so an unreachable server fails fast
    # (≤3s) instead of waiting for the full read budget.
    return httpx.Timeout(TIMEOUT, connect=CONNECT_TIMEOUT)


def _request(method: str, path: str, *, params: Optional[dict] = None,
             json_body: Optional[dict] = None) -> dict[str, Any]:
    """HTTP helper with retry on transient failures and shaped errors."""
    url = f"{BASE_URL}{path}"
    last_err: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            r = httpx.request(method, url, params=params or None,
                              json=json_body, timeout=_split_timeout())
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            return {
                "error": f"HTTP {e.response.status_code}",
                "body": e.response.text[:300],
                "url": url,
            }
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout,
                httpx.RemoteProtocolError) as e:
            last_err = e
            if attempt < RETRIES:
                time.sleep(0.5 * (attempt + 1))
                continue
            kind = "timed_out" if "timeout" in type(e).__name__.lower() else "request_failed"
            return {
                "error": kind,
                "detail": str(e) or type(e).__name__,
                "url": url,
                "attempts": attempt + 1,
                "hint": _hint(),
            }
        except httpx.RequestError as e:
            return {
                "error": "request_failed",
                "detail": str(e) or type(e).__name__,
                "url": url,
                "hint": _hint(),
            }
    # Fallthrough — defensive, should not reach here.
    return {"error": "request_failed", "detail": str(last_err), "url": url, "hint": _hint()}


def _get(path: str, params: Optional[dict] = None) -> dict:
    return _request("GET", path, params=params)


def _post(path: str, body: dict) -> dict:
    return _request("POST", path, json_body=body)


@mcp.tool()
def get_system_metrics() -> dict:
    """Current CPU, memory, disk, network, thermal snapshot from the live host.
    Returns: {system: {cpu, mem, disk, net, thermal, uptime, ...}, jetson: {...} | null}.
    Use this first to see the current state."""
    return _get("/api/system/current")


@mcp.tool()
def get_metric_history(field: str, window: str = "5m", step: str = "10s") -> dict:
    """Time-series history for one metric.
    field: e.g. 'cpu.total', 'mem.used', 'mem.percent', 'thermal.cpu_max', 'gpu.util'.
    window: '5m' | '15m' | '1h' | '6h' | '24h'.
    step: '10s' | '1m' | '5m'.
    Returns: {ts: [...epoch_ms...], values: [...]}.
    Use when current snapshot looks abnormal and you need a trend."""
    return _get("/api/system/history", params={"field": field, "window": window, "step": step})


@mcp.tool()
def query_logs(level: Optional[str] = None, service: Optional[str] = None,
               regex: Optional[str] = None, window: str = "5m", limit: int = 100) -> dict:
    """Search system logs.
    level: 'ERROR' | 'WARN' | 'INFO' (omit for all).
    service: systemd unit name like 'kubelet' or 'docker' (omit for all).
    regex: optional substring/regex filter.
    window: time back from now ('5m', '1h', etc.).
    limit: max rows.
    Returns: {rows: [{ts, level, service, message}, ...]}.
    Use when investigating a specific error or incident timeframe."""
    params = {"since": window, "limit": limit}
    if level:
        params["level"] = level
    if service:
        params["service"] = service
    if regex:
        params["regex"] = regex
    return _get("/api/logs", params=params)


@mcp.tool()
def get_log_clusters(window: str = "5m", limit: int = 15) -> dict:
    """Group similar log errors into signatures with counts.
    Returns: {clusters: [{signature, level, service, count, first, last, sample}, ...]}.
    Use to spot dominant error patterns without reading raw logs."""
    return _get("/api/logs/cluster", params={"since": window, "limit": limit})


@mcp.tool()
def get_top_processes(sort: str = "rss", limit: int = 20) -> dict:
    """Rank top N processes by resource usage.
    sort: 'rss' (memory) | 'cpu' | 'threads'.
    Returns: {processes: [{pid, name, rss, cpu, threads, leak_flag, leak_slope_mb_min}, ...]}.
    Use to find resource hogs and memory leak candidates."""
    return _get("/api/processes", params={"sort": sort, "limit": limit})


@mcp.tool()
def get_process_history(pid: int, window: str = "6h") -> dict:
    """Memory (RSS) trajectory for a single process.
    Returns: {ts: [...], rss_mb: [...], slope_mb_min, r2, ttl_oom_s}.
    Use after get_top_processes flags a leak candidate — confirms growth trend."""
    return _get(f"/api/processes/{pid}/rss", params={"window": window})


@mcp.tool()
def get_briefing(window: str = "6h") -> dict:
    """Overall health briefing.
    Returns: {score: 0-100, headline, drivers: {cpu, mem, thermal, leaks, crashes}, app_status, featured_incident}.
    Use as a starting point to summarize host state."""
    return _get("/api/briefing", params={"window": window})


@mcp.tool()
def diagnose_scope(window: str = "5m", services: str = "", pids: str = "") -> dict:
    """Scoped diagnostic context: live snapshot + leaks + crashes + relevant logs + KB matches.
    services: comma-separated systemd unit names (optional filter).
    pids: comma-separated process IDs (optional filter).
    Returns: {context: {...}, digest_text: '...'}.
    Use as a one-shot info dump when investigating an incident scoped to specific units/pids."""
    scope = {"window": window}
    if services:
        scope["services"] = [s.strip() for s in services.split(",") if s.strip()]
    if pids:
        scope["pids"] = [int(p.strip()) for p in pids.split(",") if p.strip()]
    return _post("/api/diagnose/context", {"scope": scope})


@mcp.tool()
def search_kb(query: str, k: int = 5) -> dict:
    """Semantic search of the runbook knowledge base (high_cpu.md, memory_leak.md, thermal.md, etc.).
    Returns: {results: [{id, title, tags, steps, score}, ...]}.
    Use to look up remediation steps for a known pattern."""
    return _post("/api/kb/search", {"query": query, "k": k})


@mcp.tool()
def get_thresholds() -> dict:
    """Configured alert thresholds (CPU %, memory %, thermal °C, etc.).
    Use to know what counts as 'high' for this host."""
    return _get("/api/config/thresholds")


if __name__ == "__main__":
    mcp.run(transport="stdio")
