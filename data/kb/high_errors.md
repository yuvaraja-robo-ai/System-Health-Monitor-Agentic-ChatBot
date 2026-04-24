# High Error Rate in Service

## Symptoms
- Services tab shows `errors > 10` for a unit in last hour
- Log tail flooding with ERR/CRIT lines
- Health score drops (error rate is a driver)

## Steps

1. **Services tab** — filter `issues only`, click noisiest unit.
2. **Logs tab** — set level=ERR, service=<unit name>, scan for common message prefix.
3. **AppFocus tab** — select the app, read "Recent App Logs" panel + "Selected App Analysis" LLM summary.
4. Check if errors started after a deploy:
   ```bash
   journalctl -u <service> --since "1 hour ago" -p err
   ```
5. Check for dependency failures (database down, port unreachable):
   ```bash
   journalctl -u <service> -n 50 --no-pager | grep -i "connection\|refused\|timeout"
   ```
6. Restart if transient:
   ```bash
   sudo systemctl restart <service>
   journalctl -fu <service>   # watch for recurrence
   ```
7. If recurring — add remediation step to KB and set alert threshold.

## Common error patterns

| Pattern | Likely cause |
|---------|-------------|
| `connection refused` | Dependency not running |
| `OOM` / `Cannot allocate memory` | RSS leak or undersized pod |
| `SIGKILL` / `signal 9` | OOM killer |
| `SSL` / `certificate` | Cert expired |
| `permission denied` | Wrong user / missing cap |
