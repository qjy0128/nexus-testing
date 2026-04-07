#!/usr/bin/env bash
# sandbox-exec.sh - Nexus Testing Sandbox Command Executor
# Logged command runner with optional container isolation.
# host-logged is not a container or VM security boundary.

set -euo pipefail

SESSION_ID=""
COMMAND=""
TIMEOUT_SECONDS=30
TAG=""
ACK_UNSAFE_EXEC="false"
BACKEND="host-logged"
CONTAINER_RUNTIME="auto"
CONTAINER_IMAGE="ubuntu:24.04"
CONTAINER_WORKDIR="/workspace"
ALLOW_NETWORK="false"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SANDBOX_ROOT="$PROJECT_DIR/.nexus-sandbox"
SANDBOX_TOTAL_TIMEOUT=600
MODE="exec"
PROBE_TARGET=""

BLACKLISTED_PATTERNS=(
  "rm -rf /"
  "rm -rf ~"
  "rm -rf /*"
  "del /s /q C:"
  "format "
  "mkfs."
  "dd if="
  "curl "
  "wget "
  "\\|[[:space:]]*bash"
  "\\|[[:space:]]*sh"
  "\\|[[:space:]]*python"
)

usage() {
  echo "Usage: sandbox-exec.sh --session-id ID --command CMD [options]"
  echo ""
  echo "Backends:"
  echo "  host-logged (default)  Logged host execution. Requires --ack-unsafe-exec."
  echo "  container             Containerized execution via docker or podman."
  echo ""
  echo "Options:"
  echo "  --session-id ID          Session ID (required unless --probe is used)"
  echo "  --command CMD            Command to execute (required unless --probe is used)"
  echo "  --timeout SECS           Timeout per command in seconds (default: 30)"
  echo "  --tag TAG                Test case tag (e.g. TC-47)"
  echo "  --sandbox-root PATH      Sandbox root path"
  echo "  --backend MODE           host-logged | container (default: host-logged)"
  echo "  --ack-unsafe-exec        Required for host-logged backend"
  echo "  --container-runtime RT   auto | docker | podman (default: auto)"
  echo "  --container-image IMAGE  Container image for container backend"
  echo "  --container-workdir DIR  Container workdir mount target (default: /workspace)"
  echo "  --allow-network          Enable container network access"
  echo "  --probe TARGET           node | python | container | docker | podman"
}

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
    --backend)
      BACKEND="$2"
      shift 2
      ;;
    --ack-unsafe-exec)
      ACK_UNSAFE_EXEC="true"
      shift
      ;;
    --container-runtime)
      CONTAINER_RUNTIME="$2"
      shift 2
      ;;
    --container-image)
      CONTAINER_IMAGE="$2"
      shift 2
      ;;
    --container-workdir)
      CONTAINER_WORKDIR="$2"
      shift 2
      ;;
    --allow-network)
      ALLOW_NETWORK="true"
      shift
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
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

find_timeout_binary() {
  if command -v timeout >/dev/null 2>&1; then
    echo "timeout"
    return 0
  fi
  if command -v gtimeout >/dev/null 2>&1; then
    echo "gtimeout"
    return 0
  fi
  return 1
}

check_container_runtime() {
  local candidate="$1"
  if ! command -v "$candidate" >/dev/null 2>&1; then
    return 1
  fi
  if "$candidate" version >/dev/null 2>&1; then
    return 0
  fi
  if "$candidate" --version >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

find_container_runtime() {
  local candidates=()
  case "$CONTAINER_RUNTIME" in
    auto)
      candidates=(docker podman)
      ;;
    docker|podman)
      candidates=("$CONTAINER_RUNTIME")
      ;;
    *)
      echo "ERROR: Unsupported container runtime: $CONTAINER_RUNTIME" >&2
      return 1
      ;;
  esac

  local candidate
  for candidate in "${candidates[@]}"; do
    if check_container_runtime "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done

  if [[ "$CONTAINER_RUNTIME" == "auto" ]]; then
    echo "ERROR: No runnable container runtime found (docker/podman)" >&2
  else
    echo "ERROR: Requested container runtime is not runnable: $CONTAINER_RUNTIME" >&2
  fi
  return 1
}

