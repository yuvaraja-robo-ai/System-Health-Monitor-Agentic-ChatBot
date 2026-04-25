PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA temp_store=MEMORY;
PRAGMA mmap_size=268435456;

CREATE TABLE IF NOT EXISTS metric (
    ts    INTEGER NOT NULL,
    key   TEXT    NOT NULL,
    value REAL    NOT NULL,
    PRIMARY KEY (key, ts)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_metric_ts ON metric(ts);

CREATE TABLE IF NOT EXISTS metric_10s (
    ts    INTEGER NOT NULL,
    key   TEXT    NOT NULL,
    value REAL    NOT NULL,
    PRIMARY KEY (key, ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS metric_1m (
    ts    INTEGER NOT NULL,
    key   TEXT    NOT NULL,
    value REAL    NOT NULL,
    PRIMARY KEY (key, ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS proc_rss (
    ts       INTEGER NOT NULL,
    pid      INTEGER NOT NULL,
    name     TEXT    NOT NULL,
    rss      INTEGER NOT NULL,
    cpu      REAL    NOT NULL,
    threads  INTEGER NOT NULL,
    PRIMARY KEY (pid, ts)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_proc_ts ON proc_rss(ts);

CREATE TABLE IF NOT EXISTS app_metric (
    ts    INTEGER NOT NULL,
    app   TEXT    NOT NULL,
    key   TEXT    NOT NULL,
    value REAL    NOT NULL,
    PRIMARY KEY (app, key, ts)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_app_metric_ts ON app_metric(ts);
CREATE INDEX IF NOT EXISTS idx_app_metric_app_ts ON app_metric(app, ts);

CREATE TABLE IF NOT EXISTS app_metric_10s (
    ts    INTEGER NOT NULL,
    app   TEXT    NOT NULL,
    key   TEXT    NOT NULL,
    value REAL    NOT NULL,
    PRIMARY KEY (app, key, ts)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_app_metric_10s_ts ON app_metric_10s(ts);
CREATE INDEX IF NOT EXISTS idx_app_metric_10s_app_ts ON app_metric_10s(app, ts);

CREATE TABLE IF NOT EXISTS app_metric_1m (
    ts    INTEGER NOT NULL,
    app   TEXT    NOT NULL,
    key   TEXT    NOT NULL,
    value REAL    NOT NULL,
    PRIMARY KEY (app, key, ts)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_app_metric_1m_ts ON app_metric_1m(ts);
CREATE INDEX IF NOT EXISTS idx_app_metric_1m_app_ts ON app_metric_1m(app, ts);

CREATE TABLE IF NOT EXISTS event (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      INTEGER NOT NULL,
    kind    TEXT    NOT NULL,
    payload TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_ts ON event(ts);
CREATE INDEX IF NOT EXISTS idx_event_kind ON event(kind, ts);
