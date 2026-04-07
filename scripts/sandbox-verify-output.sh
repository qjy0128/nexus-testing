#!/usr/bin/env bash
# sandbox-verify-output.sh — Nexus Testing Skill Output Verification
# POSIX-compatible, Windows Git Bash compatible
# Executes a skill's underlying script and verifies the output against expected format.
#
# Supports three verification modes:
# 1. Pattern match: --expected-pattern (regex that must appear)
# 2. Expected file: --expected-file (compare against exact file)
# 3. Expected outputs dir: --expected-dir (compare against expected_outputs/ directory)
#
# The expected_outputs/ directory structure:
#   expected_outputs/
#     {script-name}/
#       {args-hash}/
#         expected.txt       # Expected output content
#         patterns.txt       # Required regex patterns (one per line)
#         contains.txt       # Required substrings (one per line)

set -euo pipefail

# --- Defaults ---
SESSION_ID=""
SKILL_DIR=""
SCRIPT_CMD=""
SCRIPT_ARGS=""
EXPECTED_PATTERN=""
EXPECTED_FILE=""
EXPECTED_DIR=""
OUTPUT_TYPE="json"  # json | text | markdown | table
VERIFY_FIELD=""
COMPARE_MODE="pattern"  # pattern | strict | contains
TIMEOUT_SECONDS=30
TAG=""
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SANDBOX_ROOT="$PROJECT_DIR/.nexus-sandbox"

json_escape() {
  printf '%s' "$1" | sed ':a;N;$!ba;s/\\/\\\\/g;s/"/\\"/g;s/\r/\\r/g;s/\n/\\n/g'
}

# --- Parse Args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --session-id)
      SESSION_ID="$2"
      shift 2
      ;;
    --skill-dir)
      SKILL_DIR="$2"
      shift 2
      ;;
    --script)
      SCRIPT_CMD="$2"
      shift 2
      ;;
    --script-args)
      SCRIPT_ARGS="$2"
      shift 2
      ;;
    --expected-pattern)
      EXPECTED_PATTERN="$2"
      shift 2
      ;;
    --expected-file)
      EXPECTED_FILE="$2"
      shift 2
      ;;
    --expected-dir)
      EXPECTED_DIR="$2"
      shift 2
      ;;
    --output-type)
      OUTPUT_TYPE="$2"
      shift 2
      ;;
    --verify-field)
      VERIFY_FIELD="$2"
      shift 2
      ;;
    --compare-mode)
      COMPARE_MODE="$2"
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
    -h|--help)
      echo "Usage: sandbox-verify-output.sh [options]"
      echo ""
      echo "Executes a skill's underlying script and verifies output against expected format."
      echo ""
      echo "Verification Modes:"
      echo "  1. Pattern match: --expected-pattern REGEX"
      echo "  2. Exact file: --expected-file /path/to/expected.txt"
      echo "  3. Expected outputs dir: --expected-dir /path/to/expected_outputs/"
      echo ""
      echo "Options:"
      echo "  --session-id ID         Sandbox session ID (required)"
      echo "  --skill-dir PATH       Skill directory containing scripts/ (required)"
      echo "  --script CMD           Script command to execute (required)"
      echo "                           e.g., 'node' or 'python'"
      echo "  --script-args ARGS     Script arguments (required)"
      echo "                           e.g., 'scripts/action-cli.ts decide --type exec_command'"
      echo "  --expected-pattern RE   Regex pattern that MUST appear in output (mode 1)"
      echo "  --expected-file FILE   File containing expected output (mode 2)"
      echo "  --expected-dir DIR     Directory with expected_outputs/ structure (mode 3)"
      echo "  --compare-mode MODE    Comparison mode: pattern|strict|contains (default: pattern)"
      echo "  --output-type TYPE     Output format: json|text|markdown|table (default: json)"
      echo "  --verify-field FIELD   JSON field name to verify (for json output)"
      echo "                           e.g., 'decision' to verify output.decision"
      echo "  --timeout SECS         Timeout in seconds (default: 30)"
      echo "  --tag TAG              Test case tag (e.g. OUT-001)"
      echo "  --sandbox-root PATH   Sandbox root path"
      echo ""
      echo "Expected Outputs Directory Structure:"
      echo "  expected_outputs/"
      echo "    {script-name}/"
      echo "      {args-hash}/"
      echo "        expected.txt      # Exact expected output"
      echo "        patterns.txt      # Required regex patterns (one per line)"
      echo "        contains.txt     # Required substrings (one per line)"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# --- Validate Required Args ---
if [[ -z "$SESSION_ID" ]]; then
  echo "ERROR: --session-id is required" >&2
  exit 1