normalize_mount_source() {
  local raw_path="$1"
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$raw_path"
    return 0
  fi
  printf '%s' "$raw_path"
}

run_with_timeout() {
  local stdout_log="$1"
  local stderr_log="$2"
  shift 2
  local -a command_args=("$@")
  local timeout_binary=""
  timeout_binary="$(find_timeout_binary || true)"
  local actual_exit=0

  if [[ -n "$timeout_binary" ]]; then
    "$timeout_binary" "$TIMEOUT_SECONDS" "${command_args[@]}" >"$stdout_log" 2>"$stderr_log" || actual_exit=$?
  else
    "${command_args[@]}" >"$stdout_log" 2>"$stderr_log" &
    local cmd_pid=$!
    local seconds_waited=0
    while kill -0 "$cmd_pid" 2>/dev/null; do
      if [[ $seconds_waited -ge $TIMEOUT_SECONDS ]]; then
        kill -TERM "$cmd_pid" 2>/dev/null || true
        sleep 1
        kill -KILL "$cmd_pid" 2>/dev/null || true
        actual_exit=124
        break
      fi
      sleep 1
      seconds_waited=$((seconds_waited + 1))
    done
    if [[ $actual_exit -eq 0 ]]; then
      wait "$cmd_pid" 2>/dev/null || actual_exit=$?
    fi
  fi

  return "$actual_exit"
}

if [[ "$MODE" == "probe" ]]; then
  if [[ -z "$PROBE_TARGET" ]]; then
    echo "ERROR: --probe requires an argument" >&2
    exit 1
  fi

  case "$PROBE_TARGET" in
    node)
      if command -v node >/dev/null 2>&1; then
        echo "PROBE_RESULT=available"
        echo "VERSION=$(node -v 2>/dev/null)"
      else
        echo "PROBE_RESULT=unavailable"
        echo "VERSION="
      fi
      ;;
    python)
      if command -v python >/dev/null 2>&1; then
        echo "PROBE_RESULT=available"
        echo "VERSION=$(python --version 2>&1 | sed 's/Python //')"
      elif command -v python3 >/dev/null 2>&1; then
        echo "PROBE_RESULT=available"
        echo "VERSION=$(python3 --version 2>&1 | sed 's/Python //')"
      else
        echo "PROBE_RESULT=unavailable"
        echo "VERSION="
      fi
      ;;
    container)
      if runtime="$(find_container_runtime)"; then
        echo "PROBE_RESULT=available"
        echo "RUNTIME=$runtime"
      else
        echo "PROBE_RESULT=unavailable"
        echo "RUNTIME="
      fi
      ;;
    docker|podman)
      if check_container_runtime "$PROBE_TARGET"; then
        echo "PROBE_RESULT=available"
        echo "RUNTIME=$PROBE_TARGET"
      else
        echo "PROBE_RESULT=unavailable"
        echo "RUNTIME="
      fi
      ;;
    *)
      echo "ERROR: Unknown probe target: $PROBE_TARGET" >&2
      exit 1
      ;;
  esac
  exit 0
fi

case "$BACKEND" in
  host-logged|container)
    ;;
  *)
    echo "ERROR: --backend must be host-logged or container" >&2
    exit 1
    ;;
esac

if [[ -z "$SESSION_ID" ]]; then
  echo "ERROR: --session-id is required" >&2
  exit 1
fi
if [[ -z "$COMMAND" ]]; then
  echo "ERROR: --command is required" >&2
  exit 1
fi
if [[ "$BACKEND" == "host-logged" && "$ACK_UNSAFE_EXEC" != "true" ]]; then
  echo "ERROR: host-logged backend requires --ack-unsafe-exec because it is not a secure sandbox" >&2
  exit 1
