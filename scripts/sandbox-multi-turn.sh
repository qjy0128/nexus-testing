#!/usr/bin/env bash
# sandbox-multi-turn.sh - thin wrapper around the Python core implementation.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

PYTHON_BIN=""
if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: sandbox-multi-turn requires python or python3" >&2
  exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/sandbox_multi_turn.py" "$@"
