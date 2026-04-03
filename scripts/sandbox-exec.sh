#!/usr/bin/env bash
# sandbox-exec.sh — Nexus Testing Sandbox Command Executor
# POSIX-compatible, Windows Git Bash compatible
# Executes a command inside a sandbox session with logging and safety checks.

set -euo pipefail

# --- Defaults ---
SESSION_ID=""
COMMAND=""
TIMEOUT_SECONDS=30
TAG=""
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SANDBOX_ROOT="$PROJECT_DIR/.nexus-sandbox"
SANDBOX_TOTAL_TIMEOUT=600  # 10 minutes total

# --- Command Blacklist ---
BLACKLISTED_PATTERNS=(
  "rm -rf /"
  "rm -rf ~"
  "rm -rf /*"
  "del /s /q C:\\"
  "format "
  "mkfs."
  "dd if="
  "curl "
  "wget "
  "|.*bash"
  "|.*sh"
  "|.*python"
)

# NOTE: curl|bash and wget|sh are checked via pipe pattern separately

# --- Parse Args ---
MODE="exec"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --session-id)
      SESSION_ID="$2"
      shift 2
      ;;
    --command)
      COMMAND="$2"
      shift 2
      ;;
    --timeout)
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --tag)
      TAG="$2"
      shift 2
      ;;
    --sandbox-root)
      SANDBOX_ROOT="$2"
      shift 2
      ;;
    --probe)
      MODE="probe"
      PROBE_TARGET="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: sandbox-exec.sh --session-id ID --command CMD [options]"
      echo ""
      echo "Executes a command inside a sandbox session with logging."
      echo ""
      echo "Options:"
      echo "  --session-id ID     Session ID (required)"
      echo "  --command CMD       Command to execute (required)"
      echo "  --timeout SECS      Timeout per command in seconds (default: 30)"
      echo "  --tag TAG           Test case tag (e.g. TC-47)"
      echo "  --sandbox-root PATH Sandbox root path"
      echo "  --probe node|python Probe runtime availability only (no execution)"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# --- Probe Mode ---
if [[ "$MODE" == "probe" ]]; then
  if [[ -z "${PROBE_TARGET:-}" ]]; then
    echo "ERROR: --probe requires an argument: node|python" >&2
    exit 1
  fi
  if [[ "$PROBE_TARGET" == "node" ]]; then
    if command -v node &>/dev/null; then
      echo "PROBE_RESULT=available"
      echo "VERSION=$(node -v 2>/dev/null)"
    else
      echo "PROBE_RESULT=unavailable"
      echo "VERSION="
    fi
  elif [[ "$PROBE_TARGET" == "python" ]]; then
    if command -v python &>/dev/null; then
      echo "PROBE_RESULT=available"
      echo "VERSION=$(python --version 2>&1 | sed 's/Python //')"
    elif command -v python3 &>/dev/null; then
      echo "PROBE_RESULT=available"
      echo "VERSION=$(python3 --version 2>&1 | sed 's/Python //')"
    else
      echo "PROBE_RESULT=unavailable"
      echo "VERSION="
    fi
  else
    echo "ERROR: Unknown probe target: $PROBE_TARGET" >&2
    exit 1
  fi
  exit 0
fi

# --- Validate Required Args ---
if [[ -z "$SESSION_ID" ]]; then
  echo "ERROR: --session-id is required" >&2
  exit 1
fi
if [[ -z "$COMMAND" ]]; then
  echo "ERROR: --command is required" >&2
  exit 1
fi

# --- Validate Session ID format ---
if ! echo "$SESSION_ID" | grep -qE '^[a-zA-Z0-9-]+$'; then
  echo "ERROR: Invalid session-id format" >&2
  exit 1
fi

SESSION_DIR="$SANDBOX_ROOT/$SESSION_ID"

# --- Verify session exists ---
if [[ ! -d "$SESSION_DIR" ]]; then
  echo "ERROR: Session does not exist: $SESSION_DIR" >&2
  exit 1
fi

WORKSPACE_DIR="$SESSION_DIR/workspace"
LOGS_DIR="$SESSION_DIR/logs"
EXIT_CODES_FILE="$LOGS_DIR/exit-codes.json"

# --- Check total sandbox timeout ---
META_FILE="$SESSION_DIR/META.json"
if [[ -f "$META_FILE" ]]; then
  TOTAL_MS=$(grep -o '"totalDurationMs": [0-9]*' "$META_FILE" | grep -o '[0-9]*' || echo "0")
  TOTAL_SECS=$((TOTAL_MS / 1000))
  if [[ $TOTAL_SECS -ge $SANDBOX_TOTAL_TIMEOUT ]]; then
    echo "ERROR: Sandbox total time limit reached (${TOTAL_SECS}s / ${SANDBOX_TOTAL_TIMEOUT}s)" >&2
    exit 1
  fi
fi

# --- Security: Check blacklisted patterns ---
BLOCKED=""
for pattern in "${BLACKLISTED_PATTERNS[@]}"; do
  if echo "$COMMAND" | grep -qE "$pattern"; then
    BLOCKED="$pattern"
    break
  fi
done

if [[ -n "$BLOCKED" ]]; then
  echo "BLOCKED=true"
  echo "REASON=Command matches blocked pattern: $BLOCKED"
  echo "EXIT_CODE=-1"
  # Log the blocked command
  TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
  SEQ=$(cat "$EXIT_CODES_FILE" 2>/dev/null | grep -c '"seq"' || echo "0")
  SEQ=$((SEQ + 1))
  echo "$COMMAND" > "$LOGS_DIR/${TIMESTAMP}-${SEQ}.blocked.log"
  exit 0
