#!/usr/bin/env bash
# sandbox-skill-invoke.sh — Nexus Testing Skill Invocation Simulator
# POSIX-compatible, Windows Git Bash compatible
# Installs a skill into sandbox, simulates user messages, captures invocation traces.

set -euo pipefail

# --- Defaults ---
SESSION_ID=""
SKILL_PATH=""
MESSAGE=""
CHANNEL="telegram"
MODE="trace"  # live | dry-run | trace
TIMEOUT_SECONDS=60
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SANDBOX_ROOT="$PROJECT_DIR/.nexus-sandbox"

# --- Parse Args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --session-id)
      SESSION_ID="$2"
      shift 2
      ;;
    --skill-path)
      SKILL_PATH="$2"
      shift 2
      ;;
    --message)
      MESSAGE="$2"
      shift 2
      ;;
    --channel)
      CHANNEL="$2"
      shift 2
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --timeout)
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --sandbox-root)
      SANDBOX_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: sandbox-skill-invoke.sh --session-id ID --skill-path PATH --message MSG [options]"
      echo ""
      echo "Simulates skill invocation inside a sandbox session."
      echo ""
      echo "Options:"
      echo "  --session-id ID       Session ID (required)"
      echo "  --skill-path PATH     Path to skill directory or SKILL.md (required)"
      echo "  --message MSG         User message to send (required)"
      echo "  --channel CHAN        Channel: telegram|feishu|qq|wechat (default: telegram)"
      echo "  --mode MODE           Mode: live|dry-run|trace (default: trace)"
      echo "  --timeout SECS        Timeout in seconds (default: 60)"
      echo "  --sandbox-root PATH   Sandbox root path"
      echo ""
      echo "Modes:"
      echo "  live     - Invoke skill via OpenClaw CLI (requires openclaw in PATH)"
      echo "  trace    - Parse SKILL.md, trace decision tree, log tool calls without executing"
      echo "  dry-run  - Install skill, validate structure, but don't invoke"
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
if [[ -z "$SKILL_PATH" ]]; then
  echo "ERROR: --skill-path is required" >&2
  exit 1
fi
if [[ -z "$MESSAGE" && "$MODE" != "dry-run" ]]; then
  echo "ERROR: --message is required for mode=$MODE" >&2
  exit 1
fi

# --- Validate Session ID ---
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
SKILL_INSTALL_DIR="$WORKSPACE_DIR/skills"
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")

# --- Create skill installation directory ---
mkdir -p "$SKILL_INSTALL_DIR"
mkdir -p "$WORKSPACE_DIR/outputs"

# --- Resolve SKILL.md path ---
SKILL_MD=""
if [[ -f "$SKILL_PATH" ]]; then
  # Direct file path
  SKILL_MD="$SKILL_PATH"
  SKILL_DIR="$(dirname "$SKILL_PATH")"
elif [[ -d "$SKILL_PATH" ]]; then
  # Directory path, look for SKILL.md
  if [[ -f "$SKILL_PATH/SKILL.md" ]]; then
    SKILL_MD="$SKILL_PATH/SKILL.md"
    SKILL_DIR="$SKILL_PATH"
  else
    echo "ERROR: No SKILL.md found in $SKILL_PATH" >&2
    exit 1
  fi
else
  echo "ERROR: Skill path does not exist: $SKILL_PATH" >&2
  exit 1
fi

