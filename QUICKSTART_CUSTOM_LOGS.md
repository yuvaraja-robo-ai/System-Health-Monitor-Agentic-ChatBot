# Quick Start: Custom App Logs + Knowledge Base

**5-minute setup to analyze your Jetson app logs with AI agent.**

---

## Your Goal

Your Jetson app (`myapp`) writes logs. You want:
1. Dashboard to show live logs (Logs tab)
2. Error patterns captured (Services tab error counts)
3. AI agent to recommend fixes (Diagnose tab)

**This guide gets you there in 3 steps.**

---

## Step 1: Tell SystemHealth Where Your Logs Are (2 min)

### Find your log file

```bash
# Where does your app write logs?
ls -lh /var/log/myapp*
ls -lh /home/jetson/*/logs*
find /opt -name "*.log" 2>/dev/null

# Example: app writes to
# → /var/log/myapp/inference.log
```

### Configure SystemHealth

```bash
# Option A: Environment variable
export SH_LOG_APP_DIRS="/var/log/myapp/inference.log"

# Option B: Create .env file
cat > /path/to/systemhealth/.env << 'EOF'
SH_LOG_APP_DIRS=/var/log/myapp/inference.log
SH_MONITORED_APPS=myapp,inference
EOF
```

### Restart SystemHealth

```bash
cd /path/to/systemhealth

# Stop if running
pkill -f "python3 app/main.py" 2>/dev/null || true

# Start with config
python3 app/main.py &

# Verify it started
sleep 2
ps aux | grep "python3 app/main.py"
```

### Verify logs appear

Open dashboard:
```
http://localhost:9999/dashboard.html
→ Logs tab
→ Should see "myapp" or "inference" in service filter
```

**Done step 1.**

---

## Step 2: Run Your App & Let It Generate Errors (15-30 min)

```bash
# Run your app under normal workload
cd /opt/myapp
python3 inference.py --batch-size 8 &

# OR with heavy load (to trigger errors faster)
python3 inference.py --batch-size 32 --frames-per-second 60 &

# Monitor logs arriving
watch -n 2 'tail -5 /var/log/myapp/inference.log'

# Watch dashboard Logs tab in browser
# Should see errors appear in real-time
```

**Errors will appear** (out of memory, timeouts, etc.). Let app run for 15-30 minutes to collect patterns.

---

## Step 3: Create Knowledge Base from Observed Errors (3 min)

### Auto-generate KB stubs

```bash
cd /path/to/systemhealth

# See what errors exist
python3 tools/gen_kb_stubs.py --service myapp --hours 1 --min-count 1
```

**Output:**
```
  CREATED  stub_myapp_a1b2c3.md  [ERR] myapp ×12: CUDA out of memory
  CREATED  stub_myapp_d4e5f6.md  [WARN] myapp ×5: inference slow
  CREATED  stub_myapp_g7h8i9.md  [ERR] myapp ×3: connection timeout
```

### Fill in fixes (1 min each)

Edit `data/kb/stub_myapp_a1b2c3.md`:

```markdown
# MyApp: CUDA Out of Memory

tags: myapp, gpu, oom, inference, jetson

## What this means
Inference tries to allocate more GPU VRAM than available (8GB on Orin).
Happens when batch_size too large or model not quantized.

## Log patterns
- ERROR: `CUDA out of memory`
- ERROR: `failed to allocate [0-9]+ bytes`

## Steps
1. Check GPU VRAM: Jetson tab → GPU card (shows available MB)
2. Reduce batch size: config `BATCH_SIZE=4` (was 32)
3. Restart app: `systemctl restart myapp` or `pkill -f myapp; python3 inference.py &`
4. Monitor GPU memory: watch Jetson tab → should stay < 8GB
```

### Reload KB (auto-picked up by agent)

```bash
curl -X POST http://localhost:9999/api/kb/reload
# → {"ok": true, "entries": 3}
```

**Done.**

---

## Test It Works

### Dashboard Diagnose Tab

```
Open: http://localhost:9999/dashboard.html
→ Diagnose tab
→ Scope: leave empty (or pick your service)
→ Question: "Why does myapp have errors?"
→ Click: ▸ diagnose now

Expected output:
  • Summary: score=60 leaks=0 crashes=0
  • Matches: [MyApp: CUDA OOM] score=0.87
    - Steps: reduce batch size, restart
  • LLM Answer: "Your app is running out of GPU memory..."
```

### Dashboard Logs Tab

```
→ Logs tab
→ Service filter: myapp
→ Level: ERR
→ Should see: error messages in real-time
```

