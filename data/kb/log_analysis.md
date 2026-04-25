# Log Analysis Workflow

tags: logs, analysis, clusters, histogram, live-tail, troubleshooting

## What is collected

SystemHealth ingests two log sources:

1. **systemd journal** (`JournaldCollector`) — units and syslog identifiers, structured fields: `ts`, `host`, `level`, `service`, `message`.
2. **Custom file tails** (`FileLogCollector`) — configured via `SH_LOG_APP_DIRS`, parses `.log` and `.ndjson` files.

Logs land in **DuckDB** (`data/logs.duckdb`) and are available via REST and WebSocket.

## Searching logs

### Live tail (WebSocket)
```
/ws/logs  →  {"data": {"ts": ..., "level": "ERR", "service": "nginx", "message": "..."}}
```
Filter client-side by level, service, regex. See **Logs** tab in dashboard.

### REST search
```
GET /api/logs?since=5m&limit=200              # last 5 minutes
GET /api/logs?service=nginx&level=ERR         # exact service + level
GET /api/logs?regex=OOM|timeout&since=1h      # regex filter on message
GET /api/logs/cluster?since=15m&limit=20      # repeated error signatures
GET /api/logs/histogram?window=1h&bucket=1m   # counts by bucket and level
```

## Steps

1. Open **Logs** tab and start with no filters to confirm rows exist.
2. Use `Historical Results` for stored log search over `15m`, `1h`, or `24h`.
3. Use `regex` for message patterns such as `timeout|connection refused|OOM|segfault`.
4. Use `Clustered Errors` to find repeated signatures before reading individual lines.
5. Use `Log Histogram` to see whether the problem is spiky or sustained over time.
6. Switch to **Services** or **App Focus** after you identify the noisiest service.
7. Use **Diagnose** or **Agent Chat** once you have a concrete service name or error pattern.

## Building a knowledge base entry from logs

1. Identify repeating error pattern (service + message prefix).
2. Correlate with metric spikes in Overview, Health, or App Focus.
3. Create `data/kb/<id>.md` with a title, tags, symptoms, and `## Steps`.
4. Use exact service names and error phrases in the title or tags to improve retrieval.
5. Reload the KB with `POST /api/kb/reload` or restart the server.

## DuckDB direct query (advanced)

```bash
python3 -c "
import duckdb
con = duckdb.connect('data/logs.duckdb', read_only=True)
print(con.execute(\"SELECT service, COUNT(*) AS n FROM logs WHERE upper(level) IN ('ERR','ERROR','CRIT','FATAL') GROUP BY service ORDER BY n DESC LIMIT 20\").fetchdf())
"
```

## Key log severity levels

| Level | Meaning |
|-------|---------|
| ERR / ERROR / CRIT / FATAL | Actionable errors — check immediately |
| WARN | Degraded state — monitor for escalation |
| INFO | Normal operation markers |
| DEBUG | Verbose — usually filtered out |
