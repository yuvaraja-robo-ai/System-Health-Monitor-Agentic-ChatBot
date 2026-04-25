#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-9090}"
export RELOAD="${RELOAD:-1}"

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

exec bash "$ROOT_DIR/dev.sh"