fi
if [[ -z "$SKILL_DIR" ]]; then
  echo "ERROR: --skill-dir is required" >&2
  exit 1
fi
if [[ -z "$SCRIPT_CMD" ]]; then
  echo "ERROR: --script is required" >&2
  exit 1
fi
if [[ -z "$SCRIPT_ARGS" ]]; then
  echo "ERROR: --script-args is required" >&2
  exit 1
fi

# --- Determine verification mode ---
VERIFY_MODE=""
if [[ -n "$EXPECTED_DIR" ]]; then
  VERIFY_MODE="expected-dir"
elif [[ -n "$EXPECTED_FILE" ]]; then
  VERIFY_MODE="expected-file"
elif [[ -n "$EXPECTED_PATTERN" ]]; then
  VERIFY_MODE="pattern"
else
  echo "ERROR: One of --expected-pattern, --expected-file, or --expected-dir is required" >&2
  exit 1
fi

# --- Validate Session ---
SESSION_DIR="$SANDBOX_ROOT/$SESSION_ID"
if [[ ! -d "$SESSION_DIR" ]]; then
  echo "ERROR: Session does not exist: $SESSION_DIR" >&2
  exit 1
fi

WORKSPACE_DIR="$SESSION_DIR/workspace"
LOGS_DIR="$SESSION_DIR/logs"

# --- Resolve skill directory ---
if [[ ! -d "$SKILL_DIR" ]]; then
  echo "ERROR: Skill directory does not exist: $SKILL_DIR" >&2
  exit 1
fi

# --- Find expected output if using expected-dir mode ---
if [[ "$VERIFY_MODE" == "expected-dir" ]]; then
  if [[ ! -d "$EXPECTED_DIR" ]]; then
    echo "ERROR: Expected outputs directory does not exist: $EXPECTED_DIR" >&2
    exit 1
  fi

  # Extract script name and compute args hash
  SCRIPT_NAME=$(basename "$SCRIPT_CMD" | sed 's/\.[^.]*$//')
  ARGS_HASH=$(echo "$SCRIPT_ARGS" | md5sum 2>/dev/null | cut -d' ' -f1 || echo "$SCRIPT_ARGS" | cksum | cut -d' ' -f1)

  EXPECTED_SUBDIR="$EXPECTED_DIR/$SCRIPT_NAME/$ARGS_HASH"

  if [[ -d "$EXPECTED_SUBDIR" ]]; then
    echo "Found expected outputs: $EXPECTED_SUBDIR"
  else
    echo "WARNING: No expected outputs found for $SCRIPT_NAME with args hash $ARGS_HASH"
    echo "  Looked in: $EXPECTED_SUBDIR"
    # Try to find any matching subdir
    POSSIBLE_DIRS=$(find "$EXPECTED_DIR/$SCRIPT_NAME" -type d 2>/dev/null | head -5 || true)
    if [[ -n "$POSSIBLE_DIRS" ]]; then
      echo "  Did you mean one of these?"
      echo "$POSSIBLE_DIRS"
    fi
  fi
fi

# --- Execute the script ---
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
SEQ=$(cat "$LOGS_DIR/exit-codes.json" 2>/dev/null | grep -c '"seq"' || echo "0")
SEQ=$((SEQ + 1))

STDOUT_LOG="$LOGS_DIR/${TIMESTAMP}-${SEQ}-verify.stdout.log"
STDERR_LOG="$LOGS_DIR/${TIMESTAMP}-${SEQ}-verify.stderr.log"

START_MS=$(date +%s%3N 2>/dev/null || python -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo "0")

# Build the full command
FULL_CMD="cd \"$SKILL_DIR\" && $SCRIPT_CMD $SCRIPT_ARGS"

# Execute with timeout
ACTUAL_EXIT=0
cd "$WORKSPACE_DIR"

TIMEOUT_CMD=""
if command -v timeout &>/dev/null; then
  TIMEOUT_CMD="timeout ${TIMEOUT_SECONDS}"
elif command -v gtimeout &>/dev/null; then
  TIMEOUT_CMD="gtimeout ${TIMEOUT_SECONDS}"
fi

if [[ -n "$TIMEOUT_CMD" ]]; then
  $TIMEOUT_CMD bash -c "$FULL_CMD" > "$STDOUT_LOG" 2> "$STDERR_LOG" || ACTUAL_EXIT=$?
else
  bash -c "$FULL_CMD" > "$STDOUT_LOG" 2> "$STDERR_LOG" || ACTUAL_EXIT=$?
fi

