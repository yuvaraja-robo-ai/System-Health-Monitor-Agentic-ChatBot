# Dmesg Log Analysis for Jetson

Quick setup for analyzing kernel logs (dmesg) with KB.

---

## Enable Dmesg Collector (Optional)

The dmesg collector is available but not enabled by default. To enable:

**Option A: Enable via environment variable**

```bash
export SH_ENABLE_DMESG=1
cd /path/to/systemhealth
python3 app/main.py
```

**Option B: Modify main.py to always include**

Edit `app/main.py`, find `_build_collectors()`:

```python
def _build_collectors() -> list:
    cap = detect()
    cs: list = [PsutilCollector(), ProcessCollector(), AppMonitorCollector()]
    
    # ADD THIS:
    if cap.host == "jetson":  # only on Jetson
        cs.append(DmesgCollector())
    
    if cap.has_jtop:
        cs.append(JtopCollector())
    # ... rest
    return cs
```

And add import at top:

```python
from app.collectors.dmesg_collector import DmesgCollector
```

---

## What Gets Captured from dmesg

**Automatically categorized by subsystem:**

- `kernel-gpu`: nouveau, CUDA, GPU errors
- `kernel-thermal`: SoC throttling, temperature events
- `kernel-memory`: OOM killer, memory pressure
- `kernel-power`: voltage drops, PMIC events, brownouts
- `kernel-io`: disk, filesystem errors
- `kernel-net`: network driver errors
- `kernel-usb`: USB device errors

**Severity levels auto-detected:**

- `CRIT`: panic, segfault, kernel oops
- `ERR`: OOM kill, GPU rail off, reboot
- `WARN`: thermal throttle, voltage warning
- `INFO`: normal kernel messages

---

## Real Dmesg Examples & KB Entries

### Example 1: OOM Killer Event

**What you see in dmesg:**

```bash
$ dmesg | grep -A5 "Out of memory"

[Tue Apr 23 14:32:15 2026] Out of memory: Kill process 5432 (inference) score 823 or sacrifice child
[Tue Apr 23 14:32:15 2026] Killed process 5432 (inference) total-vm:4567890kB, anon-rss:3456789kB
[Tue Apr 23 14:32:16 2026] Memory: 123456K available
```

**Appears in SystemHealth as:**

- Service: `kernel-memory`
- Level: `ERR`
- Message: `Out of memory: Kill process 5432 (inference)...`

**KB Entry to create:**

```bash
cat > data/kb/jetson_oom_inference.md << 'EOF'
# Jetson: OOM Killer - Inference Process

tags: jetson, oom, memory, kernel, inference, kill

## What happens
Kernel kills the inference process when GPU/system RAM exhausted.
Process disappears instantly (signal 9).
No graceful shutdown — output may be corrupted.

## Log patterns in dmesg
- ERROR: `Out of memory: Kill process`
- ERROR: `Killed process.*inference`
- ERROR: `anon-rss:[0-9]+kB`

## Symptoms
- Inference process vanishes from `ps aux`
- No error in inference logs (killed by kernel, not app)
- Sudden drop in GPU utilization to 0%
- dmesg shows the kill event

## Steps
1. Check when: `dmesg | grep -B2 "Killed process.*inference"`
2. Check available memory: `free -h` or Overview tab
3. If GPU OOM: reduce model size or batch size
4. If system RAM OOM: stop background processes
5. Increase available memory: enable swap or upgrade device
6. Restart inference: `systemctl restart inference`
7. Monitor: watch `dmesg` and Jetson tab during next run

## Prevention
- Monitor memory in Overview tab — alert at 85%
- Set batch_size conservatively (start small, increase)
- Use quantized models (INT8 vs FP32 = 4x smaller)
EOF

curl -X POST http://localhost:9999/api/kb/reload
```

### Example 2: GPU Thermal Throttle

**What you see in dmesg:**

```bash
$ dmesg | grep -i thermal

[Tue Apr 23 15:45:20 2026] tegra-soctherm 700e2000.soctherm: THROTTLE: OC0 reached 85000 mC
[Tue Apr 23 15:45:20 2026] tegra-soctherm 700e2000.soctherm: THROTTLE_STATS: GPU OC0 count=5
[Tue Apr 23 15:45:21 2026] gpu_freq: GPU clocks throttled to 921000000 Hz
```

