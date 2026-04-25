# Agent Chat Architecture

PlantUML sequence diagram:

- [docs/agent-chat-sequence.puml](/tmp/System-Health-Monitor-Agentic-ChatBot/docs/agent-chat-sequence.puml:1)

How the chatbot works, how agent code is wired in, and what can be improved.

---

## 1. Overview

The chat system answers questions about the running system using three layers,
each independent. No layer requires the previous one to succeed. No LLM is
required for the first two layers.

```
User question
      │
      ▼
┌─────────────────────────────────────┐
│  Layer 1: Direct Metric Answer      │  ← live hub data, instant (<5ms)
│  app/api/chat.py  _direct_answer()  │
└─────────────┬───────────────────────┘
              │ no match
              ▼
┌─────────────────────────────────────┐
│  Layer 2: KB Semantic Search        │  ← FAISS + sentence-transformers
│  app/agent/kb.py  query()           │
└─────────────┬───────────────────────┘
              │ no match or needs reasoning
              ▼
┌─────────────────────────────────────┐
│  Layer 3: LLM Reasoning             │  ← Ollama or llama.cpp (optional)
│  app/agent/llm.py  chat()           │    live data injected as context
└─────────────────────────────────────┘
```

---

## 2. File Map

| File | Role |
|------|------|
| `app/api/chat.py` | HTTP endpoint, orchestrates all 3 layers + agentic loop |
| `app/agent/diagnose.py` | Collects live system context into a text digest (async) |
| `app/agent/kb.py` | Loads KB markdown files, builds FAISS index, runs semantic search |
| `app/agent/embed.py` | Wraps `sentence-transformers` to produce embedding vectors |
| `app/agent/llm.py` | HTTP client for Ollama (`/api/chat`) and llama.cpp (`/v1/chat/completions`) |
| `app/agent/keywords.json` | **Keyword routing config** — all topic/metric/reasoning keyword groups |
| `app/agent/keywords.py` | Thin loader for `keywords.json` with `lru_cache` |
| `data/kb/*.md` | Runbook markdown files (manually written + auto-generated stubs) |
| `data/kb/faiss.index` | Persisted FAISS flat inner-product index |
| `data/kb/meta.json` | Metadata for each KB doc (title, tags, steps) |

---

## 3. Layer 1 — Direct Metric Answer

**File:** `app/api/chat.py` → `_direct_answer(question)`

**How it works:**

1. Pulls live snapshots from the in-memory `hub` (no DB query, no I/O).
2. Matches the question against keyword patterns using word-boundary regex.
3. Formats and returns structured data as plain text.

```
hub.latest("system")  → CPU, memory, disk, network, PSI pressure, temps
hub.latest("jetson")  → GPU load, power rails, SoC temp, engines, fan
hub.latest("health")  → health score, driver penalties
hub.latest("processes") → top processes by CPU/RSS
hub.latest("crashes") → crash counts per service
anomaly_detector.current() → active z-score anomalies
leak_detector.current()    → active memory leak suspects
```

**Named-process routing (runs first):**

If a running process name appears verbatim in the question and it's not a
reasoning question, the answer is scoped to that process:

```
"what is llama-server cpu usage"
  → matches "llama-server" in process list → returns process-specific stats

"how can I optimize llama-server memory"
  → "optimize" is a reasoning keyword → falls through to LLM
```

**Keyword routing (word-boundary regex, config-driven):**

All keyword groups are defined in `app/agent/keywords.json` — edit that file
to add new topics or synonyms without touching Python code.

| Topic | Group key | Sample keywords |
|-------|-----------|-----------------|
| CPU | `cpu` | cpu, processor, core, utilization |
| Memory | `memory` | memory, mem, ram |
| Swap | `swap` | swap |
| Disk | `disk` | disk, storage, space, filesystem, mount |
| Temperature | `temperature` | temp, thermal, hot, heat, celsius, degrees |
| GPU | `gpu` | gpu, graphics, cuda, vram |
| Power | `power` | power, watt, energy, consumption |
| Fan | `fan` | fan, cooling, rpm |
| Network | `network` | network, net, bandwidth, rx, tx, throughput |
| Uptime | `uptime` | uptime, up time, running for, how long |
| Health | `health` | health, score, overall status, system status |
| PSI | `pressure` | pressure, psi, stall |
| Anomalies | `anomaly` | anomaly, anomalies, spike, unusual, abnormal |
| Leaks | `leak` | leak, memory leak, rss climbing |
| Crashes | `crash` | crash, crashes, killed, oom kill, segfault |
| Processes | `process` | process, top process, pid, what is running |
| Load avg | `load_average` | load average, load avg, load 1, load 5 |
| Engines | `emc` | emc, memory controller, dla, nvenc, nvdec, vic |

