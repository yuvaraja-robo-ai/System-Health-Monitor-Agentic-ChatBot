# High Error Rate in Service

tags: logs, errors, service, journald, duckdb

## Symptoms
- Services tab shows `errors > 10` for a unit in last hour
- Log tail flooding with ERR/CRIT lines
- Health score drops (error rate is a driver)

## Steps

1. **Services tab** — filter `issues only`, click the noisiest unit and note its exact service name.
2. **Logs tab** — in `Historical Results`, set level=`ERR`, service=`<exact unit name>`, and a window like `15m` or `1h`.
3. **Logs tab** — in `Clustered Errors`, look for the highest-count signature and note the repeated sample message.
4. **Live Tail** — keep the same filters and confirm whether errors are still actively arriving.
5. **App Focus tab** — select the app, read `Recent App Logs` and `Selected App Analysis`.
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
7. If recurring, add a KB runbook for the exact error pattern and keep the cluster sample text in the title/tags.

## Common error patterns

| Pattern | Likely cause |
|---------|-------------|
| `connection refused` | Dependency not running |
| `OOM` / `Cannot allocate memory` | RSS leak or undersized pod |
| `SIGKILL` / `signal 9` | OOM killer |
| `SSL` / `certificate` | Cert expired |
| `permission denied` | Wrong user / missing cap |
