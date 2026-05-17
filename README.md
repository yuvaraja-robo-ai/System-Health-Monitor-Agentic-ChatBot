# System Health Monitor — Agentic ChatBot

Real-time host monitoring dashboard for **NVIDIA Jetson** (Nano, Orin, AGX) and **Ubuntu** systems, with an agentic chat assistant that answers live system questions — no cloud required.

![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Jetson%20%7C%20Ubuntu-green)

---

## Features

- **Live metrics** — CPU, memory, disk, network, GPU (Jetson), power rails, thermal zones, PSI pressure
- **Process table** — per-process CPU/RSS, configurable app groups
- **Log explorer** — journald + custom file tails, DuckDB-backed full-text search, error clustering
- **Leak hunter** — linear regression on per-process RSS slope; flags suspects in real time
- **Crash tracker** — coredump events, OOM kills, segfaults
- **Anomaly detection** — rolling z-score (3σ), Pearson cross-metric correlation
- **USE+RED health score** — weighted penalty model, threshold auto-tune from anomaly history
- **Agent chat** — 3-layer answer pipeline: direct hub data → KB semantic search → local LLM
- **Knowledge base** — FAISS + sentence-transformers, auto-generated stubs from LLM answers
- **Alerts** — webhook (Slack-compatible), dedup cooldown, maintenance silence windows
- **Prometheus metrics** — `/metrics` endpoint, text exposition format
- **SLA reporting** — uptime %, MTTR, incident count over configurable window
- **No build step** — React 18 loaded from CDN, JSX transpiled in-browser

---

## Quickstart

### 1. Install

```bash
git clone https://github.com/your-org/System-Health-Monitor-Agentic-ChatBot.git
cd systemhealth
pip install -e .
```

**Jetson (GPU/power metrics):**
```bash
pip install -e ".[jetson]"
```

**Agent chat KB search:**
```bash
pip install -e ".[kb]"
```

**Everything:**
```bash
pip install -e ".[all]"
```

For contributors:
```bash
pip install pytest pytest-asyncio httpx
```

### 2. Configure (optional)

```bash
cp .env.example .env
# edit .env — all settings have sensible defaults
```

### 3. Run

```bash
./start.sh
# open http://localhost:9090
```

`start.sh` auto-detects a local llama.cpp server at `http://127.0.0.1:8080`
or Ollama at `http://127.0.0.1:11434`. It disables KB indexing by default for
fast startup; use `SH_ENABLE_KB=1 ./start.sh` if you want KB runbook search.

Manual developer runner:
```bash
bash dev.sh
# open http://localhost:9090
```

