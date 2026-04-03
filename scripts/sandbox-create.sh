#!/usr/bin/env bash
# sandbox-create.sh — Nexus Testing Sandbox Creator
# POSIX-compatible, Windows Git Bash compatible
# Creates an isolated sandbox directory for test execution.

set -euo pipefail

# --- Defaults ---
RUNTIME="both"
SESSION_ID=""
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SANDBOX_ROOT="$PROJECT_DIR/.nexus-sandbox"

# --- Parse Args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --runtime)
      RUNTIME="$2"
      shift 2
      ;;
    --session-id)
      SESSION_ID="$2"
      shift 2
      ;;
    --sandbox-root)
      SANDBOX_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: sandbox-create.sh [--runtime node|python|both|none] [--session-id ID] [--sandbox-root PATH]"
      echo ""
      echo "Creates a sandbox directory structure for isolated test execution."
      echo ""
      echo "Options:"
      echo "  --runtime TYPE    Runtime to detect: node, python, both, none (default: both)"
      echo "  --session-id ID   Specify session ID (default: auto-generated)"
      echo "  --sandbox-root    Sandbox root path (default: .nexus-sandbox/ in project dir)"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# --- Generate Session ID ---
if [[ -z "$SESSION_ID" ]]; then
  TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
  RAND_HEX=$(printf '%06x' $((RANDOM % 16777216)))
  SESSION_ID="${TIMESTAMP}-${RAND_HEX}"
fi

# --- Validate Session ID (alphanumeric + dash only) ---
if ! echo "$SESSION_ID" | grep -qE '^[a-zA-Z0-9-]+$'; then
  echo "ERROR: Invalid session-id. Only alphanumeric and dash characters allowed." >&2
  exit 1
fi

SESSION_DIR="$SANDBOX_ROOT/$SESSION_ID"

# --- Check if already exists ---
if [[ -d "$SESSION_DIR" ]]; then
  echo "ERROR: Session directory already exists: $SESSION_DIR" >&2
  exit 1
fi

# --- Create Directory Structure ---
mkdir -p "$SESSION_DIR/workspace/fixtures"
mkdir -p "$SESSION_DIR/workspace/outputs"
mkdir -p "$SESSION_DIR/workspace/temp"
mkdir -p "$SESSION_DIR/runtime"
mkdir -p "$SESSION_DIR/logs"

# --- Probe Runtimes ---
NODE_VERSION=""
PYTHON_VERSION=""
CAPABILITIES="minimal"

if [[ "$RUNTIME" == "node" || "$RUNTIME" == "both" ]]; then
  if command -v node &>/dev/null; then
    NODE_VERSION=$(node -v 2>/dev/null || echo "error")
  fi
fi

if [[ "$RUNTIME" == "python" || "$RUNTIME" == "both" ]]; then
  if command -v python &>/dev/null; then
    PYTHON_VERSION=$(python --version 2>&1 | sed 's/Python //' || echo "error")
  elif command -v python3 &>/dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | sed 's/Python //' || echo "error")
  fi
fi

# Determine capabilities
if [[ -n "$NODE_VERSION" && -n "$PYTHON_VERSION" ]]; then
  CAPABILITIES="full"
elif [[ -n "$NODE_VERSION" || -n "$PYTHON_VERSION" ]]; then
  CAPABILITIES="partial"
else
  CAPABILITIES="minimal"
fi

# --- Write META.json ---
PLATFORM="$(uname -s 2>/dev/null | tr '[:upper:]' '[:lower:]')"
if [[ "$PLATFORM" == msys* || "$PLATFORM" == mingw* || "$PLATFORM" == cygwin* ]]; then
  PLATFORM="win32"
fi

cat > "$SESSION_DIR/META.json" <<METAEOF
{
  "sessionId": "$SESSION_ID",
  "createdAt": "$(date -u +"%Y-%m-%dT%H:%M:%S")",
  "status": "active",
  "platform": "$PLATFORM",
  "runtime": {
    "node": "$NODE_VERSION",
    "python": "$PYTHON_VERSION"
  },
  "capabilities": "$CAPABILITIES",
  "commandCount": 0,
  "totalDurationMs": 0
}
METAEOF

# --- Output ---
echo "SESSION_ID=$SESSION_ID"
echo "CAPABILITIES=$CAPABILITIES"
echo "NODE=$NODE_VERSION"
echo "PYTHON=$PYTHON_VERSION"
echo "SANDBOX_ROOT=$SESSION_DIR"