fi
if [[ ! "$TIMEOUT_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --timeout must be an integer" >&2
  exit 1
fi

if ! echo "$SESSION_ID" | grep -qE '^[a-zA-Z0-9-]+$'; then
  echo "ERROR: Invalid session-id format" >&2
  exit 1
fi

SESSION_DIR="$SANDBOX_ROOT/$SESSION_ID"
if [[ ! -d "$SESSION_DIR" ]]; then
  echo "ERROR: Session does not exist: $SESSION_DIR" >&2
  exit 1
fi

WORKSPACE_DIR="$SESSION_DIR/workspace"
LOGS_DIR="$SESSION_DIR/logs"
EXIT_CODES_FILE="$LOGS_DIR/exit-codes.json"
AUDIT_LOCK_DIR="$LOGS_DIR/.audit-lock"
META_FILE="$SESSION_DIR/META.json"

if [[ -f "$META_FILE" ]]; then
  TOTAL_MS="$(grep -o '"totalDurationMs": [0-9]*' "$META_FILE" 2>/dev/null | head -n 1 | grep -o '[0-9]*' | head -n 1 || true)"
  TOTAL_MS="${TOTAL_MS:-0}"
  TOTAL_SECS=$((TOTAL_MS / 1000))
  if [[ $TOTAL_SECS -ge $SANDBOX_TOTAL_TIMEOUT ]]; then
    echo "ERROR: Sandbox total time limit reached (${TOTAL_SECS}s / ${SANDBOX_TOTAL_TIMEOUT}s)" >&2
    exit 1
  fi
fi

acquire_audit_lock() {
  local waited=0
  while ! mkdir "$AUDIT_LOCK_DIR" 2>/dev/null; do
    if [[ $waited -ge 100 ]]; then
      echo "ERROR: Timed out waiting for sandbox audit lock" >&2
      exit 1
    fi
    sleep 0.05
    waited=$((waited + 1))
  done
}

release_audit_lock() {
  rmdir "$AUDIT_LOCK_DIR" 2>/dev/null || true
}

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
  echo "BACKEND=$BACKEND"
  echo "ISOLATION_LEVEL=$BACKEND"
  echo "EXIT_CODE=-1"
  TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
  echo "$COMMAND" > "$LOGS_DIR/${TIMESTAMP}-$$.blocked.log"
  exit 0
fi

TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
STDOUT_LOG="$LOGS_DIR/${TIMESTAMP}-$$.stdout.log"
STDERR_LOG="$LOGS_DIR/${TIMESTAMP}-$$.stderr.log"
STDOUT_REL="logs/${TIMESTAMP}-$$.stdout.log"
STDERR_REL="logs/${TIMESTAMP}-$$.stderr.log"
TAG_FIELD="${TAG:-}"
START_MS=$(date +%s%3N 2>/dev/null || python -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo "0")

BACKEND_FIELD="$BACKEND"
ISOLATION_LEVEL="$BACKEND"
CONTAINER_RUNTIME_FIELD="none"
CONTAINER_IMAGE_FIELD="none"
NETWORK_ACCESS="host"
UNSAFE_EXEC_ACKNOWLEDGED="$ACK_UNSAFE_EXEC"

cd "$WORKSPACE_DIR"

declare -a EXEC_CMD=()
if [[ "$BACKEND" == "host-logged" ]]; then
  EXEC_CMD=(bash -c "$COMMAND")
else
  RUNTIME_BIN="$(find_container_runtime)"
  CONTAINER_RUNTIME_FIELD="$RUNTIME_BIN"
  CONTAINER_IMAGE_FIELD="$CONTAINER_IMAGE"
  NETWORK_ACCESS="disabled"
  MOUNT_SOURCE="$(normalize_mount_source "$WORKSPACE_DIR")"
  EXEC_CMD=(
    "$RUNTIME_BIN" run --rm
    --name "nexus-exec-${SESSION_ID}-$$"
    --workdir "$CONTAINER_WORKDIR"
    --volume "${MOUNT_SOURCE}:${CONTAINER_WORKDIR}"
    -e "NEXUS_EXEC_BACKEND=container"
    -e "NEXUS_SESSION_ID=$SESSION_ID"
    -e "NEXUS_TEST_TAG=$TAG_FIELD"
  )
  if [[ "$ALLOW_NETWORK" == "true" ]]; then
    NETWORK_ACCESS="enabled"
  else
    EXEC_CMD+=(--network none)
  fi
  EXEC_CMD+=("$CONTAINER_IMAGE" bash -lc "$COMMAND")
  UNSAFE_EXEC_ACKNOWLEDGED="false"
fi

ACTUAL_EXIT=0
run_with_timeout "$STDOUT_LOG" "$STDERR_LOG" "${EXEC_CMD[@]}" || ACTUAL_EXIT=$?

END_MS=$(date +%s%3N 2>/dev/null || python -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo "0")
DURATION_MS=$((END_MS - START_MS))
if [[ $DURATION_MS -lt 0 ]]; then
  DURATION_MS=0
fi

NEW_ENTRY=$(cat <<ENTRYEOF
{"seq": __SEQ__, "tag": "$TAG_FIELD", "command": $(echo "$COMMAND" | head -c 500 | python -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"(command logged)\""), "exitCode": $ACTUAL_EXIT, "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%S")", "durationMs": $DURATION_MS, "stdoutFile": "$STDOUT_REL", "stderrFile": "$STDERR_REL", "backend": "$BACKEND_FIELD", "isolationLevel": "$ISOLATION_LEVEL", "containerRuntime": "$CONTAINER_RUNTIME_FIELD", "containerImage": "$CONTAINER_IMAGE_FIELD", "networkAccess": "$NETWORK_ACCESS"}
ENTRYEOF
)

acquire_audit_lock
trap 'release_audit_lock' EXIT
if [[ -f "$EXIT_CODES_FILE" ]]; then
  EXISTING=$(cat "$EXIT_CODES_FILE" 2>/dev/null || echo "[]")
  SEQ="$(grep -c '"seq"' "$EXIT_CODES_FILE" 2>/dev/null || true)"
  SEQ="${SEQ:-0}"
  SEQ=$((SEQ + 1))
else
  EXISTING="[]"
  SEQ=1
fi
EXISTING="${EXISTING%]}"
NEW_ENTRY="${NEW_ENTRY/__SEQ__/$SEQ}"
if [[ "$EXISTING" == "[" || -z "$EXISTING" ]]; then
  echo "[${NEW_ENTRY}]" > "$EXIT_CODES_FILE"
else
  echo "${EXISTING},${NEW_ENTRY}]" > "$EXIT_CODES_FILE"
fi

if [[ -f "$META_FILE" ]]; then
  OLD_COUNT="$(grep -o '"commandCount": [0-9]*' "$META_FILE" 2>/dev/null | head -n 1 | grep -o '[0-9]*' | head -n 1 || true)"
  OLD_COUNT="${OLD_COUNT:-0}"
  NEW_COUNT=$((OLD_COUNT + 1))
  OLD_TOTAL="$(grep -o '"totalDurationMs": [0-9]*' "$META_FILE" 2>/dev/null | head -n 1 | grep -o '[0-9]*' | head -n 1 || true)"
  OLD_TOTAL="${OLD_TOTAL:-0}"
  NEW_TOTAL=$((OLD_TOTAL + DURATION_MS))

  sed -i "s/\"commandCount\": [0-9]*/\"commandCount\": $NEW_COUNT/" "$META_FILE" 2>/dev/null || \
    sed -i '' "s/\"commandCount\": [0-9]*/\"commandCount\": $NEW_COUNT/" "$META_FILE"
  sed -i "s/\"totalDurationMs\": [0-9]*/\"totalDurationMs\": $NEW_TOTAL/" "$META_FILE" 2>/dev/null || \
    sed -i '' "s/\"totalDurationMs\": [0-9]*/\"totalDurationMs\": $NEW_TOTAL/" "$META_FILE"
fi
release_audit_lock
trap - EXIT

echo "EXIT_CODE=$ACTUAL_EXIT"
echo "STDOUT_FILE=$STDOUT_REL"
echo "STDERR_FILE=$STDERR_REL"
echo "DURATION_MS=$DURATION_MS"
echo "BACKEND=$BACKEND_FIELD"
echo "ISOLATION_LEVEL=$ISOLATION_LEVEL"
echo "CONTAINER_RUNTIME=$CONTAINER_RUNTIME_FIELD"
echo "CONTAINER_IMAGE=$CONTAINER_IMAGE_FIELD"
echo "NETWORK_ACCESS=$NETWORK_ACCESS"
echo "UNSAFE_EXEC_ACKNOWLEDGED=$UNSAFE_EXEC_ACKNOWLEDGED"
echo "SEQ=$SEQ"
