#!/usr/bin/env python3
"""
Generate KB stub .md files from real log clusters in DuckDB.

Usage:
    python3 tools/gen_kb_stubs.py [--hours 24] [--min-count 3] [--service myapp]

Creates data/kb/stub_<service>_<hash>.md for each cluster that has no existing KB entry.
You then fill in the "## What this means" and "## Steps" sections.
"""

import argparse
import hashlib
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import duckdb


def cluster_logs(con, since_s: int, service_filter: str | None, min_count: int) -> list[dict]:
    where = f"ts >= {since_s}"
    if service_filter:
        where += f" AND service ILIKE '%{service_filter}%'"
    q = f"""
        SELECT
            COALESCE(service, '(unknown)') AS service,
            COALESCE(severity, 'INFO') AS level,
            -- strip numbers/timestamps to get a stable key
            regexp_replace(
                regexp_replace(message, '\\d{{4}}-\\d{{2}}-\\d{{2}}T?\\d{{2}}:\\d{{2}}:\\d{{2}}[^\\s]*', '<TS>', 'g'),
                '\\b\\d+\\b', '<N>', 'g'
            ) AS pattern,
            COUNT(*) AS n,
            MIN(message) AS sample
        FROM logs
        WHERE {where}
          AND severity IN ('ERR', 'ERROR', 'CRIT', 'FATAL', 'WARN', 'WARNING')
        GROUP BY 1, 2, 3
        HAVING COUNT(*) >= {min_count}
        ORDER BY n DESC
        LIMIT 60
    """
    rows = con.execute(q).fetchall()
    cols = ["service", "level", "pattern", "n", "sample"]
    return [dict(zip(cols, r)) for r in rows]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower())[:30].strip("_")


def make_stub(cluster: dict) -> str:
    svc = cluster["service"]
    level = cluster["level"]
    sample = cluster["sample"]
    pattern = cluster["pattern"]
    count = cluster["n"]
    return f"""# {svc}: {level} — {sample[:60]}

tags: {svc}, {level.lower()}, stub

## What this means
<!-- TODO: explain what this log message means for {svc} -->
<!-- Seen {count} times in the analysis window -->

## Log patterns
- {level}: `{sample[:120]}`
- Pattern key: `{pattern[:120]}`

## Steps
1. Check current rate: `GET /api/logs?service={svc}&severity={level}&since=300`
2. <!-- TODO: first diagnostic step -->
3. <!-- TODO: second diagnostic step — look for root cause -->
4. <!-- TODO: remediation — restart, config change, or escalate -->

## Notes
<!-- TODO: add context — is this always fatal? transient? known bug? -->
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--min-count", type=int, default=3)
    ap.add_argument("--service", type=str, default=None)
    args = ap.parse_args()

    db_path = ROOT / "data" / "logs.duckdb"
    if not db_path.exists():
        print(f"ERROR: {db_path} not found — server must run first to populate logs")
        sys.exit(1)

    kb_dir = ROOT / "data" / "kb"
    kb_dir.mkdir(parents=True, exist_ok=True)

    since = int(time.time()) - int(args.hours * 3600)
    con = duckdb.connect(str(db_path), read_only=True)

    clusters = cluster_logs(con, since, args.service, args.min_count)
    if not clusters:
        print("No clusters found matching criteria.")
        return

    existing_texts = " ".join(p.read_text() for p in kb_dir.glob("*.md"))
    created = 0
    skipped = 0

    for c in clusters:
        # Skip if a KB file already references this service+sample combo
        key = f"{c['service']} {c['sample'][:40]}".lower()
        if key in existing_texts.lower():
            skipped += 1
            continue

        h = hashlib.sha1(f"{c['service']}{c['pattern']}".encode()).hexdigest()[:8]
        fname = f"stub_{slug(c['service'])}_{h}.md"
        out_path = kb_dir / fname
        if out_path.exists():
            skipped += 1
            continue

        out_path.write_text(make_stub(c))
        print(f"  CREATED  {fname}  [{c['level']}] {c['service']} ×{c['n']}: {c['sample'][:60]}")
        created += 1

    print(f"\n{created} stubs created, {skipped} skipped (already covered).")
    print(f"Edit TODO sections in data/kb/stub_*.md, then POST /api/kb/reload")


if __name__ == "__main__":
    main()
