# GPU Overload / VRAM Exhaustion (Jetson)

## Symptoms
- `gpu.load` > 90% sustained for > 30 s
- VRAM used approaching total (< 200 MB free)
- Power draw > rated TDP for current NVP model
- SoC temp rising > 2°C/min

## Steps

1. Check GPU load + VRAM in **Jetson** tab → GPU card + VRAM sub-line.
2. Identify offending process in **Processes** tab — sort by RSS, look for CUDA processes.
3. Check NVP model: lower wattage mode reduces GPU clock.
   ```bash
   sudo nvpmodel -q          # current model
   sudo nvpmodel -m 1        # switch to 15W
   sudo jetson_clocks --show # verify clocks reduced
   ```
4. If inference workload: batch size too large — reduce or split.
5. If VRAM leak: restart the inference service.
   ```bash
   sudo systemctl restart <service>
   ```
6. Monitor NVENC/NVDEC engines if video encode/decode is involved — check **Engines** panel in Jetson tab.

## Prevention
- Set `SH_LEAK_SLOPE_MB_MIN=0.1` to catch VRAM creep earlier.
- Add inference service to `SH_MONITORED_APPS` for continuous tracking.
