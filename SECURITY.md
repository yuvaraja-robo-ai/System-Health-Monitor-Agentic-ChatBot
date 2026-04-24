# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email: **security@systemhealth.dev** (replace with your actual address before publishing)

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix

You will receive a response within 72 hours. If confirmed, a patch will be released within 14 days and you will be credited in the changelog unless you prefer anonymity.

## Scope

In scope:
- Authentication bypass (the server intentionally has no auth — document this clearly; do not add hidden auth bypasses)
- Remote code execution via API endpoints
- Path traversal in log file tailing (`SH_LOG_APP_DIRS`)
- SQLite/DuckDB injection
- WebSocket message injection affecting other sessions

Out of scope:
- Denial of service against a local single-user instance
- Issues requiring physical access to the machine
- Missing HTTPS (this tool is designed for LAN/localhost use)

## Security Model

SystemHealth is designed for **trusted local network or localhost use**. It has no built-in authentication. Do not expose port 9090 to the public internet without adding a reverse proxy with authentication (e.g., nginx + HTTP basic auth or OAuth2 proxy).