**Reasoning detection (`reasoning` group in `keywords.json`):**

Questions containing reasoning keywords (`why`, `how can`, `optimize`, `fix`,
`diagnose`, `recommend`, etc.) bypass the direct-answer layer and go straight
to the LLM agentic loop.

**Output example** (question: "what is the CPU usage"):
```
CPU: 67.3%
load avg 1.24 / 1.18 / 0.95
6 cores
saturation 31%
per-core: c0:72%  c1:61%  c2:58%  c3:70%  c4:65%  c5:68%
ctx-switches 12044/s
```

**Backend tag returned:** `"direct"` (or `"ollama+direct"` when LLM refines)

---

## 4. Layer 2 — KB Semantic Search

**Files:** `app/agent/kb.py`, `app/agent/embed.py`

**How it works:**

### 4a. KB Build (`kb.build()`)

Called once at server startup (`app/main.py` lifespan). Rebuilds only if KB
directory hash changes (SHA-256 over all `.md` filenames + contents).

```
data/kb/*.md
      │
      ▼  _parse_doc()
      │  → title, tags, steps[], full text
      │
      ▼  embed.embed(texts)
      │  → SentenceTransformer("all-MiniLM-L6-v2")
      │  → 384-dim float32 vectors, L2-normalized
      │
      ▼  faiss.IndexFlatIP(384)
         → inner product = cosine similarity (normalized vectors)
         → saved to data/kb/faiss.index
         → metadata saved to data/kb/meta.json
```

### 4b. KB Query (`kb.query(text, k=3)`)

```
question + context digest
      │
      ▼  embed.embed([text])          → 384-dim query vector
      │
      ▼  faiss_index.search(vec, k)   → top-k nearest neighbors
      │
      ▼  filter score < 0.3           → discard weak matches
      │
      ▼  return [{title, score, steps, tags}, ...]
```

### 4c. KB Markdown Format

Each file in `data/kb/` follows this structure:

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

The `## Steps` section is parsed into a list and returned with each KB match.
Steps are displayed directly in the chat without LLM involvement.

### 4d. Auto-generated KB Stubs

When LLM answers a question that had no KB match, `_maybe_save_kb_stub()` in
`chat.py` writes a minimal markdown file to `data/kb/auto_<slug>.md`. These
stubs contain the question, live context snapshot, and LLM answer as a draft.
Max 50 auto stubs. Duplicates skipped by slug match.

**Trigger a KB rebuild after new stubs are added:**
```bash
curl -X POST http://localhost:9090/api/kb/reload
```

---

## 5. Layer 3 — LLM Reasoning

**Files:** `app/agent/llm.py`, `app/config.py`

**How it works:**

When LLM is configured (`SH_OLLAMA_URL` or `SH_LLAMA_URL`), the chat endpoint
builds a structured prompt containing:

1. **Extracted metric data block** — output of `_direct_answer()` if it matched
2. **Live system context digest** — from `diagnose.collect_context()` (processes,
   logs, leaks, crashes, health score)
3. **Relevant KB steps** — from `kb.query()`
4. **Conversation history** — all previous `user`/`assistant` turns

```
[Extracted metric data for this question]
CPU: 67.3%
load avg 1.24 / 1.18 / 0.95
...

[Live system context]
Host window: last 300s. Health score: 72/100.
CPU 67.3% load 1.24. Mem used 2.1/4.0G.
Top RSS: myapp(312M) python3(88M) ...

[Relevant KB]
[KB: High CPU Usage] Check top processes; look for thermal throttling; ...

User: why is CPU so high?
```

**Ollama** (`/api/chat` with `messages` array — full multi-turn):
```python
POST /api/chat
{"model": "llama3.2:3b", "messages": [...], "stream": false}
```

**llama.cpp** (`/v1/chat/completions` with `messages` array):
```python
POST /v1/chat/completions
{"model": "...", "messages": [...], "stream": false}
```

**Backend tag:** `"ollama+direct"` (LLM refined live data), `"ollama"` (pure
reasoning), `"kb"` (KB-only, no LLM used).

---

