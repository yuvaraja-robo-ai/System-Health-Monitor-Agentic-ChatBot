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

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.

## License

Apache 2.0 — see [LICENSE](LICENSE).