**Appears in SystemHealth as:**

- Service: `kernel-thermal`
- Level: `WARN`
- Message: `tegra-soctherm: THROTTLE: OC0 reached 85000 mC`

**KB Entry:**

```bash
cat > data/kb/jetson_thermal_gpu.md << 'EOF'
# Jetson: Thermal Throttling - GPU Clock Reduction

tags: jetson, thermal, throttle, gpu, temperature, performance

## What happens
When SoC temperature hits 85°C threshold, Jetson reduces GPU clock speeds.
Inference latency increases (30-70% slower depending on throttle level).

## Log patterns in dmesg
- WARN: `THROTTLE.*reached.*mC`
- WARN: `GPU OC0 count`
- WARN: `clocks throttled to`

## Symptoms
- Inference latency doubles: 50ms → 100ms+
- GPU utilization high but output rate low
- Fan ramps to maximum noise
- Jetson tab shows SoC temp > 80°C

## Steps
1. Check current SoC temperature: Jetson tab → "SoC temp" card
2. Check all temperatures: Jetson tab → "Thermal Sensors" grid
3. If enclosed: remove enclosure, verify heatsink contact
4. Check airflow: point fan at heatsink
5. Switch power mode: `sudo nvpmodel -m 1` (15W, lower clock)
6. Reduce GPU load: smaller model, lower FPS, smaller frames
7. Monitor temps: watch Jetson tab, should drop below 75°C within 5 min

## Prevention
- Jetson Orin: design for sustained 75°C SoC temperature
- Jetson Nano: keep below 80°C
- Use higher power mode (30W) only for bursty loads, not sustained
- Monitor temperature trends: if consistently climbing, thermal issue in airflow
EOF

curl -X POST http://localhost:9999/api/kb/reload
```

### Example 3: Power Supply Brownout

**What you see in dmesg:**

```bash
$ dmesg | tail -30

[Wed Apr 24 10:11:22 2026] tegra-pmc: Module restart requested by pmic
[Wed Apr 24 10:11:22 2026] PMC register 0x1400 = 0x00000001
[Wed Apr 24 10:11:22 2026] Power rail CPU: voltage drop detected
[Wed Apr 24 10:11:22 2026] reboot: Restarting system
```

**Appears in SystemHealth as:**

- Service: `kernel-power`
- Level: `ERR`
- Message: `Module restart requested by pmic`

**KB Entry:**

```bash
cat > data/kb/jetson_power_pmic.md << 'EOF'
# Jetson: Power Supply Brownout - PMIC Reboot

tags: jetson, power, supply, pmic, brownout, reboot, shutdown

## What happens
Power supply can't deliver enough current for peak load.
PMIC detects voltage drop, triggers emergency reboot.
System restarts abruptly without shutdown sequence.
Indicates undersized PSU.

## Log patterns in dmesg
- CRITICAL: `Module restart requested by pmic`
- CRITICAL: `voltage drop detected`
- CRITICAL: `reboot: Restarting system`

## Symptoms
- System reboots suddenly during GPU-intensive inference
- Happens when GPU + CPU both at high utilization
- No logs of graceful shutdown
- Sudden loss of output

## Steps
1. Check when: `dmesg | grep -B3 "Module restart"`
2. Check power draw: Jetson tab → "Power" card
3. Reduce power demand:
   - Lower GPU clock: `sudo nvpmodel -m 1` (15W)
   - Don't run GPU + CPU-heavy tasks simultaneously
   - Reduce batch size (inference) or frame rate
4. Check PSU capacity:
   - Jetson Orin needs 25W sustained, 40W peak
   - Jetson Nano needs 10W sustained, 20W peak
5. If PSU is external: upgrade to higher wattage
6. Monitor power draw during inference: should stay < 30W

## Prevention
- Buy PSU rated 1.5x higher than device max power
- Avoid concurrent high loads
- Use lower power mode for sustained inference
- Monitor Jetson tab Power card trends
EOF

curl -X POST http://localhost:9999/api/kb/reload
```

---

## Workflow: Capture Real Dmesg Errors & Build KB

### Step 1: Run App Under Load (Trigger Real Errors)

```bash
# Start inference with heavy workload
python3 /opt/myapp/inference.py --batch-size 32 --frames-per-second 30

# Watch dmesg for events
watch -n 1 'dmesg | tail -10'
```

