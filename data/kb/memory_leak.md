# Memory leak in long-running service

tags: memory, leak, rss, oom

A process with monotonically increasing RSS and r² ≥ 0.6 over ≥ 15 minutes indicates a memory leak. If TTL-to-OOM is under 6h, act now.

## Steps

1. Identify the offending PID from `/api/leaks` (highest slope_mb_min, flagged=true).
2. Capture a heap snapshot (e.g. `py-spy dump`, `gdb gcore`, or language-native tooling).
3. Check recent deploys / config changes for the affected service.
4. If critical, restart the service via `systemctl restart <unit>` — buys time, does not fix root cause.
5. File an incident with slope, TTL, and the top stack from the heap snapshot.
