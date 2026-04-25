#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/3] Python syntax check"
python3 -m compileall app tests run_server.py

echo "[2/3] Pytest"
pytest

echo "[3/3] Done"
echo "All local verification checks passed."
