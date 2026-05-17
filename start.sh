#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-9090}"
export RELOAD="${RELOAD:-1}"

# ── ensure Ollama is running before app starts ────────────────
_OLLAMA_URL="http://127.0.0.1:11434"
if ! curl -fsS --max-time 1 "${_OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
  if command -v ollama >/dev/null 2>&1; then
    echo "[systemhealth] ollama not running — starting 'ollama serve' ..."
    ollama serve >/tmp/ollama-serve.log 2>&1 &
    for _i in 1 2 3 4 5 6 7 8 9 10; do
      sleep 1
      if curl -fsS --max-time 1 "${_OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
        echo "[systemhealth] ollama ready"
        break
      fi
    done
    if ! curl -fsS --max-time 1 "${_OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
      echo "[systemhealth] WARNING: ollama did not start in 10s — check /tmp/ollama-serve.log"
    fi
  else
    echo "[systemhealth] ollama not installed — local inference unavailable"
  fi
fi

if [[ -z "${SH_LLAMA_URL:-}" && -z "${SH_OLLAMA_URL:-}" ]]; then
  if curl -fsS "http://127.0.0.1:8080/health" >/dev/null 2>&1; then
    export SH_LLAMA_URL="http://127.0.0.1:8080"
  elif curl -fsS "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    export SH_OLLAMA_URL="http://127.0.0.1:11434"
  fi
fi

if [[ "${SH_ENABLE_KB:-0}" != "1" && -z "${SH_KB_DIR:-}" ]]; then
  export SH_KB_DIR="/tmp/systemhealth-empty-kb"
  mkdir -p "$SH_KB_DIR"
fi

echo "SystemHealth starting on http://${HOST}:${PORT}"
if [[ -n "${SH_LLAMA_URL:-}" ]]; then
  echo "LLM: llama.cpp at ${SH_LLAMA_URL}"
elif [[ -n "${SH_OLLAMA_URL:-}" ]]; then
  echo "LLM: Ollama at ${SH_OLLAMA_URL}"
else
  echo "LLM: disabled"
fi
if [[ "${SH_ENABLE_KB:-0}" != "1" ]]; then
  echo "KB: disabled for fast startup (set SH_ENABLE_KB=1 to enable)"
fi

# Prefer uv if available (recommended). Falls back to dev.sh (system uvicorn).
_stop() { kill "$CHILD" 2>/dev/null; wait "$CHILD" 2>/dev/null; exit 0; }
trap _stop INT TERM

if command -v uv >/dev/null 2>&1; then
  cd "$ROOT_DIR"
  echo "Runner: uv  (Ctrl+C to stop)"
  uv run uvicorn app.main:app --host "$HOST" --port "$PORT" $( [[ "$RELOAD" == "1" ]] && echo "--reload" ) &
else
  echo "Runner: dev.sh (uv not installed; install via 'pip install uv' for the recommended path)"
  bash "$ROOT_DIR/dev.sh" &
fi
CHILD=$!
wait $CHILD