# --- Extract skill name from YAML frontmatter ---
SKILL_NAME=""
if command -v python &>/dev/null || command -v python3 &>/dev/null; then
  PYTHON_CMD="python"
  command -v python &>/dev/null || PYTHON_CMD="python3"
  SKILL_NAME=$($PYTHON_CMD -c "
import re, sys
content = open(sys.argv[1], 'r', encoding='utf-8').read()
m = re.search(r'^name:\s*(.+)$', content, re.MULTILINE)
print(m.group(1).strip() if m else 'unknown-skill')
" "$SKILL_MD" 2>/dev/null || echo "unknown-skill")
else
  # Fallback: grep for name field
  SKILL_NAME=$(grep -m1 '^name:' "$SKILL_MD" 2>/dev/null | sed 's/^name:\s*//' | tr -d '\r' || echo "unknown-skill")
fi

SKILL_TARGET="$SKILL_INSTALL_DIR/$SKILL_NAME"

# --- Install skill into sandbox ---
echo "=== Skill Installation ==="
echo "SKILL_NAME=$SKILL_NAME"
echo "SKILL_SOURCE=$SKILL_DIR"
echo "SKILL_TARGET=$SKILL_TARGET"

# Copy skill files to sandbox
if [[ -d "$SKILL_DIR" ]]; then
  mkdir -p "$SKILL_TARGET"
  cp -r "$SKILL_DIR"/* "$SKILL_TARGET"/ 2>/dev/null || cp "$SKILL_MD" "$SKILL_TARGET/"
  echo "INSTALL_STATUS=success"
else
  cp "$SKILL_MD" "$SKILL_TARGET/"
  echo "INSTALL_STATUS=partial"
fi

# --- Verify installation ---
if [[ -f "$SKILL_TARGET/SKILL.md" ]] || [[ -f "$SKILL_TARGET/$(basename "$SKILL_MD")" ]]; then
  echo "INSTALL_VERIFIED=true"
else
  echo "INSTALL_VERIFIED=false"
  echo "ERROR: Skill installation verification failed" >&2
  exit 1
fi

# --- Extract trigger conditions and tools from SKILL.md ---
TRACE_FILE="$LOGS_DIR/${TIMESTAMP}-invoke-trace.json"
OUTPUT_FILE="$WORKSPACE_DIR/outputs/${TIMESTAMP}-response.md"
CHANNEL_RENDER_FILE="$WORKSPACE_DIR/outputs/${TIMESTAMP}-channel-${CHANNEL}.md"

echo "=== Skill Analysis ==="

# Extract tools/allowed-tools from SKILL.md
TOOLS_DECLARED=""
if command -v python &>/dev/null || command -v python3 &>/dev/null; then
  PYTHON_CMD="python"
  command -v python &>/dev/null || PYTHON_CMD="python3"
  TOOLS_DECLARED=$($PYTHON_CMD -c "
import re, sys, json
content = open(sys.argv[1], 'r', encoding='utf-8').read()
# Extract allowed-tools
tools = []
in_tools = False
for line in content.split('\n'):
    if re.match(r'^allowed[_-]tools:', line, re.IGNORECASE):
        in_tools = True
        continue
    if in_tools:
        m = re.match(r'^\s*-\s*(.+)', line)
        if m:
            tools.append(m.group(1).strip())
        elif line.strip() and not line.startswith(' '):
            in_tools = False
# Also extract from tool references in the body
for m in re.finditer(r'tools?:\s*\[([^\]]+)\]', content):
    for t in m.group(1).split(','):
        t = t.strip().strip('\"').strip(\"'\")
        if t and t not in tools:
            tools.append(t)
print(','.join(tools) if tools else 'none')
" "$SKILL_MD" 2>/dev/null || echo "none")
fi

echo "TOOLS_DECLARED=$TOOLS_DECLARED"

# --- Mode-specific execution ---
case "$MODE" in
  dry-run)
    echo "=== Dry Run Mode ==="
    echo "Skill installed and verified. No invocation performed."

    # Write trace file
    cat > "$TRACE_FILE" <<TRACEEOF
{
  "mode": "dry-run",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%S")",
  "skillName": "$SKILL_NAME",
  "skillPath": "$SKILL_TARGET",
  "toolsDeclared": "$(echo "$TOOLS_DECLARED" | tr ',' '","')",
  "message": null,
  "channel": "$CHANNEL",
  "triggerMatched": null,
  "toolsCalled": [],
  "output": null,
  "status": "dry-run-complete"
}
TRACEEOF

    echo "INVOKE_STATUS=dry-run-complete"
    echo "TRIGGER_MATCHED=n/a"
    echo "TOOLS_CALLED=none"
    echo "TOOL_TRACE_FILE=$TRACE_FILE"
    ;;

  trace)
    echo "=== Trace Mode ==="
    echo "MESSAGE=$MESSAGE"
    echo "CHANNEL=$CHANNEL"

    # Trace mode: analyze SKILL.md to determine what WOULD happen
    # Parse trigger conditions, match against message, trace decision tree

    TRIGGER_MATCHED="false"
    TOOLS_WOULD_CALL=""
    TRACE_STEPS="[]"

    if command -v python &>/dev/null || command -v python3 &>/dev/null; then
      PYTHON_CMD="python"
      command -v python &>/dev/null || PYTHON_CMD="python3"

      TRACE_RESULT=$($PYTHON_CMD -c "
import re, sys, json

skill_md = open(sys.argv[1], 'r', encoding='utf-8').read()
message = sys.argv[2]
channel = sys.argv[3]

result = {
    'mode': 'trace',
    'timestamp': '$(date -u +"%Y-%m-%dT%H:%M:%S")',
    'skillName': '$SKILL_NAME',
    'skillPath': '$SKILL_TARGET',
    'message': message,
    'channel': channel,
    'triggerMatched': False,
    'triggerAnalysis': '',
    'toolsCalled': [],
    'traceSteps': [],
    'expectedOutput': '',
    'channelAdaptation': '',
    'status': 'trace-complete'
}

# Step 1: Analyze trigger conditions
triggers = []
trigger_section = False
for line in skill_md.split('\n'):
    lower = line.lower()
    if any(kw in lower for kw in ['trigger', '触发', 'activation', '激活']):
        trigger_section = True
    if trigger_section:
        if line.strip().startswith(('-', '*', '•')):
            triggers.append(line.strip().lstrip('-*• '))
        elif line.strip() == '' and triggers:
            trigger_section = False

result['triggerAnalysis'] = f'Found {len(triggers)} trigger conditions: {triggers[:5]}'

# Step 2: Simple keyword matching for trigger detection
msg_lower = message.lower()
for t in triggers:
    t_words = re.findall(r'[\w\u4e00-\u9fff]+', t.lower())
    if any(w in msg_lower for w in t_words if len(w) > 1):
        result['triggerMatched'] = True
        result['traceSteps'].append({
            'step': 1,
            'action': 'trigger_match',
            'detail': f'Message matched trigger: {t}',
            'tools': []
        })
        break

if not result['triggerMatched']:
    # Try broader matching
    skill_keywords = re.findall(r'[\w\u4e00-\u9fff]{2,}', skill_md[:2000].lower())
    msg_keywords = re.findall(r'[\w\u4e00-\u9fff]{2,}', msg_lower)
    overlap = set(msg_keywords) & set(skill_keywords)
    if len(overlap) >= 2:
        result['triggerMatched'] = True
        result['traceSteps'].append({
            'step': 1,
            'action': 'trigger_match_fuzzy',
            'detail': f'Fuzzy match via keywords: {list(overlap)[:5]}',
            'tools': []
        })

# Step 3: Trace tool calls from SKILL.md logic
tools_str = '$TOOLS_DECLARED'
tools = [t.strip() for t in tools_str.split(',') if t.strip() != 'none']
for i, tool in enumerate(tools):
    result['toolsCalled'].append(tool)
    result['traceSteps'].append({
        'step': i + 2,
        'action': 'tool_call_trace',
        'detail': f'Would call tool: {tool}',
        'tools': [tool]
    })

# Step 4: Channel adaptation analysis
channel_notes = {
    'telegram': 'Markdown rendering supported, max 4096 chars per message',
    'feishu': 'Rich text supported, card messages available',
    'qq': 'Limited formatting, plain text fallback',
    'wechat': 'Plain text only, file sent separately'
}
result['channelAdaptation'] = channel_notes.get(channel, 'Unknown channel')

print(json.dumps(result, ensure_ascii=False, indent=2))
" "$SKILL_MD" "$MESSAGE" "$CHANNEL" 2>/dev/null || echo '{"status": "trace-error", "error": "Python trace failed"}')

      echo "$TRACE_RESULT" > "$TRACE_FILE"

      # Extract key values from trace
      TRIGGER_MATCHED=$(echo "$TRACE_RESULT" | grep -o '"triggerMatched": [a-z]*' | head -1 | sed 's/.*: //')
      TOOLS_WOULD_CALL=$(echo "$TRACE_RESULT" | grep -o '"toolsCalled": \[[^]]*\]' | head -1 || echo "[]")
    else
      # No Python available, minimal trace
      cat > "$TRACE_FILE" <<TRACEEOF
{
  "mode": "trace",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%S")",
  "skillName": "$SKILL_NAME",
  "message": "$MESSAGE",
  "channel": "$CHANNEL",
  "triggerMatched": "unknown",
  "toolsDeclared": "$TOOLS_DECLARED",
  "toolsCalled": [],
  "traceSteps": [{"step": 1, "action": "no_python", "detail": "Python not available for trace analysis"}],
  "status": "trace-limited"
}
TRACEEOF
      TRIGGER_MATCHED="unknown"
    fi

    # Write expected output based on trace
    cat > "$OUTPUT_FILE" <<OUTEOF
# Skill Trace Output

## Trigger Analysis
- Message: $MESSAGE
- Trigger Matched: $TRIGGER_MATCHED
- Tools Declared: $TOOLS_DECLARED

## Trace Result
See: $TRACE_FILE

## Note
This is a trace-mode output. The skill was not actually invoked.
Tools were identified but not executed. Use 'live' mode for actual invocation.
OUTEOF

    # Write channel-specific render
    cat > "$CHANNEL_RENDER_FILE" <<CHANEOF
# Channel Render: $CHANNEL

## Message Sent
$MESSAGE

## Expected Response Format
Channel: $CHANNEL
$(case "$CHANNEL" in
  telegram) echo "Format: Markdown, max 4096 chars" ;;
  feishu) echo "Format: Rich text / Card message" ;;
  qq) echo "Format: Plain text fallback" ;;
  wechat) echo "Format: Plain text, file separate" ;;
esac)

## Trace Reference
See: $TRACE_FILE
CHANEOF

    echo "INVOKE_STATUS=trace-complete"
    echo "TRIGGER_MATCHED=$TRIGGER_MATCHED"
    echo "TOOLS_CALLED=$TOOLS_DECLARED"
    echo "TOOL_TRACE_FILE=$TRACE_FILE"
    echo "OUTPUT_FILE=$OUTPUT_FILE"
    echo "CHANNEL_RENDER_FILE=$CHANNEL_RENDER_FILE"
    ;;

  live)
    echo "=== Live Mode ==="
    echo "MESSAGE=$MESSAGE"
    echo "CHANNEL=$CHANNEL"

    # Check if OpenClaw CLI is available
    OPENCLAW_CMD=""
    if command -v openclaw &>/dev/null; then
      OPENCLAW_CMD="openclaw"
    elif command -v claw &>/dev/null; then
      OPENCLAW_CMD="claw"
    fi

    if [[ -z "$OPENCLAW_CMD" ]]; then
      echo "WARNING: OpenClaw CLI not found. Falling back to trace mode."
      echo "INVOKE_STATUS=fallback-to-trace"
      echo "FALLBACK_REASON=openclaw_cli_not_found"
      # Re-run in trace mode
      exec "$0" --session-id "$SESSION_ID" --skill-path "$SKILL_PATH" \
        --message "$MESSAGE" --channel "$CHANNEL" --mode trace \
        --timeout "$TIMEOUT_SECONDS" --sandbox-root "$SANDBOX_ROOT"
      exit 0
    fi

    # Live invocation via OpenClaw CLI
    INVOKE_OUTPUT="$LOGS_DIR/${TIMESTAMP}-invoke-live.stdout.log"
    INVOKE_ERROR="$LOGS_DIR/${TIMESTAMP}-invoke-live.stderr.log"

    START_MS=$(date +%s%3N 2>/dev/null || echo "0")

    # Attempt to invoke the skill
    TIMEOUT_CMD=""
    if command -v timeout &>/dev/null; then
      TIMEOUT_CMD="timeout ${TIMEOUT_SECONDS}"
    elif command -v gtimeout &>/dev/null; then
      TIMEOUT_CMD="gtimeout ${TIMEOUT_SECONDS}"
    fi

    ACTUAL_EXIT=0
    if [[ -n "$TIMEOUT_CMD" ]]; then
      $TIMEOUT_CMD $OPENCLAW_CMD invoke \
        --skill "$SKILL_TARGET" \
        --message "$MESSAGE" \
        --channel "$CHANNEL" \
        > "$INVOKE_OUTPUT" 2> "$INVOKE_ERROR" || ACTUAL_EXIT=$?
    else
      $OPENCLAW_CMD invoke \
        --skill "$SKILL_TARGET" \
        --message "$MESSAGE" \
        --channel "$CHANNEL" \
        > "$INVOKE_OUTPUT" 2> "$INVOKE_ERROR" || ACTUAL_EXIT=$?
    fi

    END_MS=$(date +%s%3N 2>/dev/null || echo "0")
    DURATION_MS=$((END_MS - START_MS))
    if [[ $DURATION_MS -lt 0 ]]; then DURATION_MS=0; fi

    # Copy output to response file
    cp "$INVOKE_OUTPUT" "$OUTPUT_FILE" 2>/dev/null || touch "$OUTPUT_FILE"

    # Write trace file for live mode
    cat > "$TRACE_FILE" <<TRACEEOF
{
  "mode": "live",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%S")",
  "skillName": "$SKILL_NAME",
  "skillPath": "$SKILL_TARGET",
  "message": "$(echo "$MESSAGE" | head -c 500)",
  "channel": "$CHANNEL",
  "exitCode": $ACTUAL_EXIT,
  "durationMs": $DURATION_MS,
  "stdoutFile": "$INVOKE_OUTPUT",
  "stderrFile": "$INVOKE_ERROR",
  "status": "$([ $ACTUAL_EXIT -eq 0 ] && echo 'success' || echo 'failure')"
}
TRACEEOF

    echo "INVOKE_STATUS=$([ $ACTUAL_EXIT -eq 0 ] && echo 'success' || echo 'failure')"
    echo "EXIT_CODE=$ACTUAL_EXIT"
    echo "DURATION_MS=$DURATION_MS"
    echo "TOOL_TRACE_FILE=$TRACE_FILE"
    echo "OUTPUT_FILE=$OUTPUT_FILE"
    echo "STDOUT_FILE=$INVOKE_OUTPUT"
    echo "STDERR_FILE=$INVOKE_ERROR"
    ;;

  *)
    echo "ERROR: Unknown mode: $MODE. Use: live|dry-run|trace" >&2
    exit 1
    ;;
esac
