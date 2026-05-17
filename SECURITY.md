# Security Policy

## TL;DR

SystemHealth is designed for **trusted localhost / LAN use**. It ships with **no
authentication**. Do **not** expose port 9090 to the public internet. Never
commit a real `.env`, API key, or webhook URL.

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report privately via either channel:

1. GitHub Security Advisories — *Security* tab → *Report a vulnerability*
2. Email — replace with your actual maintainer address before publishing the
   repository, e.g. `security@example.com`

Include:
- Description of the vulnerability
- Steps to reproduce (PoC preferred)
- Potential impact (confidentiality / integrity / availability)
- Suggested fix, if any

You should expect an acknowledgement within 72 hours. Confirmed issues are
patched within 14 days where feasible, and reporters are credited in the
changelog unless they prefer anonymity.

---

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |
| < 0.1   | No        |

---

## Threat Model

### In scope

- Authentication bypass — the server intentionally has no auth; report any
  *hidden* bypass, unsafe defaults, or accidental privilege escalation
- Remote code execution via REST or WebSocket endpoints
- Path traversal in log-file tailing (`SH_LOG_APP_DIRS`)
- SQL / DuckDB injection in metrics or log queries
- WebSocket message injection that affects other browser sessions
- Server-Side Request Forgery (SSRF) via `SH_ALERT_WEBHOOK_URL` or
  `SH_OLLAMA_URL`
- Prompt injection that exfiltrates host data through the LLM gateway
- Tool-use abuse — an LLM-routed call to an MCP tool that returns sensitive
  host data to a remote provider
- Insecure deserialization in stored thresholds / pinned apps
- Dependency vulnerabilities flagged by `pip-audit` / `safety`

### Out of scope

- Denial of service against a local single-user instance
- Issues requiring physical access to the machine
- Missing HTTPS — tool is designed for LAN/localhost; terminate TLS at a
  reverse proxy if you must expose it
- Social-engineering of maintainers
- Self-XSS via the dashboard developer console

---

## Security Model

- **No authentication**: any process that can reach `:9090` has full access
  to host metrics, logs, and the LLM agent. Bind to `127.0.0.1` (default) or
  put the service behind a reverse proxy with auth before exposing it.
- **Read-only by design**: the agent's MCP tools only *read* the host. They
  do not restart services, write files, or change kernel parameters.
- **LLM provider data flow**: if you configure a cloud provider key
  (OpenAI / Anthropic / Gemini / Groq / NVIDIA / OpenRouter / GitHub), the
  agent will send process names, log snippets, and metric values to that
  provider. Review their data-retention policy before enabling.
- **Local-first default**: out of the box the agent uses Ollama on
  `127.0.0.1:11434`. No host data leaves the machine.
- **Sandboxed log dirs**: log tailing honours `SH_LOG_APP_DIRS` and rejects
  paths outside the allowlist. Report path-traversal bypasses.

---

## Secrets Handling

### Files that must never be committed

- `.env`, `.env.local`, `.env.production`, any `.env.*` except `.env.example`
- `*.pem`, `*.key`, `*.crt`, `*.p12`, `*.pfx`
- `id_rsa`, `id_ed25519`, `.netrc`, `.npmrc`, `.pypirc`
- `secrets.json`, `credentials.json`, `*_token*`, `*_secret*`,
  `*_credentials*`, `*api_key*`
- Cloud SDK creds — `.aws/`, `.azure/`, `.gcloud/`, `gcp-key*.json`,
  `service-account*.json`, `firebase-adminsdk*.json`

All of the above are excluded by `.gitignore`. Run `git status` before every
push regardless.

### If a secret was committed

1. **Rotate the secret immediately** at the provider — assume it is public.
2. Remove it from history. For a single file:
   ```bash
   git filter-repo --path .env --invert-paths     # preferred
   # or, if you cannot install filter-repo:
   git rebase -i --root                            # drop the offending commit
   ```
3. Force-push the cleaned branch and notify any collaborators to re-clone.
4. Add a regression entry to `.gitignore` if a new pattern slipped through.

### Pre-push checklist

```bash
# 1. Verify no secrets are staged or tracked
git ls-files | grep -E '\.env$|\.pem$|\.key$|secret|credential' && echo "STOP"

# 2. Diff scan
git diff --cached | grep -iE 'api[_-]?key|secret|token|password|bearer'

# 3. Run gitleaks (recommended)
gitleaks detect --no-banner --redact

# 4. Confirm .env is untracked
git ls-files --error-unmatch .env 2>&1 | grep -q 'did not match' && echo OK
```

A pre-commit hook is recommended:

```bash
pip install pre-commit detect-secrets
detect-secrets scan > .secrets.baseline
pre-commit install
```

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ["--baseline", ".secrets.baseline"]
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks:
      - id: gitleaks
```

---

## Hardening for Production

If you must expose SystemHealth beyond localhost:

1. Bind it to `127.0.0.1` and terminate the public listener at a reverse
   proxy (nginx, Caddy, Traefik).
2. Add authentication at the proxy — HTTP basic auth, OAuth2-proxy, mTLS, or
   Cloudflare Access.
3. Enable HTTPS at the proxy. The app itself does not handle TLS.
4. Restrict `SH_LOG_APP_DIRS` to the minimum directories required.
5. Run as a low-privilege user. `SH_ENABLE_DMESG=1` requires `adm` group or
   root — leave it off unless you need kernel logs.
6. Disable cloud LLM providers (`SH_*_PROVIDER=ollama`) for sensitive hosts.
7. Set `RELOAD=0`. The auto-reloader watches the filesystem and can be
   abused as a denial-of-service vector on shared hosts.
8. Pin dependencies (`uv pip compile` → `uv.lock`) and run `pip-audit` in CI.

---

## Disclosure Timeline

| Day | Action                                            |
|-----|---------------------------------------------------|
| 0   | Report received                                   |
| ≤3  | Acknowledgement to reporter                       |
| ≤14 | Patch developed and shared with reporter          |
| ≤30 | Patch released; advisory published; CVE requested |

Embargo can be extended by mutual agreement when coordination with
downstream packagers is required.
