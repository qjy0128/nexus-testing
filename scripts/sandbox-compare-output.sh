#!/usr/bin/env bash
# sandbox-compare-output.sh — Nexus Testing Expected Output Comparison
# POSIX-compatible, Windows Git Bash compatible
# Compares actual script output against expected output patterns.

set -euo pipefail

# --- Defaults ---
ACTUAL_OUTPUT=""
EXPECTED_FILE=""
MODE="strict"  # strict | pattern | contains
REPORT_FILE=""
TAG=""
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SANDBOX_ROOT="$PROJECT_DIR/.nexus-sandbox"

# --- Parse Args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --actual)
      ACTUAL_OUTPUT="$2"
      shift 2
      ;;
    --expected)
      EXPECTED_FILE="$2"
      shift 2
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --report)
      REPORT_FILE="$2"
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
      echo "Usage: sandbox-compare-output.sh --actual FILE --expected FILE [options]"
      echo ""
      echo "Compares actual script output against expected output."
      echo ""
      echo "Options:"
      echo "  --actual FILE     File containing actual output (required)"
      echo "  --expected FILE   File containing expected output (required)"
      echo "  --mode MODE       Comparison mode: strict|pattern|contains (default: strict)"
      echo "  --report FILE     Write report to FILE (optional)"
      echo "  --tag TAG         Test case tag"
      echo "  --sandbox-root PATH  Sandbox root path"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# --- Validate Required Args ---
if [[ -z "$ACTUAL_OUTPUT" ]]; then
  echo "ERROR: --actual is required" >&2
  exit 1
fi
if [[ -z "$EXPECTED_FILE" ]]; then
  echo "ERROR: --expected is required" >&2
  exit 1
fi

# --- Read actual output ---
if [[ -f "$ACTUAL_OUTPUT" ]]; then
  ACTUAL_CONTENT=$(cat "$ACTUAL_OUTPUT")
else
  # If not a file, treat as literal content
  ACTUAL_CONTENT="$ACTUAL_OUTPUT"
fi

# --- Read expected output ---
if [[ ! -f "$EXPECTED_FILE" ]]; then
  echo "ERROR: Expected file does not exist: $EXPECTED_FILE" >&2
  exit 1
fi
EXPECTED_CONTENT=$(cat "$EXPECTED_FILE")

# --- Initialize comparison ---
COMPARE_PASSED="false"
DIFF_LINES=""
MATCH_SCORE="0"
ISSUE_COUNT="0"

