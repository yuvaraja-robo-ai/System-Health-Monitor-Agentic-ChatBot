# Contributing to SystemHealth

Thanks for contributing. This document covers dev setup, coding conventions, and the PR process.

---

## Dev Setup

```bash
git clone https://github.com/your-org/systemhealth.git
cd systemhealth

python3 -m venv .venv
source .venv/bin/activate

pip install -e ".[all]"
pip install pytest pytest-asyncio httpx
```

Run the server:
```bash
bash dev.sh
# http://localhost:9090
```

Run tests:
```bash
bash tools/test_before_push.sh
```

This is the required local verification step before opening or updating a PR.

---

## Project Structure

```
app/
  api/          REST endpoints
  analytics/    Health scoring, anomaly detection, correlation
  agent/        Chat layers: KB, LLM, diagnose
  alerts/       Webhook router, silence windows
  collectors/   Metric collectors (psutil, jtop, journald, …)
  db/           SQLite + DuckDB wrappers
  hub.py        In-memory pub/sub for live snapshots
  config.py     Pydantic settings (SH_* env vars)

tests/          pytest suite (session-scoped client fixture)
data/kb/        Runbook markdown files
tools/          Utility scripts, including pre-push verification

dashboard.jsx   React dashboard (CDN, no build step)
design/wireframes/  Prototype wireframes and design canvas
design/docs/        Design-specific reference docs
```

---

## Coding Conventions

- Python 3.10+, type hints on all public functions
- One collector per file in `app/collectors/`
- New API endpoints go in `app/api/`; register the router in `app/main.py`
- No comments unless the WHY is non-obvious
- No dead code, no backwards-compat shims
- Tests in `tests/` — use the session-scoped `client` fixture from `conftest.py` to avoid DuckDB lock conflicts

## Required Verification

Before every push, run:

```bash
bash tools/test_before_push.sh
```

This currently runs:

1. `python3 -m compileall app tests run_server.py`
2. `pytest`

Contributors should not push code without completing this local verification.

---

## Extending Keyword Routing

The chat agent matches questions to live-data handlers using keyword groups
defined in `app/agent/keywords.json`. To add a new topic or synonym:

```json
// app/agent/keywords.json
{
  "metrics": {
    "my_metric": {
      "keywords": ["my keyword", "synonym one", "synonym two"],
      "exclude": ["word that should prevent this match"]
    }
  }
}
```

Then handle the new group in `_direct_answer` (`app/api/chat.py`):

```python
if _kw_metric(q, "my_metric"):
    return "..."
```

To add reasoning/optimization keywords (questions that should go to the LLM
instead of returning a direct answer), append to the `reasoning` array:

```json
"reasoning": ["why", "optimize", "your new keyword here"]
```

No Python changes needed for adding new keywords or reasoning triggers —
only `keywords.json` needs editing.

---

## Adding a Knowledge Base Entry

Create a markdown file in `data/kb/`:

```markdown
---
title: "Descriptive title"
tags: [relevant, tags]
severity: info|warn|critical
---

# Title

## Steps
1. First step
2. Second step
```

Then reload:
```bash
curl -X POST http://localhost:9090/api/kb/reload
```

KB files in `data/kb/` (excluding `auto_*.md`) can be committed. Auto-generated stubs are gitignored.

KB implementation notes:

- KB build/query code lives in `app/agent/kb.py`
- Embeddings come from `app/agent/embed.py`
- Chat fallback and KB usage are exercised in `tests/test_kb_chat_flow.py`

---

## Pull Request Process

1. Fork the repo and create a branch: `git checkout -b feature/my-thing`
2. Make changes; add or update tests
3. Run `bash tools/test_before_push.sh` — contributors should do this before every push
4. Open a PR against `main`
5. Fill in the PR template
6. One maintainer review required before merge

---

## Reporting Issues

Use GitHub Issues. For security vulnerabilities, see [SECURITY.md](SECURITY.md) instead.

---

## License

By contributing, you agree your contributions are licensed under Apache 2.0.