## 6. Context Collection (`diagnose.collect_context`)

**File:** `app/agent/diagnose.py`

Called for Layer 2 and 3 only (not Layer 1 — Layer 1 reads hub directly).

Collects into a single dict:
- `system` — current CPU/mem/net/disk snapshot from hub
- `health` — health score + driver penalties
- `crashes` — crash counts and recent crash events from SQLite
- `leaks` — active flagged memory leaks
- `top_procs` — top 15 processes by CPU from hub
- `log_clusters` — top error log clusters from DuckDB (last N seconds)
- `unit_events` — systemd state-change events from SQLite
- `cpu_series / mem_series` — historical time series from SQLite

`_digest_text()` converts this to a compact multi-line string that fits in the
LLM context window (~500 tokens).

---

## 7. Configuration

```bash
# LLM backend (optional — Layers 1+2 work without it)
SH_OLLAMA_URL=http://localhost:11434   # Ollama server
SH_LLAMA_URL=http://127.0.0.1:8080     # llama.cpp server
SH_LLM_MODEL=llama3.2:3b              # model name for Ollama
SH_LLM_TIMEOUT_S=30                   # LLM request timeout

# KB + embeddings (optional — Layer 2 requires these)
SH_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
SH_KB_DIR=/path/to/kb                 # default: data/kb/

# Install KB deps
pip install -e ".[kb]"    # sentence-transformers + faiss-cpu
```

---

## 8. Data Flow Diagram

```
Browser (AgentChat component in dashboard.jsx)
  │
  │  POST /api/chat
  │  {"messages": [{role,content}...], "scope": {"window":"5m"}}
  │
  ▼
app/api/chat.py  chat_endpoint()
  │
  ├─→ _direct_answer(question)
  │     └─ hub.latest("system"|"jetson"|"health"|"processes"|"crashes")
  │        anomaly_detector.current()
  │        leak_detector.current()
  │        → plain text OR None
  │
  ├─→ diagnose.collect_context(scope)          [if LLM or KB needed]
  │     ├─ hub.latest(...)
  │     ├─ sdb.history(metric, since, now)     [SQLite]
  │     ├─ ldb.cluster_logs(since)             [DuckDB]
  │     └─ sdb.recent_events(kind, since)      [SQLite]
  │
  ├─→ kb.query(question + digest, k=3)
  │     ├─ embed.embed([text])                 [sentence-transformers]
  │     └─ faiss_index.search(vec, k)
  │
      └─→ llm.chat(messages, system=SYSTEM_PROMPT) [if configured]
        ├─ _ollama_chat()  → POST /api/chat    [Ollama]
        └─ _llama_chat()   → POST /v1/chat/completions  [llama.cpp]
  │
  ▼
{"answer": "...", "backend": "direct|kb|ollama+direct|none", "latency_ms": N}
```

---

## 9. What Can Be Improved

### 9.1 Smarter Query Routing

**Current:** Keyword regex decides Layer 1 vs Layer 2/3. Named-process routing
now handles `"llama-server cpu usage"` vs `"optimize llama-server memory"` via
reasoning-keyword detection. All keywords are in `app/agent/keywords.json`.

**Remaining gap:** Paraphrased questions ("show me how busy the processor is")
miss the `cpu` keyword and fall to Layer 2/3 unnecessarily.

**Fix options:**
- Add more synonyms to `keywords.json` (zero-code, low risk)
- Lightweight intent classifier (TF-IDF or small embedding similarity against
  canonical question templates)

---

### 9.2 Streaming LLM Responses

**Current:** Waits for full LLM response before returning (blocking, can take
10–30 seconds for longer answers).

**Fix:** Use Server-Sent Events (SSE) or WebSocket streaming:

```python
# Ollama supports stream=true
POST /api/chat  {"stream": true}
→ newline-delimited JSON chunks

# Dashboard: EventSource or ReadableStream
const stream = await fetch("/api/chat/stream", {...});
const reader = stream.body.getReader();
```

Add `GET /api/chat/stream` endpoint that proxies streaming chunks. Dashboard
updates the chat bubble in real time as tokens arrive.

---

### 9.3 Conversation Memory Across Sessions

**Current:** Conversation history lives only in React state — lost on page
refresh. Server has no memory of previous turns.

**Fix:** Persist conversation to SQLite per session ID:

```python
# New table
CREATE TABLE chat_sessions (
    session_id TEXT,
    ts INTEGER,
    role TEXT,
    content TEXT
);

# GET /api/chat/history?session_id=abc → last 20 turns
# POST /api/chat includes session_id, server appends to history
```

Browser stores `session_id` in `localStorage`.

---

### 9.4 Tool-Use / Function Calling ✅ Implemented

**Implemented in `_run_agentic_chat` (`app/api/chat.py`).**

The agentic loop follows the pattern: seed context → LLM call → tool call →
result → next LLM call (with full history) → repeat up to `max_iterations`.

```
messages = [context, ack]               ← grounding (collected once)
         + [user turn 1]                ← original question

Iteration 1: LLM → {"tool_name": "get_live_context", ...}
messages += [assistant, tool_result]

Iteration 2: LLM → {"tool_name": "search_kb", ...}
messages += [assistant, tool_result]

Iteration 3: LLM → {"answer": "..."}   ← final response
```

Tools available to the LLM agent:

| Tool | Returns |
|------|---------|
| `get_direct_answer(question)` | Live metric snapshot for a specific query |
| `get_live_context(window, services, pids)` | Full diagnostic digest |
| `search_kb(query, window, services, pids)` | KB runbook matches + steps |
| `get_log_status(window, level, service, regex)` | Log ingestion status |
| `get_log_clusters(window, limit)` | Grouped repeated error signatures |

**Remaining gap:** `restart_service` and other write operations are not
implemented — those require explicit user approval flow (out of scope).

---

### 9.5 KB Quality Improvement

**Current:** KB is static markdown files. Auto-generated stubs are unverified
drafts that could contain incorrect LLM answers.

**Fix options:**

- **Confidence scoring:** Mark auto stubs with `verified: false` in frontmatter.
  Show unverified stubs differently in KB match results.
- **Feedback loop:** Add thumbs up/down to each chat answer. On thumbs-down,
  open KB editor to correct the relevant stub.
- **Cluster-driven stubs:** Run `tools/gen_kb_stubs.py` on a schedule against
  DuckDB log clusters — generates stubs from real observed error patterns.
- **GraphRAG upgrade:** Replace flat FAISS with a knowledge graph where entities
  (services, metrics, symptoms) link to each other. Better multi-hop reasoning
  ("high CPU + memory pressure together → likely OOM condition").

---

### 9.6 Anomaly-Triggered Chat Context

**Current:** User must ask questions manually.

**Fix:** When anomaly detector fires, auto-inject an alert message into the chat:

```javascript
// dashboard.jsx: listen to /ws/anomalies
useWS("/ws/anomalies", env => {
  if (env.data?.current?.length > 0 && !chatOpen) {
    setChatOpen(true);
    // inject system message: "Anomaly detected: cpu.total z=4.2"
  }
});
```

Server side: anomaly webhook could POST to `/api/chat` to pre-generate a
diagnostic response and cache it, so when user opens chat it's already there.

---

### 9.7 Multi-Model Support

**Current:** Single model configured globally.

**Fix:** Route by question type:
- Fast small model (llama3.2:1b) → simple metric explanation, rephrasing
- Larger model (llama3.2:8b or mistral) → deep diagnostic reasoning
- Embedding model stays independent (`all-MiniLM-L6-v2` is already separate)

```python
# config
SH_LLM_FAST_MODEL=llama3.2:1b
SH_LLM_REASONING_MODEL=mistral:7b

# routing
model = settings.llm_reasoning_model if _needs_llm(question) else settings.llm_fast_model
```

---

### 9.8 Silence / Rate-Limit Awareness

**Current:** Chat has no knowledge of alert silence windows.

**Fix:** Inject silence status into system prompt so LLM knows maintenance mode
is active and adjusts its urgency tone.

```python
from app.api.silence import get_silence
silence = get_silence()
if silence["silenced"]:
    system_prompt += f"\nNote: alerts silenced until {silence['until']} (maintenance window)."
```

---

## 10. Summary

| Layer | Requires | Latency | Best for |
|-------|----------|---------|----------|
| Direct | Nothing (hub in-memory) | <5ms | "what is X right now" |
| KB | sentence-transformers + faiss | 50–200ms | "how do I fix X" |
| LLM | Ollama or llama.cpp running | 2–30s | "why is X happening" |

The design intentionally degrades gracefully: a Jetson with no GPU-heavy LLM
still gets instant metric answers and runbook lookup. The LLM adds reasoning
when available but is never required for operational visibility.