Or directly:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 9090
```

---

## Agent Chat

The dashboard includes a chat panel (click **💬 agent** in the tab bar) that answers questions about the running system.

Answers come from three layers — no LLM required for the first two:

| Layer | Requires | Latency | Best for |
|-------|----------|---------|----------|
| Direct hub data | Nothing | <5 ms | "what is CPU usage right now" |
| KB semantic search | `pip install -e ".[kb]"` | 50–200 ms | "how do I fix high memory pressure" |
| Local LLM reasoning | Ollama or llama.cpp | 2–30 s | "why is CPU spiking every 10 minutes" |

**Configure LLM backend (optional):**
```bash
# .env
SH_OLLAMA_URL=http://localhost:11434
# or, for llama.cpp:
SH_LLAMA_URL=http://127.0.0.1:8080
SH_LLM_MODEL=llama3.2:3b
```

See [AGENT_CHAT_ARCHITECTURE.md](AGENT_CHAT_ARCHITECTURE.md) for full design details and [docs/agent-chat-sequence.puml](/tmp/System-Health-Monitor-Agentic-ChatBot/docs/agent-chat-sequence.puml:1) for the end-to-end sequence diagram.

Chat resolution order:

1. Direct live-data answer from in-memory hub snapshots
2. KB semantic search over Markdown runbooks in `data/kb/`
3. Local LLM reasoning through Ollama or llama.cpp

---

## Agent Chat v2 — ai_core integration

A second chat pipeline, backed by the reusable [`ai_core`](../ai_core) package and `llm_gatewayV2`, replaces the prompted-JSON dispatch in `app/api/chat.py` with **native tool-use, parallel dispatch, and a structured Verdict from a separate verifier LLM**.

### Architecture

```
dashboard.html ──💬 floating panel ──► WS /api/chat_v2/stream
                                              │
                                              ▼
                        app/api/chat_v2.py ──► app/agent/aicore_chat.py
                                                      │
                                                      ▼
                                              ai_core.run_agent()
                                              │            │
                                ┌─────────────┘            └─────────────┐
                                ▼                                        ▼
                  llm_gatewayV2 (port 8100)             app/agent/mcp_server.py (stdio)
                  native tool-use, structured              │
                  output, reasoning knob                   ▼
                                                  HTTP → /api/* endpoints
                                                  (system, processes, logs, briefing,
                                                   kb/search, diagnose/context, ...)
```

### Component overview

| File | Purpose |
|------|---------|
| `app/agent/mcp_server.py` | FastMCP server with 10 tools that proxy to existing `/api/*` REST endpoints |
| `app/agent/health_prompt.md` | Qualified sysadmin system prompt |
| `app/agent/aicore_chat.py` | Thin wrapper: `answer(question)` → calls `ai_core.run_agent()` |
| `app/api/chat_v2.py` | `POST /api/chat_v2` (one-shot) + `WS /api/chat_v2/stream` (live trace) |
| `app/api/diagnose.py` | `POST /api/kb/search` and `POST /api/diagnose/context` (pure-data, no LLM) |
| `chat_v2_panel.jsx` | Floating chat panel self-mounted on dashboard.html |
| `pyproject.toml` | Declares `mcp[cli]` + `ai-core` path dependency |

### MCP tools exposed

| Tool | Wraps |
|------|-------|
| `get_system_metrics()` | `GET /api/current` |
| `get_metric_history(field, window, step)` | `GET /api/system/history` |
| `query_logs(level, service, regex, window, limit)` | `GET /api/logs` |
| `get_log_clusters(window, limit)` | `GET /api/logs/cluster` |
| `get_top_processes(sort, limit)` | `GET /api/processes` |
| `get_process_history(pid, window)` | `GET /api/processes/{pid}/rss` |
| `get_briefing(window)` | `GET /api/briefing` |
| `diagnose_scope(window, services, pids)` | `POST /api/diagnose/context` |
| `search_kb(query, k)` | `POST /api/kb/search` |
| `get_thresholds()` | `GET /api/config/thresholds` |

### Run (uv recommended)

```bash
# 0. Make sure uv is installed
curl -LsSf https://astral.sh/uv/install.sh | sh   # if missing

# 1. Start llm_gatewayV2 (one level up, port 8100)
#    Auto-detects local Ollama (port 11434) and prefers it in failover.
cd ../llm_gatewayV2 && ./run.sh

# 2. Sync this project's venv (picks up ai-core path dep + mcp[cli])
cd ../System-Health-Monitor-Agentic-ChatBot
uv sync

# 3. Start SystemHealth (start.sh uses uv when available)
./start.sh   # port 9090

# 4. Use the chat panel
#    Browser: open http://localhost:9090/dashboard.html — click "💬 Ask SystemHealth"
#
#    CLI:
uv run python -m app.agent.aicore_chat "why is cpu spiking?"
#
#    REST:
curl -s -X POST http://localhost:9090/api/chat_v2 \
  -H 'Content-Type: application/json' \
  -d '{"message":"top memory hogs right now"}' | python3 -m json.tool
```

**Local-first LLM routing:** the gateway probes `127.0.0.1:11434` on startup. If
Ollama is running, it auto-registers and lands at the head of `LLM_ORDER`. The
agent loop's executor (no structured output needed) will use Ollama; the
verifier and UI composer (need `response_format`) fall over to Gemini/NVIDIA
via capability routing.

### Why v2 over v1

| | v1 (`app/api/chat.py`) | v2 (`app/api/chat_v2.py`) |
|---|---|---|
| Tool dialect | Prompted JSON in text | Native tool-use via llm_gatewayV2 |
| Parsing | Manual `parse_llm_json` + regex | None — structured response from gateway |
| Parallel dispatch | Sequential | `asyncio.TaskGroup` |
| Verifier | None | Separate LLM call → `Verdict` JSON |
| Reasoning budget | n/a | `"off"` executor, `"medium"` verifier |
| Pydantic boundary | partial | every boundary (`ToolDef`, `AgentTrace`, `Verdict`) |
| Reuse across apps | no | yes — same `ai_core` powers physics_solver |

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/system/current` | Live system snapshot |
| GET | `/api/system/history?metric=cpu.total&window=3600` | Time series |
| GET | `/api/processes` | Process table |
| GET | `/api/leaks` | Active leak suspects |
| GET | `/api/crashes` | Crash events |
| GET | `/api/logs?q=error&service=myapp` | Log search |
| GET | `/api/health` | Health score + drivers |
| GET | `/api/anomalies` | Active z-score anomalies |
| GET | `/api/correlate` | Cross-metric Pearson pairs |
| GET | `/api/sla?window=7d` | Uptime %, MTTR, incidents |
| GET | `/api/timeline?window=3600` | Merged event stream |
| GET | `/metrics` | Prometheus text |
| POST | `/api/chat` | Agent chat |
| POST | `/api/kb/reload` | Hot-reload KB |
| GET | `/api/config/thresholds` | Current thresholds |
| POST | `/api/config/thresholds` | Update thresholds |
| GET | `/api/config/thresholds/suggest` | Auto-tune suggestions |
| POST | `/api/alerts/silence` | Set maintenance window |
| WS | `/ws/system` | Live system stream |
| WS | `/ws/health` | Live health score stream |
| WS | `/ws/processes` | Live process stream |
| WS | `/ws/logs` | Live log stream |

---

## Architecture

```
Collectors (1–60s intervals)
  PsutilCollector   → CPU, mem, disk, net, PSI
  JtopCollector     → GPU, power, thermal, engines   [Jetson only]
  JournaldCollector → systemd journal
  FileLogCollector  → custom log directories
  DmesgCollector    → kernel ring buffer              [opt-in]
  ProcessCollector  → per-process stats
  CrashCollector    → coredump events
        │
        ▼
    hub (in-memory pub/sub)
        │
        ├─→ SQLite (metrics.sqlite)   raw + 10s + 1m downsampled
        ├─→ DuckDB (logs.duckdb)      structured logs, full-text search
        ├─→ Anomaly detector          rolling z-score
        ├─→ Leak detector             RSS slope regression
        └─→ Health scorer             USE+RED penalties
        │
        ▼
  FastAPI (port 9090)
        │
        ├─→ REST endpoints
        ├─→ WebSocket streams
        └─→ Agent chat (3 layers)
        │
        ▼
  React dashboard (dashboard.jsx)
    CDN React 18 + Babel standalone — no build step
```

---

## AI Agent Architecture

Three complementary patterns work together in the agentic chat pipeline.

### Diagram 1 — ReAct Runtime (`ai_core/agent.py`)

The executor LLM follows a **Reasoning + Acting** loop: it emits a thought,
calls one or more tools in parallel, observes the results, then loops until it
produces a final answer. Each tool call is tagged with a CoT reasoning category
(`metric_lookup | log_search | correlation | leak_check | kb_lookup | verify`).

```
User: "why is memory climbing?"
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Agent Runtime (ai_core)                     │
│                                                                 │
│  [Thought — CoT tag: correlation]                               │
│  "Score is low. I need briefing + top processes together."      │
│                                                                 │
│  [Action — parallel dispatch]                                   │
│    get_briefing(window="1h")        ──────────────────────────► │
│    get_top_processes(sort="rss")    ──────────────────────────► │
│                                                                 │
│  [Observation]                                                  │
│    score=54, headline="myapp RSS +200MB/hr"                     │
│    myapp pid=1234 rss=1.8GB, slope=3.2MB/min                   │
│                                                                 │
│  [Thought — CoT tag: leak_check]                               │
│  "Confirm growth trend over 6h before recommending restart."    │
│                                                                 │
│  [Action]  get_process_history(pid=1234, window="6h")           │
│  [Observation]  r²=0.97, slope=3.2MB/min, OOM in ~4h           │
│                                                                 │
│  [Thought — CoT tag: kb_lookup]                                │
│  "Pattern matches memory_leak runbook."                         │
│                                                                 │
│  [Action]  search_kb(query="memory leak rss climbing")          │
│  [Observation]  Steps: 1. confirm r²>0.9  2. restart service   │
│                                                                 │
│  [Final Answer]                                                 │
│    Finding: myapp leaking 3.2MB/min (r²=0.97), OOM in ~4h.    │
│    Action: restart myapp per memory_leak runbook.               │
│    Confidence: high                                             │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼  ┌──────────────────────────────────┐
           │  Verifier LLM (separate call)    │
           │  Verdict{passed, confidence, why}│
           └──────────────────────────────────┘
```

**Code path:** `app/api/chat_v2.py` → `app/agent/aicore_chat.py` → `ai_core.run_agent()`

**CoT reasoning tags** are set per-tool via `HEALTH_TOOL_REASONING_TAGS` in
`aicore_chat.py` and stored on every `ToolCallResult.reasoning_tag` in the
`AgentTrace`. The verifier can audit whether the right reasoning category was
applied before it issues a `Verdict`.

---

### Diagram 2 — RAG Knowledge Base (`app/agent/kb.py` + `embed.py`)

For "how do I fix X" questions, semantic search over local Markdown runbooks
provides remediation steps without requiring an LLM.

```
User query
    │  1. embed query
    ▼
┌──────────────┐   384-dim vector (all-MiniLM-L6-v2)
│  Embeddings  │──────────────────────────────────────┐
└──────────────┘                                      │ 2. ANN search
                                                      ▼
                                          ┌──────────────────────┐
                                          │  FAISS IndexFlatIP   │
                                          │  (data/kb/faiss.idx) │
                                          └──────────┬───────────┘
                                                     │ 3. top-k, score ≥ 0.3
                                                     ▼
                         ┌───────────────────────────────────────┐
                         │  Retrieved KB docs                    │
                         │  [{title, steps[], tags, score}, ...] │
                         └──────────────┬────────────────────────┘
                                        │ 4. inject as context
                                        ▼
                              ┌──────────────────┐
                              │  Agent / LLM     │
                              └────────┬─────────┘
                                       │ 5. final answer
                                       ▼
                                  ┌──────────┐
                                  │ Response │
                                  └──────────┘
```

**KB files:** `data/kb/*.md` — each has YAML frontmatter (`title`, `tags`,
`severity`) and a `## Steps` section parsed into a steps list.

**Auto-stub generation:** when the LLM answers a novel question with no KB
match, `_maybe_save_kb_stub()` writes `data/kb/auto_<slug>.md`. Trigger a
rebuild with `POST /api/kb/reload`.

---

### Diagram 3 — End-to-End Sequence Flow

```
User              dashboard.jsx          chat_v2.py        ai_core           MCP server        SystemHealth API
 │                     │                     │               │                    │                    │
 │ "why memory high?"  │                     │               │                    │                    │
 │────────────────────►│                     │               │                    │                    │
 │                     │── WS /chat_v2/stream►               │                    │                    │
 │                     │                     │──run_agent()──►                    │                    │
 │                     │                     │               │──spawn stdio───────►                    │
 │                     │                     │               │  list_tools()       │                    │
 │                     │                     │               │◄──10 tool defs──────│                    │
 │                     │                     │               │                    │                    │
 │                     │◄──{type:"log"}──────│               │                    │                    │
 │                     │  (streaming steps)  │──LLM call─────► (Groq/Ollama)      │                    │
 │                     │                     │◄──tool_calls──│                    │                    │
 │                     │                     │               │──call_tool─────────►                    │
 │                     │                     │               │  get_briefing()     │──GET /api/briefing►│
 │                     │                     │               │                    │◄──JSON─────────────│
 │                     │                     │               │◄──observation───────│                    │
 │                     │                     │               │  (loop max 12 turns)│                    │
 │                     │                     │               │──final answer───────►                    │
 │                     │                     │──verify()─────► (Gemini verifier)   │                    │
 │                     │                     │◄──Verdict─────│                    │                    │
 │                     │                     │──render_ui()──► (Gemini UI)         │                    │
 │                     │◄──{type:"done",     │               │                    │                    │
 │                     │   trace,verdict,ui}─│               │                    │                    │
 │◄────────────────────│                     │               │                    │                    │
 │  rendered cards     │                     │               │                    │                    │
```

**Three independent LLM roles:**
1. **Executor** (Groq/Ollama) — drives the ReAct tool-use loop, reasoning=off for speed
2. **Verifier** (Gemini) — separate call, checks evidence → issues `Verdict`, reasoning=medium
3. **UI Composer** (Gemini) — turns `AgentTrace` into prefab dashboard cards

---

### Chain of Thought (CoT) in `health_prompt.md`

The system prompt enforces explicit CoT before every tool call:

```
REASONING PROCESS (before every tool call):
- Tag your reasoning type: [metric_lookup | log_search | correlation
                            | leak_check | kb_lookup | verify]
- State what you suspect and what evidence would confirm/refute it
- Explain why you chose this tool over alternatives
```

Self-verification rules after each result:
1. Are units sensible? (% in [0,100], MB > 0, °C plausible)
2. Is the value consistent with the briefing health score?
3. Spike vs. sustained? (use `get_metric_history` to confirm)

**Prompt quality checklist** (9/9 criteria met):

| Criterion | Pass | Evidence in `health_prompt.md` |
|-----------|------|--------------------------------|
| Explicit reasoning instructions | ✅ | "REASONING PROCESS (before every tool call): State what you suspect..." |
| Structured output format | ✅ | "FINAL ANSWER FORMAT: 1. Finding 2. Evidence 3. Action 4. Confidence" |
| Separation of reasoning and tools | ✅ | Separate `REASONING PROCESS` + `TOOL RULES` sections; think → pick tool → state observation |
| Conversation loop support | ✅ | Worked example shows Turn 1 / Turn 2 / Turn 3 / Final with context carried forward |
| Instructional framing | ✅ | Full multi-turn example with expected reasoning tags and output at each turn |
| Internal self-checks | ✅ | "SELF-VERIFICATION (after each result): units sensible? consistent with score? spike vs. sustained?" |
| Reasoning type awareness | ✅ | "Tag your reasoning type: [metric_lookup \| log_search \| correlation \| leak_check \| kb_lookup \| verify]" |
| Error handling / fallbacks | ✅ | HTTP 503 → `TOOL_ERROR` + stop; empty list → widen window; uncertain → 2-3 hypotheses ranked by evidence |
| Overall clarity and robustness | ✅ | "never guess current state", "do not invent data", threshold anchoring reduce hallucination |

To re-run programmatically:
```python
from ai_core import evaluate_prompt
from app.agent.health_prompt import HEALTH_PROMPT  # or read the .md directly

result = await evaluate_prompt(HEALTH_PROMPT)
print(result.model_dump_json(indent=2))
```

---

## Configuration

All settings are environment variables. See [`.env.example`](.env.example) for the full list.

Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `9090` | Server port |
| `SH_DATA_DIR` | `./data` | SQLite + DuckDB storage |
| `SH_OLLAMA_URL` | — | Ollama server URL |
| `SH_LLAMA_URL` | — | llama.cpp server URL |
| `SH_LLM_MODEL` | `llama3.2:3b` | Model name (Ollama) |
| `SH_EMBED_MODEL` | `all-MiniLM-L6-v2` | KB embedding model |
| `SH_KB_DIR` | `./data/kb` | KB markdown files |
| `SH_ALERT_WEBHOOK_URL` | — | Slack-compatible webhook |
| `SH_ENABLE_DMESG` | — | Enable kernel log collector |
| `SH_LOG_APP_DIRS` | — | Extra log directories to tail |

---

## Knowledge Base

Add runbook markdown files to `data/kb/` to extend the chat agent:

```markdown
---
title: "High CPU Usage"
tags: [cpu, performance]
severity: warn
---

# High CPU Usage

## Steps
1. Run `top` or check `/api/processes`
2. Look for processes with sustained >80% CPU
3. Check `dmesg` for thermal throttling
4. Reduce workload or increase cooling
```

Reload without restart:
```bash
curl -X POST http://localhost:9090/api/kb/reload
```

Notes:

- KB search requires `pip install -e ".[kb]"`
- The embed/index build uses `sentence-transformers` + FAISS locally
- The KB directory defaults to `data/kb/` and can be overridden with `SH_KB_DIR`
- Auto-generated KB stubs are written as `auto_*.md` and are gitignored

## Repository Layout

```
app/                 FastAPI app, collectors, analytics, KB, LLM routing
tests/               Pytest coverage for API, analytics, chat, KB flow
tools/               Utility scripts, including pre-push verification
data/kb/             Markdown runbooks used by the chat KB
design/wireframes/   Prototype wireframes and design canvas assets
design/docs/         Design-specific documentation
dashboard.*          Production dashboard assets
```

---

## Running Tests

```bash
bash tools/test_before_push.sh
```

This is the required local verification step before pushing changes.

Single module:
```bash
pytest tests/test_chat.py -v
```

Useful focused runs:

```bash
pytest tests/test_kb_chat_flow.py -v
pytest tests/test_analytics.py -v
```

---

## Platform Notes

### Jetson
- Requires `jtop` (`jetson-stats` package) for GPU/power/thermal metrics
- `SH_ENABLE_DMESG=1` needs `adm` group or root for `/dev/kmsg`
- PSI (`/proc/pressure/`) available on JetPack 5+ (kernel 5.10+)

### Ubuntu
- GPU tab hidden automatically when `jtop` unavailable
- All other features work identically

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Pull requests must pass `ruff`,
`pytest`, and the secrets-scan pre-commit hook documented in
[SECURITY.md](SECURITY.md#pre-push-checklist).

## Security

> ⚠ **SystemHealth has no authentication.** It is designed for trusted
> localhost / LAN use only. Do **not** expose port 9090 to the public
> internet without a reverse proxy and auth in front of it.

- **Reporting**: see [SECURITY.md](SECURITY.md) — use GitHub Security
  Advisories or the maintainer email, never a public issue.
- **Secrets**: `.env`, API keys, webhook URLs, certificates, and cloud
  credentials are excluded by `.gitignore`. Copy `.env.example` →
  `.env` locally and never commit it. Run the pre-push checklist in
  [SECURITY.md](SECURITY.md#pre-push-checklist) before every push.
- **Data egress**: by default the agent calls Ollama on `127.0.0.1` and
  no host data leaves the machine. If you configure a cloud LLM
  provider key, process names, log snippets, and metric values will be
  sent to that provider — review their retention policy first.
- **Read-only agent**: MCP tools only *read* the host. Report any
  endpoint that can mutate state without explicit user confirmation.

If you find that a secret was committed by accident, rotate it
immediately and follow the recovery steps in
[SECURITY.md](SECURITY.md#if-a-secret-was-committed).

## License

Licensed under the **Apache License 2.0** — see [LICENSE](LICENSE) for the
full text.

```
Copyright 2025 SystemHealth contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
```

Third-party components retain their own licenses; see headers in
individual files and `uv.lock` for the dependency graph.
