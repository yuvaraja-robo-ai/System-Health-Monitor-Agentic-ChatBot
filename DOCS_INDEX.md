# SystemHealth Documentation Index

Complete guide to analyzing custom application logs with AI-powered diagnostics on Jetson Nano/Orin.

---

## 📚 Documentation Files

### For Getting Started (Start Here!)

**[QUICKSTART_CUSTOM_LOGS.md](QUICKSTART_CUSTOM_LOGS.md)** (5 min read)
- One-click setup for your Jetson app logs
- 3 simple steps to get dashboard + KB working
- Real example: inference app → KB → diagnostics
- **Best for:** Users who want it working NOW

### For Complete Understanding

**[LOG_ANALYSIS_README.md](LOG_ANALYSIS_README.md)** (20 min read)
- Complete architecture: logs → storage → agent → LLM
- How collectors work (journald, file, dmesg)
- Real dmesg examples with full KB entries
- Auto-generate KB from live errors
- Pattern extraction & knowledge base creation
- Testing & debugging guide
- **Best for:** Understanding the full system

### For Kernel/System Logs

**[DMESG_SETUP.md](DMESG_SETUP.md)** (10 min read)
- Kernel logs (dmesg) analysis on Jetson
- Real examples: OOM killer, thermal throttle, power brownout
- How to enable dmesg collector
- Pre-built KB entries for common issues
- **Best for:** System-level diagnostics (Thermal, OOM, power)

### Reference Documents

**[LOG_ANALYSIS_README.md](LOG_ANALYSIS_README.md)** — Complete reference
- Sections: How to configure, test, troubleshoot
- Real dmesg log examples
- Step-by-step KB creation workflow
- API endpoints reference

---

## 🔧 Tools

### Auto-Generate Knowledge Base from Live Logs

**[tools/gen_kb_stubs.py](tools/gen_kb_stubs.py)**
```bash
# See what error patterns exist
python3 tools/gen_kb_stubs.py --service myapp --hours 6 --min-count 2

# Output: creates data/kb/stub_myapp_*.md files (you fill in fixes)
```

### Dmesg/Kernel Log Collector

**[app/collectors/dmesg_collector.py](app/collectors/dmesg_collector.py)**
- Optional collector (not enabled by default)
- Parses kernel logs into: kernel-thermal, kernel-memory, kernel-power, etc.
- Enable: add `DmesgCollector()` to `app/main.py`

---

## 🚀 Quick Start (3 Steps)

### 1. Configure Your App's Log Path

```bash
export SH_LOG_APP_DIRS="/var/log/myapp/app.log"
# Or multiple paths: "/var/log/app1.log:/opt/app2/logs/app.log"
```

### 2. Start SystemHealth + Your App

```bash
cd /path/to/System-Health-Monitor-Agentic-ChatBot
python3 app/main.py &
python3 /opt/myapp/run.py &
```

### 3. After 5-10 Minutes: Auto-Generate KB

```bash
# See errors that occurred
python3 tools/gen_kb_stubs.py --service myapp --hours 1

# Edit data/kb/stub_myapp_*.md (fill in fixes)

# Reload KB
curl -X POST http://localhost:9999/api/kb/reload
```

**Done.** Open http://localhost:9999/dashboard.html → Diagnose tab → ask about your errors.

---

## 📊 How It Works (30 Seconds)

```
Your App
  ↓ (writes logs to file or systemd)
FileLogCollector / JournaldCollector
  ↓ (parses severity, extracts service name)
DuckDB (data/logs.duckdb)
  ↓ (stored as: ts, service, level, message)
  
Dashboard:
  • Logs tab: live tail, search by service/level/regex
  • Services tab: error counts per app
  • App Focus: per-app error details + AI analysis

Knowledge Base:
  • You create .md files in data/kb/
  • Each KB entry has: title, tags, log patterns, steps
  • Semantic search finds matching KB entries
  
Agent (Diagnose tab):
  • Sees live errors from DuckDB
  • Searches KB for matching patterns
  • Sends digest + KB matches to LLM
  • LLM recommends fixes (from KB steps)
```

---

## 💾 Key Files & Directories

| Path | Purpose |
|------|---------|
| `data/logs.duckdb` | All ingested logs (auto-created) |
| `data/kb/` | Knowledge base .md files |
| `data/kb/meta.json` | KB index (auto-generated) |
| `data/pinned_apps.json` | Pinned app list |
| `tools/gen_kb_stubs.py` | Auto-generate KB from live logs |
| `app/collectors/dmesg_collector.py` | Kernel log parser (optional) |
| `app/api/diagnose.py` | Diagnose endpoint + KB reload |
| `http://localhost:9999/dashboard.html` | Main dashboard |

---

## 🎯 Recommended Reading Path

**If you just want logs + KB working:**
```
1. QUICKSTART_CUSTOM_LOGS.md (5 min)
2. Set env var + start app
3. Done
```

**If you want to understand how it works:**
```
1. LOG_ANALYSIS_README.md (20 min)
2. QUICKSTART_CUSTOM_LOGS.md (5 min)
3. Try it out
```

**If you want kernel/system diagnostics too:**
```
1. QUICKSTART_CUSTOM_LOGS.md (5 min)
2. DMESG_SETUP.md (10 min)
3. Enable dmesg collector
4. Create dmesg KB entries
```