END_MS=$(date +%s%3N 2>/dev/null || python -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo "0")
DURATION_MS=$((END_MS - START_MS))
if [[ $DURATION_MS -lt 0 ]]; then DURATION_MS=0; fi

# --- Read actual output ---
if [[ -f "$STDOUT_LOG" ]]; then
  ACTUAL_OUTPUT=$(cat "$STDOUT_LOG")
else
  ACTUAL_OUTPUT=""
fi

# --- Verification ---
VERIFICATION_PASSED="false"
VERIFICATION_ERROR=""
PATTERN_MATCH="false"
FIELD_VALUE=""
FIELD_VERIFY="not_required"
MATCH_SCORE="0"

case "$VERIFY_MODE" in
  pattern)
    # Check 1: Pattern match
    if echo "$ACTUAL_OUTPUT" | grep -qE "$EXPECTED_PATTERN"; then
      PATTERN_MATCH="true"
      VERIFICATION_PASSED="true"
    else
      PATTERN_MATCH="false"
      VERIFICATION_ERROR="Expected pattern '$EXPECTED_PATTERN' not found in output"
    fi
    ;;

  expected-file)
    # Compare against expected file
    if [[ ! -f "$EXPECTED_FILE" ]]; then
      VERIFICATION_ERROR="Expected file not found: $EXPECTED_FILE"
    else
      EXPECTED_CONTENT=$(cat "$EXPECTED_FILE")
      if [[ "$ACTUAL_OUTPUT" == "$EXPECTED_CONTENT" ]]; then
        VERIFICATION_PASSED="true"
        MATCH_SCORE="100"
      else
        # Calculate similarity
        PYTHON_CMD="python"
        command -v python &>/dev/null || PYTHON_CMD="python3"
        if command -v "$PYTHON_CMD" &>/dev/null; then
          MATCH_SCORE=$(
            "$PYTHON_CMD" - "$STDOUT_LOG" "$EXPECTED_FILE" <<'PY' 2>/dev/null || echo "0"
import difflib
import pathlib
import sys

actual = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
expected = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8", errors="replace")
ratio = difflib.SequenceMatcher(None, actual, expected).ratio()
print(int(ratio * 100))
PY
          )
        fi
        VERIFICATION_ERROR="Output does not match expected file exactly"
      fi
    fi
    ;;

  expected-dir)
    # Check expected_outputs directory
    CHECKS_PASSED=0
    CHECKS_TOTAL=0

    # Check patterns.txt
    if [[ -f "$EXPECTED_SUBDIR/patterns.txt" ]]; then
      CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
      MISSING_PATTERNS=""
      while IFS= read -r pattern || [[ -n "$pattern" ]]; do
        [[ -z "$pattern" || "$pattern" =~ ^# ]] && continue
        if echo "$ACTUAL_OUTPUT" | grep -qE "$pattern"; then
          CHECKS_PASSED=$((CHECKS_PASSED + 1))
        else
          MISSING_PATTERNS="${MISSING_PATTERNS}  - Pattern not found: ${pattern}\n"
        fi
      done < "$EXPECTED_SUBDIR/patterns.txt"

      if [[ -n "$MISSING_PATTERNS" ]]; then
        VERIFICATION_ERROR="Missing patterns:\n${MISSING_PATTERNS}"
      fi
    fi

    # Check contains.txt
    if [[ -f "$EXPECTED_SUBDIR/contains.txt" ]]; then
      CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
      MISSING_SUBSTRINGS=""
      while IFS= read -r substring || [[ -n "$substring" ]]; do
        [[ -z "$substring" || "$substring" =~ ^# ]] && continue
        if echo "$ACTUAL_OUTPUT" | grep -qF -- "$substring"; then
          CHECKS_PASSED=$((CHECKS_PASSED + 1))
        else
          MISSING_SUBSTRINGS="${MISSING_SUBSTRINGS}  - Substring not found: ${substring}\n"
        fi
      done < "$EXPECTED_SUBDIR/contains.txt"

      if [[ -n "$MISSING_SUBSTRINGS" ]]; then
        VERIFICATION_ERROR="${VERIFICATION_ERROR}Missing substrings:\n${MISSING_SUBSTRINGS}"
      fi
    fi

    # Check expected.txt (strict match)
    if [[ -f "$EXPECTED_SUBDIR/expected.txt" ]]; then
      CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
      EXPECTED_CONTENT=$(cat "$EXPECTED_SUBDIR/expected.txt")
      if [[ "$ACTUAL_OUTPUT" == "$EXPECTED_CONTENT" ]]; then
        CHECKS_PASSED=$((CHECKS_PASSED + 1))
      else
        VERIFICATION_ERROR="${VERIFICATION_ERROR}Strict match failed for expected.txt"
      fi
    fi

    if [[ $CHECKS_TOTAL -eq 0 ]]; then
      VERIFICATION_PASSED="true"
      MATCH_SCORE="100"
    elif [[ $CHECKS_PASSED -eq $CHECKS_TOTAL ]]; then
      VERIFICATION_PASSED="true"
      MATCH_SCORE="100"
    else
      MATCH_SCORE=$((CHECKS_PASSED * 100 / CHECKS_TOTAL))
    fi
    ;;
esac

# Check 2: JSON field verification (if specified)
if [[ "$VERIFICATION_PASSED" == "true" && -n "$VERIFY_FIELD" && "$OUTPUT_TYPE" == "json" ]]; then
  PYTHON_CMD="python"
  command -v python &>/dev/null || PYTHON_CMD="python3"

  if command -v "$PYTHON_CMD" &>/dev/null; then
    FIELD_CHECK=$(
      "$PYTHON_CMD" - "$STDOUT_LOG" "$VERIFY_FIELD" <<'PY' 2>/dev/null
import json
import pathlib
import sys

try:
    data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace"))
    value = data
    for key in sys.argv[2].split("."):
        value = value[key]
    print("FOUND:" + str(value))
except Exception as exc:
    print("ERROR:" + str(exc))
    sys.exit(1)
PY
    )

    if echo "$FIELD_CHECK" | grep -q "^FOUND:"; then
      FIELD_VALUE=$(echo "$FIELD_CHECK" | sed 's/^FOUND://')
      FIELD_VERIFY="true"
    else
      FIELD_VALUE=""
      FIELD_VERIFY="false"
      VERIFICATION_PASSED="false"
      VERIFICATION_ERROR="$VERIFICATION_ERROR; JSON field '$VERIFY_FIELD' not found"
    fi
  else
    FIELD_VERIFY="skipped"
  fi
else
  FIELD_VERIFY="not_required"
fi

# --- Write verification log ---
VERIFICATION_FILE="$LOGS_DIR/${TIMESTAMP}-${SEQ}-verification.json"
PYTHON_CMD="python"
command -v python &>/dev/null || PYTHON_CMD="python3"
if command -v "$PYTHON_CMD" &>/dev/null; then
  "$PYTHON_CMD" - "$VERIFICATION_FILE" \
    "$SESSION_ID" \
    "$SKILL_DIR" \
    "$SCRIPT_CMD" \
    "$SCRIPT_ARGS" \
    "$VERIFY_MODE" \
    "${EXPECTED_PATTERN:-}" \
    "${EXPECTED_FILE:-}" \
    "${EXPECTED_DIR:-}" \
    "${EXPECTED_SUBDIR:-}" \
    "$OUTPUT_TYPE" \
    "$VERIFY_FIELD" \
    "$COMPARE_MODE" \
    "$TAG" \
    "$ACTUAL_EXIT" \
    "$DURATION_MS" \
    "$(basename "$STDOUT_LOG")" \
    "$(basename "$STDERR_LOG")" \
    "$VERIFICATION_PASSED" \
    "$PATTERN_MATCH" \
    "$FIELD_VERIFY" \
    "$FIELD_VALUE" \
    "$MATCH_SCORE" \
    "$VERIFICATION_ERROR" <<'PY'
import json
import pathlib
import sys
from datetime import datetime, timezone

(
    output_path,
    session_id,
    skill_dir,
    script_cmd,
    script_args,
    verify_mode,
    expected_pattern,
    expected_file,
    expected_dir,
    expected_subdir,
    output_type,
    verify_field,
    compare_mode,
    tag,
    exit_code,
    duration_ms,
    stdout_file,
    stderr_file,
    verification_passed,
    pattern_match,
    field_verify,
    field_value,
    match_score,
    verification_error,
) = sys.argv[1:]

payload = {
    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    "sessionId": session_id,
    "skillDir": skill_dir,
    "script": script_cmd,
    "scriptArgs": script_args,
    "verifyMode": verify_mode,
    "expectedPattern": expected_pattern,
    "expectedFile": expected_file,
    "expectedDir": expected_dir,
    "expectedSubdir": expected_subdir,
    "outputType": output_type,
    "verifyField": verify_field,
    "compareMode": compare_mode,
    "tag": tag,
    "exitCode": int(exit_code),
    "durationMs": int(duration_ms),
    "stdoutFile": stdout_file,
    "stderrFile": stderr_file,
    "verification": {
        "passed": verification_passed == "true",
        "patternMatch": pattern_match == "true",
        "fieldVerify": field_verify,
        "fieldValue": field_value,
        "matchScore": match_score,
        "error": verification_error,
    },
}
pathlib.Path(output_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
PY
else
  cat > "$VERIFICATION_FILE" <<VEREOF
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%S")",
  "sessionId": "$(json_escape "$SESSION_ID")",
  "skillDir": "$(json_escape "$SKILL_DIR")",
  "script": "$(json_escape "$SCRIPT_CMD")",
  "scriptArgs": "$(json_escape "$SCRIPT_ARGS")",
  "verifyMode": "$(json_escape "$VERIFY_MODE")",
  "expectedPattern": "$(json_escape "${EXPECTED_PATTERN:-}")",
  "expectedFile": "$(json_escape "${EXPECTED_FILE:-}")",
  "expectedDir": "$(json_escape "${EXPECTED_DIR:-}")",
  "expectedSubdir": "$(json_escape "${EXPECTED_SUBDIR:-}")",
  "outputType": "$(json_escape "$OUTPUT_TYPE")",
  "verifyField": "$(json_escape "$VERIFY_FIELD")",
  "compareMode": "$(json_escape "$COMPARE_MODE")",
  "tag": "$(json_escape "$TAG")",
  "exitCode": $ACTUAL_EXIT,
  "durationMs": $DURATION_MS,
  "stdoutFile": "$(json_escape "$(basename "$STDOUT_LOG")")",
  "stderrFile": "$(json_escape "$(basename "$STDERR_LOG")")",
  "verification": {
    "passed": $VERIFICATION_PASSED,
    "patternMatch": $PATTERN_MATCH,
    "fieldVerify": "$(json_escape "$FIELD_VERIFY")",
    "fieldValue": "$(json_escape "$FIELD_VALUE")",
    "matchScore": "$(json_escape "$MATCH_SCORE")",
    "error": "$(json_escape "$VERIFICATION_ERROR")"
  }
}
VEREOF
fi

# --- Update exit-codes.json ---
EXISTING=$(cat "$LOGS_DIR/exit-codes.json" 2>/dev/null || echo "[]")
EXISTING="${EXISTING%]}"
NEW_ENTRY=$(cat <<ENTRYEOF
{"seq": $SEQ, "tag": "$TAG", "command": $(echo "$FULL_CMD" | head -c 500 | python -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo "\"(command logged)\""), "exitCode": $ACTUAL_EXIT, "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%S")", "durationMs": $DURATION_MS, "type": "output-verification", "verification": "logs/$(basename "$VERIFICATION_FILE")"}
ENTRYEOF
)

if [[ "$EXISTING" == "[" || -z "$EXISTING" ]]; then
  echo "[${NEW_ENTRY}]" > "$LOGS_DIR/exit-codes.json"
else
  echo "${EXISTING},${NEW_ENTRY}]" > "$LOGS_DIR/exit-codes.json"
fi

# --- Output results ---
echo "VERIFICATION_PASSED=$VERIFICATION_PASSED"
echo "EXIT_CODE=$ACTUAL_EXIT"
echo "VERIFY_MODE=$VERIFY_MODE"
echo "PATTERN_MATCH=$PATTERN_MATCH"
echo "FIELD_VERIFY=$FIELD_VERIFY"
echo "MATCH_SCORE=$MATCH_SCORE"
if [[ -n "$FIELD_VALUE" ]]; then
  echo "FIELD_VALUE=$FIELD_VALUE"
fi
echo "DURATION_MS=$DURATION_MS"
echo "VERIFICATION_FILE=logs/$(basename "$VERIFICATION_FILE")"
echo "STDOUT_FILE=logs/$(basename "$STDOUT_LOG")"
echo "STDERR_FILE=logs/$(basename "$STDERR_LOG")"

# --- Print summary ---
echo ""
echo "=== Output Verification Summary ==="
echo "Script: $SCRIPT_CMD $SCRIPT_ARGS"
echo "Verification Mode: $VERIFY_MODE"
echo "Match Score: ${MATCH_SCORE}%"
echo "Verification: $([ "$VERIFICATION_PASSED" == "true" ] && echo '✅ PASSED' || echo '❌ FAILED')"
if [[ -n "$VERIFICATION_ERROR" ]]; then
  echo "Error: $VERIFICATION_ERROR"
fi
echo ""

# --- Show actual output (first 20 lines) ---
if [[ -n "$ACTUAL_OUTPUT" ]]; then
  echo "=== Actual Output (first 20 lines) ==="
  echo "$ACTUAL_OUTPUT" | head -20
  echo "..."
fi

# Exit with appropriate code
[[ "$VERIFICATION_PASSED" == "true" ]] || exit 1
