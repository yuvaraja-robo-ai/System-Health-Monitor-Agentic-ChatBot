# No Logs Showing Up

tags: logs, empty, ingestion, journald, filelog, dmesg, troubleshooting

## Symptoms
- `Logs` tab shows no lines in both `Historical Results` and `Live Tail`
- `/api/logs?since=15m&limit=20` returns `[]`
- Cluster and histogram panels are empty

## Steps
1. Clear all UI filters first: level, service, and regex can hide valid log rows.
2. Increase the history window to `1h` or `24h` to rule out a short-window miss.
3. If you expect systemd logs, verify the host has journald and the app is running as a service.
4. If you expect file logs, set `SH_LOG_APP_DIRS` to the exact file or directory path and restart the app.
5. Confirm the target files end with `.log` or `.ndjson` when using directory-based discovery.
6. Check that the application has produced fresh log lines since SystemHealth started.
7. If needed, call `GET /api/logs?since=24h&limit=50` directly to distinguish UI issues from ingestion issues.

## Common causes
- No collectors matched the source you expected
- Wrong `SH_LOG_APP_DIRS` path
- File exists but has no new appended lines
- Filters are too narrow
- Service name guessed from the UI does not match the exact stored service field