fi

# --- Read current seq number ---
if [[ -f "$EXIT_CODES_FILE" ]]; then
  SEQ=$(grep -c '"seq"' "$EXIT_CODES_FILE" 2>/dev/null || echo "0")
  SEQ=$((SEQ + 1))
else
  SEQ=1
  echo "[]" > "$EXIT_CODES_FILE"
fi

# --- Execute ---
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
STDOUT_LOG="$LOGS_DIR/${TIMESTAMP}-${SEQ}.stdout.log"
STDERR_LOG="$LOGS_DIR/${TIMESTAMP}-${SEQ}.stderr.log"
TAG_FIELD="${TAG:-}"

START_MS=$(date +%s%3N 2>/dev/null || python -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo "0")

# Run command with timeout, CWD = workspace
# Use 'timeout' on Linux, 'gtimeout' on macOS (coreutils), or fallback
TIMEOUT_CMD=""
if command -v timeout &>/dev/null; then
  TIMEOUT_CMD="timeout ${TIMEOUT_SECONDS}"
elif command -v gtimeout &>/dev/null; then
  TIMEOUT_CMD="gtimeout ${TIMEOUT_SECONDS}"
fi

ACTUAL_EXIT=0
cd "$WORKSPACE_DIR"
if [[ -n "$TIMEOUT_CMD" ]]; then
  $TIMEOUT_CMD bash -c "$COMMAND" > "$STDOUT_LOG" 2> "$STDERR_LOG" || ACTUAL_EXIT=$?
else
  # No timeout available, run directly
  bash -c "$COMMAND" > "$STDOUT_LOG" 2> "$STDERR_LOG" &
  CMD_PID=$!
  # Manual timeout via background + wait
  SECONDS_WAITED=0
  while kill -0 $CMD_PID 2>/dev/null; do
    if [[ $SECONDS_WAITED -ge $TIMEOUT_SECONDS ]]; then
      kill -TERM $CMD_PID 2>/dev/null
      sleep 1
      kill -KILL $CMD_PID 2>/dev/null
      ACTUAL_EXIT=124  # Same as timeout command exit code
      break
    fi
    sleep 1
    SECONDS_WAITED=$((SECONDS_WAITED + 1))
  done
  if [[ $ACTUAL_EXIT -eq 0 ]]; then
    wait $CMD_PID 2>/dev/null || ACTUAL_EXIT=$?
  fi
fi

END_MS=$(date +%s%3N 2>/dev/null || python -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo "0")
DURATION_MS=$((END_MS - START_MS))
if [[ $DURATION_MS -lt 0 ]]; then DURATION_MS=0; fi

# --- Append to exit-codes.json ---
# Read existing, append new entry, write back
EXISTING=$(cat "$EXIT_CODES_FILE" 2>/dev/null || echo "[]")
# Remove trailing ]
EXISTING="${EXISTING%]}"

NEW_ENTRY=$(cat <<ENTRYEOF
{"seq": $SEQ, "tag": "$TAG_FIELD", "command": $(echo "$COMMAND" | head -c 500 | python -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"(command logged)\""), "exitCode": $ACTUAL_EXIT, "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%S")", "durationMs": $DURATION_MS, "stdoutFile": "logs/${TIMESTAMP}-${SEQ}.stdout.log", "stderrFile": "logs/${TIMESTAMP}-${SEQ}.stderr.log"}
ENTRYEOF
)

if [[ "$EXISTING" == "[" || -z "$EXISTING" ]]; then
  echo "[${NEW_ENTRY}]" > "$EXIT_CODES_FILE"
else
  echo "${EXISTING},${NEW_ENTRY}]" > "$EXIT_CODES_FILE"
fi

# --- Update META.json ---
if [[ -f "$META_FILE" ]]; then
  # Update commandCount and totalDurationMs using sed
  OLD_COUNT=$(grep -o '"commandCount": [0-9]*' "$META_FILE" | grep -o '[0-9]*' || echo "0")
  NEW_COUNT=$((OLD_COUNT + 1))
  OLD_TOTAL=$(grep -o '"totalDurationMs": [0-9]*' "$META_FILE" | grep -o '[0-9]*' || echo "0")
  NEW_TOTAL=$((OLD_TOTAL + DURATION_MS))

  sed -i "s/\"commandCount\": [0-9]*/\"commandCount\": $NEW_COUNT/" "$META_FILE" 2>/dev/null || \
    sed -i '' "s/\"commandCount\": [0-9]*/\"commandCount\": $NEW_COUNT/" "$META_FILE"
  sed -i "s/\"totalDurationMs\": [0-9]*/\"totalDurationMs\": $NEW_TOTAL/" "$META_FILE" 2>/dev/null || \
    sed -i '' "s/\"totalDurationMs\": [0-9]*/\"totalDurationMs\": $NEW_TOTAL/" "$META_FILE"
fi

# --- Output ---
echo "EXIT_CODE=$ACTUAL_EXIT"
echo "STDOUT_FILE=logs/${TIMESTAMP}-${SEQ}.stdout.log"
echo "STDERR_FILE=logs/${TIMESTAMP}-${SEQ}.stderr.log"
echo "DURATION_MS=$DURATION_MS"
echo "SEQ=$SEQ"