### Step 2: Capture Dmesg to File

```bash
# Save current dmesg
dmesg > /tmp/jetson_dmesg.log

# Or stream to file while app runs
dmesg -T -L > /tmp/jetson_dmesg_$(date +%s).log &
```

### Step 3: Extract Patterns

```bash
# Find all ERROR/CRITICAL lines
grep -i "error\|fatal\|kill\|throttle\|brownout" /tmp/jetson_dmesg.log

# Count by type
grep -i "error\|fatal" /tmp/jetson_dmesg.log | cut -d: -f2- | sort | uniq -c | sort -rn
```

### Step 4: Create KB Entry from Real Patterns

```bash
# Example: you found 5 thermal throttle events
# Create KB entry based on observed messages

cat > data/kb/myjetson_throttle.md << 'EOF'
# My Jetson: Thermal Throttle Under Load

tags: myjetson, thermal, throttle, observed

## What happens
Inference workload (batch_size=32) causes SoC temp > 85°C.
Jetson throttles GPU clocks automatically.

## Log patterns observed in dmesg
- WARN: `tegra-soctherm.*THROTTLE.*OC0 reached 85000`
- WARN: `GPU OC0 throttle_count=5`
- WARN: `gpu_freq.*clocks throttled`

## Symptoms observed
- Inference latency increases from 50ms to 120ms
- Happens 5-10 minutes into continuous inference
- Fan noise increases to maximum
- Jetson tab shows SoC temp 82-88°C

## Steps
1. Check dmesg: `dmesg | grep -i throttle`
2. Reduce batch size: 32 → 16 or 8
3. Switch power mode: `sudo nvpmodel -m 1`
4. Check airflow: ensure heatsink has airflow
5. Monitor temperature: `watch -n 1 "jetson_release | grep -i temp"`

## Root cause
Thermal design: batch_size=32 with full GPU load exceeds cooling capacity.
Solution: use batch_size=8 for sustained operation, or 32 for bursty only.
EOF

curl -X POST http://localhost:9999/api/kb/reload
```

### Step 5: Test in Dashboard

```
Dashboard → Diagnose tab
Scope: empty (all services)
Question: "Why is my Jetson throttling the GPU?"

Expected: LLM response includes your KB entry + recommendations
```

---

## Useful Commands for Dmesg Analysis

```bash
# View thermal events
dmesg | grep -i "thermal\|throttle\|temp"

# View memory events
dmesg | grep -i "oom\|memory\|killed"

# View power events
dmesg | grep -i "power\|pmic\|voltage\|brownout"

# View GPU events
dmesg | grep -i "gpu\|nouveau\|cuda"

# Timeline: last 50 lines with timestamp
dmesg -T -L | tail -50

# Watch live (follow mode)
dmesg -T -f

# Save raw dmesg
sudo dmesg > dmesg_$(date +%Y%m%d_%H%M%S).log
```

---

## Troubleshooting

**Dmesg not captured in SystemHealth:**
```bash
# Check if collector is running
ps aux | grep python3 | grep app/main.py

# Check if dmesg command works
dmesg | head -5

# Check logs in DuckDB
python3 << 'EOF'
import duckdb
con = duckdb.connect('data/logs.duckdb', read_only=True)
result = con.execute("""
    SELECT DISTINCT service FROM logs WHERE service LIKE 'kernel%'
""").fetchall()
print("Kernel services found:", result)
EOF
```

**KB not matching dmesg entries:**
```bash
# Reload KB with debug
curl -X POST http://localhost:9999/api/kb/reload

# Check meta.json
cat data/kb/meta.json | python3 -m json.tool | grep -A5 "kernel\|thermal\|dmesg"
```

---

## Summary

| Step | Command |
|------|---------|
| Enable dmesg | Add `DmesgCollector()` to `app/main.py` |
| Run app under load | `python3 /opt/myapp/run.py` |
| Capture events | `dmesg > /tmp/dmesg.log` |
| Analyze patterns | `grep -i error /tmp/dmesg.log` |
| Create KB entry | `cat > data/kb/myapp_thermal.md` |
| Reload KB | `curl -X POST .../kb/reload` |
| Test diagnose | Dashboard → Diagnose tab |