### Dashboard Services Tab

```
→ Services tab
→ Should show myapp with error count (Err column)
```

---

## Complete Example: Real Jetson Inference App

### Setup

```bash
# Create app directory
mkdir -p /opt/myinference/logs

# Create simple inference script
cat > /opt/myinference/app.py << 'EOF'
import logging
import random
import time

# Setup logging
logging.basicConfig(
    filename="/var/log/myinference/app.log",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# Simulate inference
for i in range(100):
    batch_size = 32
    
    # Simulate random errors (like real inference does)
    if random.random() < 0.05:  # 5% error rate
        log.error(f"CUDA out of memory: tried to allocate {batch_size*1024}MB but only 500MB free")
    elif random.random() < 0.03:
        log.warning(f"GPU utilization at 95%, batch {i} slow")
    else:
        log.info(f"Inference batch {i} complete: {random.randint(50, 100)}ms latency")
    
    time.sleep(1)

log.info("Inference completed")
EOF

# Make logs writable
sudo mkdir -p /var/log/myinference
sudo chmod 777 /var/log/myinference
```

### Configure SystemHealth

```bash
export SH_LOG_APP_DIRS="/var/log/myinference/app.log"
export SH_MONITORED_APPS="myinference"

cd /path/to/systemhealth
python3 app/main.py &
```

### Run app

```bash
python3 /opt/myinference/app.py &

# Watch logs
tail -f /var/log/myinference/app.log
```

### Generate KB

```bash
# After 2-3 minutes of app running
python3 tools/gen_kb_stubs.py --service myinference --hours 1 --min-count 1

# Edit stub_myinference_*.md files
# Reload
curl -X POST http://localhost:9999/api/kb/reload
```

### Test Diagnose

```bash
Dashboard → Diagnose
Question: "why is my inference slow and error prone?"
```

---

## Real Commands for Your Setup

```bash
# 1. Find where your app logs
find /var/log /home /opt -name "*.log" 2>/dev/null | grep -i myapp

# 2. Configure (add to .env)
echo "SH_LOG_APP_DIRS=/path/to/app.log" >> .env

# 3. Start SystemHealth
cd /path/to/systemhealth
python3 app/main.py &

# 4. Run your app
/path/to/myapp &

# 5. Wait 5-10 minutes for logs to accumulate

# 6. Generate KB
python3 tools/gen_kb_stubs.py --service myapp --hours 1

# 7. Edit data/kb/stub_*.md files (fill in fixes)

# 8. Reload KB
curl -X POST http://localhost:9999/api/kb/reload

# 9. Test
# Open dashboard → Diagnose → question → diagnose now
```

---

## Troubleshooting

| Problem | Check |
|---------|-------|
| Logs not appearing | `ls -la /path/to/app.log` exists? `SH_LOG_APP_DIRS` set? |
| Logs appear but no service name | App writes plain text? Parser auto-detects severity |
| KB not matching | Edit .md file: title must have `#`, steps section must have `##` |
| Agent says "no LLM configured" | Set `SH_OLLAMA_URL` or `SH_LLAMA_URL` env var |
| Diagnose times out | LLM running? Try `curl http://localhost:11434/api/generate` |

---

## Next Steps

1. **Deep customization:** read `LOG_ANALYSIS_README.md`
2. **Kernel logs (dmesg):** read `DMESG_SETUP.md`
3. **Pattern matching:** read `LOG_ANALYSIS_README.md` → "Creating Knowledge Base Entries"
4. **Add regex patterns:** read `LOG_ANALYSIS_README.md` → "Option B: Add regex pattern endpoint"

---

## File Reference

| Path | Purpose |
|------|---------|
| `/var/log/myapp/app.log` | Your app logs (adjust path) |
| `.env` | Config: `SH_LOG_APP_DIRS`, `SH_MONITORED_APPS` |
| `data/logs.duckdb` | All ingested logs (auto-created) |
| `data/kb/stub_*.md` | KB stubs (auto-generated, you fill in) |
| `tools/gen_kb_stubs.py` | Generator script |
| `http://localhost:9999/dashboard.html` | Dashboard |

---

## One-Liner Setup

If app already logs to `/var/log/myapp.log`:

```bash
cd /path/to/systemhealth && \
echo "SH_LOG_APP_DIRS=/var/log/myapp.log" > .env && \
python3 app/main.py & \
sleep 3 && echo "Dashboard: http://localhost:9999/dashboard.html"
```

Done. Open dashboard, run your app, wait 5 min, generate KB, fill in fixes, reload.
