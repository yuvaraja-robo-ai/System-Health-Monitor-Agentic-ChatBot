# Log Analysis & Knowledge Base Setup

Complete guide for analyzing custom application logs, system logs (dmesg, journald), and creating a knowledge base for the LLM agent.

---

## Table of Contents

1. [Log Sources](#log-sources)
2. [How Logs Flow to Agent](#how-logs-flow-to-agent)
3. [Configuring Custom Log Sources](#configuring-custom-log-sources)
4. [Real Examples: dmesg](#real-examples-dmesg)
5. [Creating Knowledge Base Entries](#creating-knowledge-base-entries)
6. [Auto-Generate KB from Live Logs](#auto-generate-kb-from-live-logs)
7. [Testing & Debugging](#testing--debugging)

---

## Log Sources

### 1. Systemd Journal (Automatic)

Any app running as systemd service auto-logs to journalctl.

```bash
# Your systemd service
[Unit]
Description=MyApp Inference Engine

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/myapp/inference.py
StandardOutput=journal
StandardError=journal
```

Logs appear immediately:
```bash
journalctl -u myapp.service -f  # live tail
journalctl -u myapp.service -n 100  # last 100 lines
```

**SystemHealth captures:** Automatic. No config needed.

---

### 2. File Logs (Any Path)

App writes to `/var/log`, `/home/user/app/logs`, `/tmp`, etc.

```bash
# Typical app logging
python3 myapp.py > /var/log/myapp/app.log 2>&1

# Or with rotation
python3 myapp.py 2>&1 | tee /var/log/myapp/$(date +%Y%m%d).log
```

**Configure SystemHealth:**

```bash
# Option A: Environment variable
export SH_LOG_APP_DIRS="/var/log/myapp/app.log:/var/log/inference.log"

# Option B: .env file
echo "SH_LOG_APP_DIRS=/var/log/myapp/app.log:/opt/myapp/logs/current.log" >> .env

# Option C: Multiple paths (colon-separated)
export SH_LOG_APP_DIRS="/var/log/app1.log:/var/log/app2.log:/home/user/custom.log"
```

Then restart:
```bash
pkill -f "python3 app/main.py"
python3 app/main.py &
```

---

### 3. Kernel Logs (dmesg)

Jetson kernel messages: thermal throttling, OOM killer, GPU errors, power events.

```bash
# View dmesg
dmesg | tail -50

# Save to file for analysis
dmesg > /tmp/dmesg.log
```

**Configure SystemHealth to read dmesg:**

Create a dmesg collector. See [Dmesg Collector Setup](#dmesg-collector-setup) below.

---

## How Logs Flow to Agent

```
┌─────────────────────────────────────────────────────────────┐
│ LOG SOURCES                                                 │
├─────────────────────────────────────────────────────────────┤
│ 1. App writes to stdout/stderr  → systemd journal           │
│ 2. App writes to file           → FileLogCollector reads    │
│ 3. Kernel messages              → dmesg collector reads     │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ PARSING & STORAGE                                           │
├─────────────────────────────────────────────────────────────┤
│ • Extract: timestamp, service, severity, message            │
│ • Normalize severity: ERROR|WARN|INFO|DEBUG                 │
│ • Store in DuckDB: data/logs.duckdb                         │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ ANALYSIS                                                    │
├─────────────────────────────────────────────────────────────┤
│ Dashboard:                                                  │
│  • Logs tab:    live tail, filter by service/level/regex    │
│  • Services:    error counts, trends                        │
│  • App Focus:   app-specific errors + analysis              │
│                                                             │
│ Agent (when Diagnose called):                               │
│  • Path A (LIVE): cluster_logs() → show repeated errors     │
│  • Path B (KB):   semantic search KB .md files              │
│  • LLM: receives digest + live clusters + KB matches        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ OUTPUT                                                      │
├─────────────────────────────────────────────────────────────┤
│ Dashboard Diagnose panel:                                   │
│  "What you saw: 12 GPU OOM errors in 5 min"                │
│  "What to do: [from KB] reduce batch size, restart"        │
└─────────────────────────────────────────────────────────────┘
```

---

## Configuring Custom Log Sources

### Step 1: Identify Log Paths

For your Jetson app, find where logs are written:

```bash
# Find active log files
find /var/log -name "*myapp*" -type f
find /home -name "*.log" -type f 2>/dev/null
find /opt -name "*.log" -type f 2>/dev/null

# Check app config
grep -r "log" /opt/myapp/config.ini
grep -r "LogFile\|log_path" /opt/myapp/
```

**Example Jetson app logs:**
```
/var/log/myapp/inference.log
/home/jetson/workspace/logs/current.log
/opt/trt-inference/debug.log
```

### Step 2: Configure SystemHealth

Edit `/path/to/systemhealth/.env`:

```bash
# Multiple log paths
SH_LOG_APP_DIRS=/var/log/myapp/inference.log:/home/jetson/workspace/logs/current.log:/opt/trt-inference/debug.log

# App names to monitor
SH_MONITORED_APPS=myapp,inference-engine,trt-service
```

Or set env vars before starting:

```bash
export SH_LOG_APP_DIRS="/var/log/myapp.log:/opt/myapp/logs/app.log"
export SH_MONITORED_APPS="myapp,inference"

cd /path/to/systemhealth
python3 app/main.py
```

### Step 3: Verify Logs Are Captured

Check dashboard:
```
http://localhost:9999/dashboard.html
→ Logs tab: should see your service name
→ REST API: curl http://localhost:9999/api/logs?service=myapp&limit=10
```

Or check DuckDB directly:
```bash
python3 << 'EOF'
import duckdb
con = duckdb.connect('data/logs.duckdb', read_only=True)
result = con.execute("SELECT DISTINCT service FROM logs ORDER BY service").fetchall()
print("Services found:", [r[0] for r in result])
EOF
```

---

## Real Examples: dmesg

Kernel messages contain valuable Jetson diagnostics. Real dmesg examples and how to handle them:

### Example 1: GPU Out of Memory (OOM Killer)

**Raw dmesg output:**
```
[12345.678901] Out of memory: Kill process 5432 (inference) score 823 or sacrifice child
[12345.678945] Killed process 5432 (inference) total-vm:4567890kB, anon-rss:3456789kB, file-rss:0kB
[12345.679012] Memory: 123456K available (16384K kernel code, 2345K rwdata, 4567K rodata, 1234K init, 5678K pages, 3456K reserved, 0K cma)
```

**What it means:**
- GPU inference process was killed because VRAM exhausted
- 3.4 GB was allocated before kill
- Need to reduce batch size or increase GPU memory

**KB entry (`data/kb/jetson_oom_killer.md`):**

```markdown
# Jetson: OOM Killer Triggered (GPU/System)

tags: jetson, oom, memory, kill, orin, nano

## What happens
Kernel OOM killer terminates process when system runs out of memory.
Always fatal — process exits with signal 9.
GPU inference most common victim on Jetson.

## Log patterns observed in dmesg
- CRITICAL: `Out of memory: Kill process`
- CRITICAL: `Killed process.*inference`
- ERROR: `Memory: .*available`

## Symptoms
- Process disappears: `ps aux | grep inference` shows nothing
- Nothing in journalctl — killed by kernel, not service
- Batch inference hangs or restarts

## Steps
1. Check when it happened: `dmesg | grep -A2 "Out of memory"`
2. Check GPU VRAM in Jetson tab → if >95%, problem is GPU
3. Check system RAM: Overview tab Memory card
4. If GPU OOM: reduce batch size by 50% → restart inference
5. If system RAM: add swap or kill background tasks
6. Enable dmesg monitoring: `watch -n 5 'dmesg | tail -5'`
```

### Example 2: Thermal Throttling

**Raw dmesg output:**
```
[34567.123456] thermal_sys: Registered thermal governor 'fair_share'
[34567.234567] tegra-soctherm 700e2000.soctherm: THROTTLE: OC0 reached 85000 mC threshold, shutting down
[34567.345678] tegra-soctherm 700e2000.soctherm: THROTTLE_STATS: GPU OC0 throttle_count=5
[34567.456789] gpu_freq: GPU clocks throttled to 921000000 Hz
```

**What it means:**
- SoC (System-on-Chip) hit 85°C
- GPU clocks reduced to save power/heat
- Inference will be slow

**KB entry (`data/kb/jetson_thermal_throttle.md`):**

```markdown
# Jetson: Thermal Throttling

tags: jetson, thermal, throttle, temperature, performance, orin, nano

## What happens
When SoC temp exceeds 85°C (configurable), Jetson reduces GPU/CPU clocks.
Inference speed drops 30-70% depending on throttle level.
Fan ramps up to max.

## Log patterns in dmesg
- WARN: `THROTTLE.*reached.*threshold`
- WARN: `GPU OC0 throttle_count`
- ERROR: `clocks throttled to`

## Symptoms
- Inference latency doubles
- GPU load shows high but output rate low
- Fan noise increases
- Jetson tab shows SoC temp > 80°C

## Steps
1. Check current temp: Jetson tab → SoC temp card
2. Check all temps: Jetson tab → Thermal Sensors grid
3. Verify airflow: remove enclosure, check heatsink contact
4. Switch to lower power mode: `sudo nvpmodel -m 1` (15W mode)
5. Reduce GPU workload: scale down inference batch or FPS
6. Monitor temps 10 min: `watch -n 1 'jetson_stats'`
```

### Example 3: GPU Driver/Hardware Error

**Raw dmesg output:**
```
[56789.111111] nouveau 0000:00:02.0: DRM: recoverable fault on HUBMMU
[56789.222222] nouveau 0000:00:02.0: DRM: failed to load firmware "nouveau/gm20b/fecs_bl.bin"
[56789.333333] tegra-pmc 7000e400.pmc: GPU rail off
```

**What it means:**
- GPU firmware loading failed or GPU encountered memory fault
- GPU may be unavailable or degraded

**KB entry (`data/kb/jetson_gpu_driver.md`):**

```markdown
# Jetson: GPU Driver or Firmware Error

tags: jetson, gpu, driver, firmware, hardware, orin, nano

## What happens
GPU firmware fails to load or GPU encounters recoverable/unrecoverable faults.
GPU may be unavailable until reboot.

## Log patterns in dmesg
- ERROR: `failed to load firmware.*gpu`
- ERROR: `recoverable fault on.*HUBMMU`
- CRITICAL: `GPU rail off`

## Symptoms
- Inference immediately fails: `CUDA_ERROR_NO_DEVICE`
- No GPU listed: `nvidia-smi` shows "No Devices"
- Jetson tab shows GPU% = 0% always

## Steps
1. Check dmesg: `dmesg | grep -i gpu`
2. Check nvidia-smi: `nvidia-smi` (may fail)
3. Try software reset: `sudo systemctl restart nvidia-persistenced`
4. If persists: reboot `sudo reboot`
5. After reboot: verify GPU appears in `nvidia-smi`
6. If still fails after reboot: hardware issue — contact support
```

### Example 4: Power Supply / Brownout

**Raw dmesg output:**
```
[78901.444444] tegra-pmc: Module restart requested by pmic
[78901.555555] PMC register 0x1400 = 0x00000001
[78901.666666] Power rail CPU: voltage drop detected
[78901.777777] reboot: Restarting system
```

**What it means:**
- Power supply not delivering enough current
- System force-restarted to prevent damage

**KB entry (`data/kb/jetson_power_supply.md`):**

```markdown
# Jetson: Power Supply / Brownout

tags: jetson, power, supply, brownout, reboot, orin, nano

## What happens
Power supply can't deliver enough current for peak load.
Voltage drops, PMIC detects issue, triggers reboot.
Indicates undersized PSU or power delivery problem.

## Log patterns in dmesg
- CRITICAL: `Module restart requested by pmic`
- CRITICAL: `voltage drop detected`
- CRITICAL: `reboot: Restarting system`

## Symptoms
- System reboots unexpectedly during GPU workload
- Happens when GPU + CPU at high utilization simultaneously
- No graceful shutdown — sudden reboot

## Steps
1. Check power consumption: Jetson tab → Power card
2. Check PSU capacity: `cat /proc/device-tree/power-supply/*/capacity` (Jetson specific)
3. Lower power mode: `sudo nvpmodel -m 1` → reduce power draw
4. Split workload: don't run GPU + CPU-intensive tasks together
5. If power supply is external: upgrade to higher wattage PSU
6. Monitor power draw: watch Jetson tab Power card during inference
```

---

## Creating Knowledge Base Entries

### Manual Method

**1. Create .md file in `data/kb/`**

```bash
cat > /path/to/systemhealth/data/kb/myapp_gpu_oom.md << 'EOF'
# MyApp: GPU Out of Memory

tags: myapp, gpu, oom, inference, jetson, orin

## What this means
Inference engine tries to allocate more GPU VRAM than available.
Causes immediate failure: CUDA_ERROR_OUT_OF_MEMORY.
Model cannot be loaded or processed.

## Log patterns
- ERROR: `CUDA out of memory`
- ERROR: `failed to allocate [0-9]+ bytes`
- FATAL: `RuntimeError: CUDA out of memory`
- CRITICAL: `[E] GPU.*allocation`

## Symptoms
- Inference process crashes immediately on startup
- GPU load stays 0% in Jetson tab
- Logs show "out of memory" at first inference attempt

## Steps
1. Check VRAM usage: Jetson tab → GPU VRAM card
2. If available > 500MB: issue is model too large
3. If available < 100MB: clear background apps
4. Reduce model size: quantization, pruning, or smaller variant
5. Reduce batch size: from 32 → 8 → 1
6. Restart inference: `systemctl restart myapp`
7. Monitor GPU memory: watch Jetson tab for 5 minutes
EOF
```

**2. Reload KB (no server restart needed)**

```bash
curl -X POST http://localhost:9999/api/kb/reload
```

**3. Test in Diagnose tab**

Dashboard → Diagnose tab → scope=myapp, question="why does inference crash?"

Expected response includes your KB entry.

---

## Auto-Generate KB from Live Logs

### 1. Collect Logs (Let App Run for a Few Hours)

Your app runs and encounters errors naturally.

### 2. Generate KB Stubs from DuckDB

```bash
cd /path/to/systemhealth

# See all error clusters
python3 tools/gen_kb_stubs.py --hours 6 --min-count 2

# Filter to one app
python3 tools/gen_kb_stubs.py --service myapp --hours 6 --min-count 1
```

**Output:**
```
  CREATED  stub_myapp_a1b2c3.md  [ERR] myapp ×12: CUDA out of memory
  CREATED  stub_myapp_d4e5f6.md  [WARN] myapp ×5: slow inference latency
  CREATED  stub_myapp_g7h8i9.md  [ERR] myapp ×3: connection to DB timeout

3 stubs created, 0 skipped.
Edit TODO sections in data/kb/stub_*.md, then POST /api/kb/reload
```

### 3. Fill in TODO Sections

Edit `data/kb/stub_myapp_a1b2c3.md`:

```markdown
# MyApp: CUDA out of memory  ← KEEP

tags: myapp, gpu, oom, inference  ← UPDATE with real tags

## What this means
← FILL IN: explain what this error means for your app

Seen 12 times in the analysis window.

## Log patterns
- ERROR: `CUDA out of memory`  ← KEEP (auto-populated)

## Steps
← FILL IN: specific steps to fix
1. Check GPU VRAM in Jetson tab
2. Reduce batch size from 32 to 8
3. Restart: systemctl restart myapp

## Notes
← FILL IN: context
Known issue when processing >1080p video frames. Reproducible with batch_size > 16.
```

### 4. Reload KB

```bash
curl -X POST http://localhost:9999/api/kb/reload
```

---

## Testing & Debugging

### Check What Logs Are Captured

```bash
# Dashboard Logs tab
http://localhost:9999/dashboard.html
→ Logs tab → set service filter

# REST API
curl http://localhost:9999/api/logs?service=myapp&since=300&limit=20

# Direct DuckDB query
python3 << 'EOF'
import duckdb
con = duckdb.connect('data/logs.duckdb', read_only=True)
rows = con.execute("""
    SELECT ts, service, level, message 
    FROM logs 
    WHERE service = 'myapp' 
    ORDER BY ts DESC 
    LIMIT 20
""").fetchall()
for r in rows:
    print(f"{r[0]} [{r[2]}] {r[1]}: {r[3]}")
EOF
```

### Check KB Was Loaded

```bash
# REST API
curl http://localhost:9999/api/kb/entries

# Or check meta.json
cat data/kb/meta.json | python3 -m json.tool | grep -A3 '"id"'
```

### Test Diagnose with Specific Service

```bash
# Ask agent about specific app
curl -X POST http://localhost:9999/api/diagnose \
  -H "content-type: application/json" \
  -d '{
    "scope": {"services": ["myapp"]},
    "question": "Why does myapp crash with GPU errors?"
  }'

# Response includes:
# - context_digest: what agent saw (metrics + live log clusters)
# - matches: KB entries that matched
# - llm_answer: LLM analysis + recommendations
```

### Monitor Log Ingestion in Real Time

```bash
# Watch logs arrive in DuckDB
python3 << 'EOF'
import duckdb
import time

con = duckdb.connect('data/logs.duckdb')
last_ts = 0

while True:
    result = con.execute("""
        SELECT COUNT(*) FROM logs WHERE ts > ?
    """, [last_ts]).fetchone()
    count = result[0]
    if count > 0:
        latest = con.execute("""
            SELECT ts, service, level, message 
            FROM logs 
            WHERE ts > ? 
            ORDER BY ts DESC 
            LIMIT 5
        """, [last_ts]).fetchall()
        for r in latest:
            print(f"{r[0]} [{r[2]:5}] {r[1]:15} {r[3][:60]}")
            last_ts = max(last_ts, r[0])
    time.sleep(2)
EOF
```

---

## Complete Workflow Example: Jetson Inference App

### Step 1: Setup

```bash
# Create log directory
mkdir -p /var/log/inference-engine

# Start app with logging
python3 /opt/inference/run.py > /var/log/inference-engine/app.log 2>&1 &

# Configure SystemHealth
export SH_LOG_APP_DIRS="/var/log/inference-engine/app.log"
export SH_MONITORED_APPS="inference-engine"

# Start SystemHealth
cd /path/to/systemhealth
python3 app/main.py
```

### Step 2: Let It Run (Collect Error Data)

```bash
# Run inference workload for 2-4 hours
# App will encounter errors naturally: GPU OOM, timeouts, etc.
```

### Step 3: Generate KB from Observed Errors

```bash
python3 tools/gen_kb_stubs.py --service inference-engine --hours 4 --min-count 1
```

Output:
```
CREATED stub_inference_a1b2.md [ERR] ×8: CUDA out of memory
CREATED stub_inference_c3d4.md [WARN] ×12: GPU memory at 90%
CREATED stub_inference_e5f6.md [ERR] ×3: model load timeout
```

### Step 4: Fill KB Entries

Edit `data/kb/stub_inference_a1b2.md`:

```markdown
# Inference Engine: CUDA Out of Memory

tags: inference-engine, gpu, oom, jetson, orin

## What this means
Model inference tries to allocate more GPU VRAM than available.
Batch size too large for model size.

## Log patterns
- ERROR: `CUDA out of memory`
- ERROR: `failed to allocate [0-9]+ bytes`

## Steps
1. Check Jetson tab → GPU VRAM card (should show available MB)
2. Reduce batch size: config BATCH_SIZE=4 (was 16)
3. Restart: systemctl restart inference-engine
4. Monitor GPU memory in Jetson tab for stability

## Notes
Observed with YOLOv8 Large model on Jetson Orin. 
Happens when batch_size > 4 with 8GB GPU memory.
Solution: use Medium model or batch_size=2.
```

### Step 5: Reload & Test

```bash
curl -X POST http://localhost:9999/api/kb/reload

# Dashboard Diagnose tab
# Question: "why does inference crash?"
# Expected: KB entry + LLM recommendations
```

---

## Summary

| Step | Command | Purpose |
|------|---------|---------|
| **1. Configure logs** | `export SH_LOG_APP_DIRS=...` | Tell SystemHealth where to read logs |
| **2. Start SystemHealth** | `python3 app/main.py` | Collector reads logs → DuckDB |
| **3. View live logs** | Dashboard Logs tab | Verify logs arriving |
| **4. Collect errors** | Let app run 2-4 hours | Gather real error patterns |
| **5. Generate KB stubs** | `python3 tools/gen_kb_stubs.py` | Auto-create KB templates |
| **6. Fill KB entries** | Edit `data/kb/stub_*.md` | Add fixes/steps |
| **7. Reload KB** | `curl -X POST .../kb/reload` | Agent learns new patterns |
| **8. Test diagnose** | Dashboard Diagnose tab | Agent analyzes with KB |

---

## Files Reference

| Path | Purpose |
|------|---------|
| `data/logs.duckdb` | Log storage (auto-created) |
| `data/kb/*.md` | Knowledge base entries |
| `data/kb/meta.json` | KB index (auto-generated) |
| `data/pinned_apps.json` | Pinned apps for monitoring |
| `tools/gen_kb_stubs.py` | Auto-generate KB from logs |
| `.env` | Environment config (SH_LOG_APP_DIRS, etc.) |

---

## Troubleshooting

**Logs not appearing in dashboard:**
```bash
# Check if file exists
ls -lh /var/log/myapp.log

# Check if configured
echo $SH_LOG_APP_DIRS

# Check DuckDB directly
python3 << 'EOF'
import duckdb
con = duckdb.connect('data/logs.duckdb', read_only=True)
result = con.execute("SELECT COUNT(*) FROM logs").fetchone()
print(f"Total logs: {result[0]}")
EOF
```

**KB not matching logs:**
```bash
# Verify KB is loaded
curl http://localhost:9999/api/kb/entries | python3 -m json.tool | head -20

# Check if your .md files have correct format
# Must have: "# Title" + "## Steps" or "tags:" line
grep -l "^#\|^tags:\|^##" data/kb/*.md
```

**Agent not using KB:**
```bash
# Test manually
curl -X POST http://localhost:9999/api/diagnose \
  -H "content-type: application/json" \
  -d '{"scope": {}, "question": "test"}'

# Check "matches" field in response — should show KB entries
```
