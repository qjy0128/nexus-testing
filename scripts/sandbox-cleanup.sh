#!/usr/bin/env bash
# sandbox-cleanup.sh — Nexus Testing Sandbox Cleanup
# POSIX-compatible, Windows Git Bash compatible
# Safely removes a sandbox session directory.

set -euo pipefail

# --- Defaults ---
SESSION_ID=""
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SANDBOX_ROOT="$PROJECT_DIR/.nexus-sandbox"
FORCE=false
DRY_RUN=false

# --- Parse Args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --session-id)
      SESSION_ID="$2"
      shift 2
      ;;
    --sandbox-root)
      SANDBOX_ROOT="$2"
      shift 2
      ;;
    --force)
      FORCE=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      echo "Usage: sandbox-cleanup.sh --session-id ID [--force] [--dry-run] [--sandbox-root PATH]"
      echo ""
      echo "Safely removes a sandbox session directory."
      echo ""
      echo "Options:"
      echo "  --session-id ID    Session ID to clean up (required)"
      echo "  --force            Skip confirmation"
      echo "  --dry-run          Show what would be deleted without deleting"
      echo "  --sandbox-root     Sandbox root path"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# --- Validate ---
if [[ -z "$SESSION_ID" ]]; then
  echo "ERROR: --session-id is required" >&2
  exit 1
fi

# Security: Validate session ID format (prevent path traversal)
if ! echo "$SESSION_ID" | grep -qE '^[a-zA-Z0-9-]+$'; then
  echo "ERROR: Invalid session-id format. Only alphanumeric and dash allowed." >&2
  exit 1
fi

SESSION_DIR="$SANDBOX_ROOT/$SESSION_ID"

# Verify path doesn't escape sandbox root
REAL_SESSION_DIR="$(cd "$SESSION_DIR" 2>/dev/null && pwd || echo "")"
REAL_SANDBOX_ROOT="$(cd "$SANDBOX_ROOT" 2>/dev/null && pwd || echo "")"

if [[ -n "$REAL_SESSION_DIR" && -n "$REAL_SANDBOX_ROOT" ]]; then
  if [[ "$REAL_SESSION_DIR" != "$REAL_SANDBOX_ROOT"* ]]; then
    echo "ERROR: Session directory resolves outside sandbox root. Path traversal detected." >&2
    exit 1
  fi
fi

# --- Verify session exists ---
if [[ ! -d "$SESSION_DIR" ]]; then
  echo "ERROR: Session directory does not exist: $SESSION_DIR" >&2
  exit 1
fi

# --- Dry Run ---
if [[ "$DRY_RUN" == true ]]; then
  echo "DRY_RUN=true"
  echo "WOULD_DELETE=$SESSION_DIR"
  FILE_COUNT=$(find "$SESSION_DIR" -type f 2>/dev/null | wc -l || echo "0")
  DIR_SIZE=$(du -sh "$SESSION_DIR" 2>/dev/null | cut -f1 || echo "unknown")
  echo "FILE_COUNT=$FILE_COUNT"
  echo "TOTAL_SIZE=$DIR_SIZE"
  exit 0
fi

# --- Show summary before cleanup ---
FILE_COUNT=$(find "$SESSION_DIR" -type f 2>/dev/null | wc -l || echo "0")

if [[ "$FORCE" != true ]]; then
  echo "About to delete sandbox session: $SESSION_ID"
  echo "  Files: $FILE_COUNT"
  echo "  Path: $SESSION_DIR"
  echo ""
  echo "Use --force to skip this confirmation."
  echo "CLEANUP_STATUS=pending_confirmation"
  exit 0
fi

# --- Update META.json status ---
META_FILE="$SESSION_DIR/META.json"
if [[ -f "$META_FILE" ]]; then
  sed -i 's/"status": "active"/"status": "cleaning"/' "$META_FILE" 2>/dev/null || \
    sed -i '' 's/"status": "active"/"status": "cleaning"/' "$META_FILE"
fi

# --- Delete ---
rm -rf "$SESSION_DIR"

# --- Verify Deletion ---
if [[ -d "$SESSION_DIR" ]]; then
  echo "CLEANUP_STATUS=failed"
  echo "ERROR: Directory still exists after deletion: $SESSION_DIR" >&2
  exit 1
fi

echo "CLEANUP_STATUS=success"
echo "DELETED_PATH=$SESSION_DIR"
echo "DELETED_FILES=$FILE_COUNT"
