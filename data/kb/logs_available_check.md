# Check Whether Logs Are Available

tags: logs, availability, journald, filelog, duckdb, ui

## Symptoms
- Chatbot answers with a generic log KB entry but does not confirm real log rows exist
- Logs tab looks empty
- You need to know whether logs are actually being ingested or just theoretically supported

## Steps
1. Open the `Logs` tab and leave filters empty.
2. Check `Historical Results` with a window like `15m` and limit `200`.
3. If rows appear there, logs are stored in DuckDB and available for analysis.
4. Check `Live Tail`; if rows appear there, live WebSocket log streaming is working too.
5. Check `Clustered Errors`; if grouped signatures appear, error clustering is working.
6. If the UI is unclear, call `GET /api/logs?since=15m&limit=20`.
7. If the API returns `[]`, the log endpoints are working but nothing has been ingested yet.

## Quick interpretation
- `Historical Results` has rows: stored logs available
- `Live Tail` has rows: live stream available
- `Clustered Errors` has rows: repeated error signatures available
- All three empty: investigate collector setup, log source availability, or window/filter mismatch
