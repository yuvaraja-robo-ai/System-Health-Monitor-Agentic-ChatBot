# Log Analysis Workflow

## What is collected

SystemHealth ingests two log sources:

1. **systemd journal** (`JournaldCollector`) — all units, structured fields: `ts`, `host`, `severity`, `service`, `message`. Runs every 60 s.
2. **Custom file tails** (`FileLogCollector`) — configured via `SH_LOG_APP_DIRS` env var, line-parsed with auto-level detection.

Logs land in **DuckDB** (`data/logs.duckdb`) and are available via REST and WebSocket.

## Searching logs

### Live tail (WebSocket)
```
/ws/logs  →  {"data": {"ts": ..., "level": "ERR", "service": "nginx", "message": "..."}}
```
Filter client-side by level, service, regex. See **Logs** tab in dashboard.

### REST search
```
GET /api/logs?since=300&limit=200          # last 5 minutes
GET /api/logs?service=nginx&severity=ERR   # filter by service + level
GET /api/logs?q=OOM&since=3600            # full-text search
```

### Log summary per service
```
GET /api/units?window=6h   # returns errors/warns/crashes count per unit
```

## Pattern extraction steps

1. Open **Logs** tab — set level=ERR, watch for repeated messages.
2. Use regex filter to narrow: `timeout|connection refused|OOM|segfault`.
3. Switch to **Services** tab — sort by `Err` column to find noisiest unit.
4. Use **Diagnose** tab — enter question like "what errors occurred in the last 15 minutes?" to get LLM summary.
5. Check **AppFocus** tab → "Recent App Logs" panel for app-specific log correlation.

## Building a knowledge base entry from logs

1. Identify repeating error pattern (service + message prefix).
2. Correlate with metric spike in Overview (CPU, RSS, GPU temp).
3. Add entry to `data/kb/meta.json` with:
   - `id`, `title`, `tags` (e.g. `["nginx", "timeout", "net"]`)
   - `steps` — remediation checklist
4. Optionally create `data/kb/<id>.md` with full runbook.
5. KB auto-reloads on server restart; force reload via `POST /api/kb/reload` if available.

## DuckDB direct query (advanced)

```bash
python3 -c "
import duckdb
con = duckdb.connect('data/logs.duckdb', read_only=True)
print(con.execute(\"SELECT service, COUNT(*) AS n FROM logs WHERE severity='ERR' GROUP BY service ORDER BY n DESC LIMIT 20\").fetchdf())
"
```

## Key log severity levels

| Level | Meaning |
|-------|---------|
| ERR / ERROR / CRIT / FATAL | Actionable errors — check immediately |
| WARN | Degraded state — monitor for escalation |
| INFO | Normal operation markers |
| DEBUG | Verbose — usually filtered out |
