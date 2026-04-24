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

import re
import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.agent import kb, llm
from app.agent.diagnose import collect_context, _digest_text
from app.hub import hub

router = APIRouter(prefix="/api", tags=["chat"])

_SYSTEM_PROMPT = (
    "You are an embedded ops assistant on a Linux/Jetson device. "
    "Live system context is already injected. Be concise, name specific processes/services. "
    "No markdown headers. Max 6 lines."
)


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

    # ── CPU ──
    if _kw(q, "cpu", "processor", "core", "utilization") and not _kw(q, "gpu"):
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
        return "\n".join(parts) if parts else None

    # ── Memory / RAM ──
    if _kw(q, "memory", "mem", "ram") and not _kw(q, "gpu", "vram"):
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
    if _kw(q, "swap"):
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
    if _kw(q, "disk", "storage", "space", "filesystem", "mount"):
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
    if _kw(q, "temp", "thermal", "hot", "heat", "celsius", "degrees"):
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
    if _kw(q, "gpu", "graphics", "cuda", "vram", "gpu ram"):
        if not jetson:
            return "No GPU data (Jetson not detected or jtop not running)."
        parts = []
        load = jetson.get("gpu_load")
        if load is not None:
            parts.append(f"GPU load: {load:.1f}%")
        ram_used = jetson.get("gpu_ram_used")
        ram_total = jetson.get("gpu_ram_total")
        if ram_used is not None:
            parts.append(f"GPU RAM: {_fmtb(ram_used)} / {_fmtb(ram_total or 0)}")
        for eng, pct in (jetson.get("engines") or {}).items():
            parts.append(f"{eng}: {pct:.0f}%")
        return "\n".join(parts) if parts else "GPU data not available."

    # ── Power ──
    if _kw(q, "power", "watt", "energy", "consumption"):
        if not jetson:
            return "No power data (Jetson not detected)."
        parts = []
        pw = jetson.get("power_w")
        if pw is not None:
            parts.append(f"Total power: {pw:.1f}W")
        for rail, w in (jetson.get("power_rails") or {}).items():
            parts.append(f"  {rail}: {w:.2f}W")
        return "\n".join(parts) if parts else "Power data not available."

    # ── Fan ──
    if _kw(q, "fan", "cooling", "rpm"):
        if not jetson:
            return "No fan data (Jetson not detected)."
        fan = jetson.get("fan_pct")
        if fan is not None:
            return f"Fan speed: {fan:.1f}%"
        return "Fan data not available."

    # ── Network ──
    if _kw(q, "network", "net", "bandwidth", "rx", "tx", "throughput"):
        parts = []
        rx = net.get("rx_bps")
        tx = net.get("tx_bps")
        if rx is not None:
            parts.append(f"RX: {_fmtb(rx)}/s")
        if tx is not None:
            parts.append(f"TX: {_fmtb(tx)}/s")
        return "\n".join(parts) if parts else "No network data."

    # ── Uptime ──
    if _kw(q, "uptime", "up time", "running for", "how long"):
        uptime = sys.get("uptime_s")
        return f"Uptime: {_fmts(uptime)}" if uptime else "Uptime data not available."

    # ── Health / Score ──
    if _kw(q, "health", "score", "overall status", "system status", "how is the system"):
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
    if _kw(q, "pressure", "psi", "stall"):
        if not pressure:
            return "No PSI data (Linux 4.20+ required, /proc/pressure may be absent)."
        lines = []
        for kind, fields in pressure.items():
            if isinstance(fields, dict):
                for field, val in fields.items():
                    lines.append(f"{kind}.{field}: {val:.2f}%")
        return "\n".join(lines) if lines else "No PSI data."

    # ── Anomalies ──
    if _kw(q, "anomaly", "anomalies", "spike", "unusual", "abnormal"):
        from app.analytics.anomaly import detector as adet
        cur = adet.current()
        if not cur:
            return "No active anomalies."
        lines = [f"{a['metric']}: z={a['z']} value={a['value']} (mean {a['mean']})" for a in cur[:10]]
        return f"{len(cur)} active anomaly/anomalies:\n" + "\n".join(lines)

    # ── Leaks ──
    if _kw(q, "leak", "memory leak", "rss climbing", "rss growing"):
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
    if _kw(q, "crash", "crashes", "killed", "oom kill", "segfault"):
        crashes = (hub.latest("crashes") or {}).get("data") or {}
        counts = crashes.get("counts") or {}
        if not counts:
            return "No crashes recorded."
        lines = [f"{k}: {v}" for k, v in counts.items()]
        return "Crashes (24h):\n" + "\n".join(lines)

    # ── Processes ──
    if _kw(q, "process", "top process", "pid", "what is running", "who is using"):
        procs = (hub.latest("processes") or {}).get("data", {}).get("procs") or []
        if not procs:
            return "No process data available."
        top = sorted(procs, key=lambda p: p.get("cpu", 0), reverse=True)[:8]
        lines = [
            f"{p['name']} (pid {p['pid']}): cpu {p.get('cpu',0):.1f}% "
            f"mem {_fmtb(p.get('rss',0))}"
            for p in top
        ]
        return "Top processes by CPU:\n" + "\n".join(lines)

    # ── Load average ──
    if _kw(q, "load average", "load avg", "load 1", "load 5", "load 15"):
        load = cpu.get("load") or []
        if not load:
            return "Load average not available."
        labels = ["1m", "5m", "15m"]
        return "Load average: " + "  ".join(f"{l}: {v:.2f}" for l, v in zip(labels, load))

    # ── EMC / Jetson engines ──
    if _kw(q, "emc", "memory controller", "dla", "nvenc", "nvdec", "vic"):
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
    return bool(settings.ollama_url or settings.llama_url)


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
        ctx = collect_context(body.scope or {"window": "5m"})
        digest = _digest_text(ctx)
        kb_ans = _kb_answer(last_user, digest)
        if kb_ans:
            return {
                "answer": kb_ans,
                "backend": "kb",
                "latency_ms": int((time.time() - t0) * 1000),
            }
        return {
            "answer": (
                "No LLM configured (set SH_OLLAMA_URL or SH_LLAMA_URL).\n\n"
                f"Live system snapshot:\n{digest}"
            ),
            "backend": "none",
            "latency_ms": int((time.time() - t0) * 1000),
        }

    # LLM IS configured: gather all context, then refine with LLM
    ctx = collect_context(body.scope or {"window": "5m"})
    digest = _digest_text(ctx)
    kb_ans = _kb_answer(last_user, digest)
    kb_text = kb_ans or ""

    # Build LLM prompt: live data first, then KB, then conversation
    # If direct answer exists, inject it as a structured data block so
    # LLM can reason over it rather than guess the values
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
        # LLM failed — fall back to direct/KB answer
        fallback = direct or kb_ans or digest
        return {
            "answer": fallback,
            "backend": "direct+kb_fallback",
            "note": str(e),
            "latency_ms": int((time.time() - t0) * 1000),
        }

    answer = result.get("text", "")
    backend = result.get("backend", "none")

    # Tag with refinement info when direct data was used
    if direct and backend not in ("none", "error"):
        backend = f"{backend}+direct"

    # KB auto-refinement stub
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
    reasoning_words = ["why", "what should", "how to", "fix", "diagnose", "cause", "reason", "recommend", "help"]
    return any(w in q for w in reasoning_words)


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