# --- Comparison Logic ---
case "$MODE" in
  strict)
    # Exact match required
    if [[ "$ACTUAL_CONTENT" == "$EXPECTED_CONTENT" ]]; then
      COMPARE_PASSED="true"
      MATCH_SCORE="100"
    else
      COMPARE_PASSED="false"
      # Calculate diff
      if command -v diff &>/dev/null; then
        DIFF_OUTPUT=$(diff -u "$EXPECTED_FILE" <(echo "$ACTUAL_CONTENT") 2>/dev/null || true)
        DIFF_LINES=$(echo "$DIFF_OUTPUT" | head -50)
      fi
      # Calculate similarity score
      if [[ -n "$ACTUAL_CONTENT" ]]; then
        PYTHON_CMD="python"
        command -v python &>/dev/null || PYTHON_CMD="python3"
        MATCH_SCORE=$(
          "$PYTHON_CMD" - "$ACTUAL_OUTPUT" "$EXPECTED_FILE" <<'PY' 2>/dev/null || echo "0"
import difflib
import pathlib
import sys

actual_arg = sys.argv[1]
actual_path = pathlib.Path(actual_arg)
if actual_path.exists():
    actual = actual_path.read_text(encoding="utf-8", errors="replace")
else:
    actual = actual_arg
expected = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8", errors="replace")
ratio = difflib.SequenceMatcher(None, actual, expected).ratio()
print(int(ratio * 100))
PY
        )
      fi
    fi
    ;;

  pattern)
    # Each line of expected file is a regex pattern that must match
    MISSING_PATTERNS=""
    MATCHED_COUNT=0
    TOTAL_COUNT=0

    while IFS= read -r pattern || [[ -n "$pattern" ]]; do
      # Skip empty lines and comments
      [[ -z "$pattern" || "$pattern" =~ ^# ]] && continue

      TOTAL_COUNT=$((TOTAL_COUNT + 1))

      if echo "$ACTUAL_CONTENT" | grep -qE "$pattern"; then
        MATCHED_COUNT=$((MATCHED_COUNT + 1))
      else
        MISSING_PATTERNS="${MISSING_PATTERNS}  - Pattern not found: ${pattern}\n"
      fi
    done < "$EXPECTED_FILE"

    if [[ $TOTAL_COUNT -eq 0 ]]; then
      COMPARE_PASSED="true"
      MATCH_SCORE="100"
    elif [[ $MATCHED_COUNT -eq $TOTAL_COUNT ]]; then
      COMPARE_PASSED="true"
      MATCH_SCORE="100"
    else
      COMPARE_PASSED="false"
      MATCH_SCORE=$((MATCHED_COUNT * 100 / TOTAL_COUNT))
      ISSUE_COUNT=$((TOTAL_COUNT - MATCHED_COUNT))
      DIFF_LINES=$(printf "$MISSING_PATTERNS")
    fi
    ;;

  contains)
    # Expected file contains substrings that must all be present
    MISSING_SUBSTRINGS=""
    MATCHED_COUNT=0
    TOTAL_COUNT=0

    while IFS= read -r substring || [[ -n "$substring" ]]; do
      # Skip empty lines and comments
      [[ -z "$substring" || "$substring" =~ ^# ]] && continue

      TOTAL_COUNT=$((TOTAL_COUNT + 1))

      if echo "$ACTUAL_CONTENT" | grep -qF -- "$substring"; then
        MATCHED_COUNT=$((MATCHED_COUNT + 1))
      else
        MISSING_SUBSTRINGS="${MISSING_SUBSTRINGS}  - Substring not found: ${substring}\n"
      fi
    done < "$EXPECTED_FILE"

    if [[ $TOTAL_COUNT -eq 0 ]]; then
      COMPARE_PASSED="true"
      MATCH_SCORE="100"
    elif [[ $MATCHED_COUNT -eq $TOTAL_COUNT ]]; then
      COMPARE_PASSED="true"
      MATCH_SCORE="100"
    else
      COMPARE_PASSED="false"
      MATCH_SCORE=$((MATCHED_COUNT * 100 / TOTAL_COUNT))
      ISSUE_COUNT=$((TOTAL_COUNT - MATCHED_COUNT))
      DIFF_LINES=$(printf "$MISSING_SUBSTRINGS")
    fi
    ;;

  *)
    echo "ERROR: Unknown mode: $MODE" >&2
    exit 1
    ;;
esac

# --- Generate Report ---
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S")
REPORT_CONTENT="=== OUTPUT COMPARISON REPORT ===
Timestamp: $TIMESTAMP
Mode: $MODE
Tag: ${TAG:-N/A}

RESULT: $([ "$COMPARE_PASSED" == "true" ] && echo 'PASSED' || echo 'FAILED')
Match Score: ${MATCH_SCORE}%

ACTUAL OUTPUT (first 20 lines):
$(echo "$ACTUAL_CONTENT" | head -20)
$([ $(echo "$ACTUAL_CONTENT" | wc -l) -gt 20 ] && echo '...(truncated more lines)')

EXPECTED FILE: $EXPECTED_FILE
"

if [[ "$COMPARE_PASSED" == "false" ]]; then
  REPORT_CONTENT="${REPORT_CONTENT}
ISSUES (${ISSUE_COUNT}):
${DIFF_LINES}
"
fi

# --- Output ---
echo "$REPORT_CONTENT"

# --- Write report file if specified ---
if [[ -n "$REPORT_FILE" ]]; then
  echo "$REPORT_CONTENT" > "$REPORT_FILE"
  echo "Report written to: $REPORT_FILE"
fi

# --- Exit with appropriate code ---
[[ "$COMPARE_PASSED" == "true" ]] || exit 1
