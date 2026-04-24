#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-9090}"
RELOAD="${RELOAD:-1}"
APP="${APP:-app.main:app}"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

pre_stop_known_servers() {
  if ! command -v pkill >/dev/null 2>&1; then
    return 0
  fi
  pkill -TERM -f "uvicorn ${APP}" 2>/dev/null || true
  pkill -TERM -f "uvicorn .*${APP}" 2>/dev/null || true
  pkill -TERM -f "uvicorn .*--port ${PORT}" 2>/dev/null || true
  pkill -TERM -f "python.*-m uvicorn.*--port ${PORT}" 2>/dev/null || true
  pkill -TERM -f "python.*run_server.py" 2>/dev/null || true
  pkill -TERM -f "python.*-m app.main" 2>/dev/null || true
  pkill -TERM -f "watchfiles.*${ROOT_DIR}" 2>/dev/null || true
}

find_app_pids() {
  if ! command -v pgrep >/dev/null 2>&1; then
    return 0
  fi
  pgrep -f "uvicorn ${APP}" 2>/dev/null || true
  pgrep -f "uvicorn .*${APP}" 2>/dev/null || true
  pgrep -f "uvicorn .*--port ${PORT}" 2>/dev/null || true
  pgrep -f "python run_server.py" 2>/dev/null || true
  pgrep -f "python -m app.main" 2>/dev/null || true
  pgrep -f "${ROOT_DIR}.*uvicorn" 2>/dev/null || true
  pgrep -f "watchfiles.*${ROOT_DIR}" 2>/dev/null || true
}

find_port_pid() {
  local pid=""
  if command -v fuser >/dev/null 2>&1; then
    pid="$(fuser "$PORT"/tcp 2>/dev/null | tr ' ' '\n' | sed '/^$/d' | head -n 1 || true)"
  fi
  if [[ -z "$pid" ]] && command -v lsof >/dev/null 2>&1; then
    pid="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
  fi
  if [[ -z "$pid" ]] && command -v ss >/dev/null 2>&1; then
    pid="$(ss -ltnp "sport = :$PORT" 2>/dev/null | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | head -n 1 || true)"
  fi
  printf '%s' "$pid"
}

describe_pid() {
  local pid="$1"
  ps -p "$pid" -o pid=,cmd= 2>/dev/null | sed 's/^ *//'
}

mapfile -t app_pids < <(find_app_pids | sed '/^$/d' | sort -u)
if [[ "${#app_pids[@]}" -gt 0 ]]; then
  echo "Stopping existing SystemHealth server processes:"
  for pid in "${app_pids[@]}"; do
    echo "  $(describe_pid "$pid")"
  done
  kill -TERM "${app_pids[@]}" 2>/dev/null || true
fi

pre_stop_known_servers
sleep 1

pid="$(find_port_pid)"
if [[ -n "$pid" ]]; then
  echo "Port $PORT is already in use by: $(describe_pid "$pid")"
  echo "Stopping it with: kill -TERM $pid"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k -TERM "$PORT"/tcp >/dev/null 2>&1 || true
  else
    kill -TERM "$pid" 2>/dev/null || true
  fi
fi

if [[ "${#app_pids[@]}" -gt 0 || -n "$pid" ]]; then

  for _ in $(seq 1 30); do
    sleep 1
    mapfile -t app_pids < <(find_app_pids | sed '/^$/d' | sort -u)
    next_pid="$(find_port_pid)"
    if [[ "${#app_pids[@]}" -eq 0 && -z "$next_pid" ]]; then
      pid=""
      break
    fi
    pid="$next_pid"
  done

  if [[ "${#app_pids[@]}" -gt 0 || -n "$pid" ]]; then
    echo "Server processes still present after waiting."
    if [[ "${#app_pids[@]}" -gt 0 ]]; then
      echo "Force stop with: kill -KILL ${app_pids[*]}"
    fi
    if [[ -n "$pid" ]]; then
      echo "Port $PORT is still busy."
      echo "Force stop with: kill -KILL $pid"
    fi
    exit 1
  fi
fi

args=( "$APP" --host "$HOST" --port "$PORT" )
if [[ "$RELOAD" == "1" || "$RELOAD" == "true" || "$RELOAD" == "yes" ]]; then
  args+=( --reload )
fi

exec uvicorn "${args[@]}"
