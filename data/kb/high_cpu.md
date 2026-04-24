# Sustained high CPU

tags: cpu, load, hot

CPU total > 90% for several minutes or load1 > cores × 1.5 indicates saturation.

## Steps

1. Check top processes by CPU in `/api/processes?sort=cpu`.
2. Inspect per-core usage — single hot core suggests a pinned thread or GIL bottleneck.
3. Correlate with log errors and recent deploys.
4. Consider renicing, throttling, or scaling out the offending workload.