---

## 🔗 Related Files

| File | Purpose |
|------|---------|
| `app/collectors/jtop_collector.py` | Extended GPU metrics (power rails, EMC, engines, swap) |
| `app/api/config.py` | Custom app pinning API |
| `app/runtime.py` | Monitored apps management |
| `dashboard.jsx` | New Jetson tab, CPU per-core, app pinning |
| `dashboard.css` | Styles for sensors, cores, pins |
| `data/kb/meta.json` | 6 KB entries (was 3) |

---

## ❓ Troubleshooting

### Logs not appearing in dashboard
```bash
# Check log file exists
ls -lh /var/log/myapp.log

# Check configured
echo $SH_LOG_APP_DIRS

# Check DuckDB
python3 << 'EOF'
import duckdb
con = duckdb.connect('data/logs.duckdb', read_only=True)
result = con.execute("SELECT COUNT(*) FROM logs").fetchone()
print(f"Total logs: {result[0]}")
EOF
```

### KB not matching errors
```bash
# Verify KB loaded
curl http://localhost:9999/api/kb/entries | head

# Check .md format (must have "# Title" + "## Steps")
grep -l "^#\|^##" data/kb/*.md
```

### Agent says "no LLM configured"
```bash
# Set LLM endpoint
export SH_OLLAMA_URL=http://localhost:11434
# OR
export SH_LLAMA_URL=http://localhost:8000
```

See **Troubleshooting** section in LOG_ANALYSIS_README.md for detailed debugging.

---

## 📖 Full Documentation

- **Architecture & Patterns:** LOG_ANALYSIS_README.md
- **Quick Setup:** QUICKSTART_CUSTOM_LOGS.md
- **Kernel Logs:** DMESG_SETUP.md
- **API Reference:** In code: `app/api/diagnose.py`, `app/api/config.py`
- **Collectors:** `app/collectors/`
- **Tools:** `tools/gen_kb_stubs.py`

---

## 🎓 Real Example Workflows

### Workflow 1: Inference App Crashes

```
1. App running → CUDA out of memory error → SystemHealth captures
2. Dashboard Logs tab → see error repeated 12 times
3. Run: python3 tools/gen_kb_stubs.py --service myinference
4. Output: stub_myinference_abc123.md created with error message
5. Edit: fill in "## Steps" with fixes (reduce batch size, restart)
6. Reload: curl -X POST .../kb/reload
7. Test: Diagnose tab → "Why does inference crash?" → KB match found
8. Result: Agent suggests reducing batch size (from your KB)
```

### Workflow 2: Thermal Throttling on Jetson

```
1. Jetson running inference → SoC temp > 85°C → dmesg records throttle
2. Enable dmesg collector → kernel-thermal service captured
3. Run: python3 tools/gen_kb_stubs.py --service kernel-thermal --hours 2
4. Output: stub_kernel_thermal_xyz789.md with thermal event
5. Edit: fill in steps (check airflow, reduce GPU load, lower power mode)
6. Reload: curl -X POST .../kb/reload
7. Test: Diagnose tab → "why is GPU slow?" → thermal throttle KB match
8. Result: Agent suggests checking airflow + reducing GPU load
```

---

## 🔄 API Endpoints (After Setup)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/logs` | GET | Query logs: `?service=myapp&level=ERR&since=3600` |
| `/api/logs?service=X` | GET | Logs for specific service |
| `/api/units?window=6h` | GET | Service state + error counts |
| `/api/apps?window=24h` | GET | App-level aggregation |
| `/api/diagnose` | POST | Run diagnostics with LLM |
| `/api/kb/reload` | POST | Reload KB after editing .md files |
| `/api/config/apps` | GET/POST | Manage pinned apps |
| `/ws/logs` | WS | Live log stream |

See LOG_ANALYSIS_README.md for detailed API examples.

---

## 💬 Need Help?

| Question | Answer Location |
|----------|-----------------|
| "How do I set up my app's logs?" | QUICKSTART_CUSTOM_LOGS.md |
| "How does the system work?" | LOG_ANALYSIS_README.md |
| "How do I analyze dmesg?" | DMESG_SETUP.md |
| "Why aren't logs showing?" | LOG_ANALYSIS_README.md → Troubleshooting |
| "How do I create a KB entry?" | LOG_ANALYSIS_README.md → Creating KB Entries |
| "Can I parse custom log formats?" | LOG_ANALYSIS_README.md → Option B: Custom Collector |

---

## ✅ What's Included

✓ Jetson GPU metrics (power rails, EMC, engine load)
✓ Jetson thermal deep-dive tab
✓ CPU per-core visualization
✓ Custom app pinning
✓ File log collection (any path)
✓ Systemd journal collection
✓ Kernel log collection (dmesg)
✓ Auto-generate KB from live errors
✓ KB semantic search + LLM integration
✓ Complete documentation (3 guides)
✓ Tools for KB generation + pattern extraction

---

**Start here:** [QUICKSTART_CUSTOM_LOGS.md](QUICKSTART_CUSTOM_LOGS.md)

**Deep dive:** [LOG_ANALYSIS_README.md](LOG_ANALYSIS_README.md)

**Kernel logs:** [DMESG_SETUP.md](DMESG_SETUP.md)
