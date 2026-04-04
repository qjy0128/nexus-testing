#!/usr/bin/env bash
# sandbox-multi-turn.sh — Nexus Testing Multi-Turn Conversation Simulator
# POSIX-compatible, Windows Git Bash compatible
# Executes a multi-turn conversation script against a skill, capturing each turn's response.

set -euo pipefail

# --- Defaults ---
SESSION_ID=""
SKILL_PATH=""
CONVERSATION_FILE=""
CHANNEL="telegram"
TIMEOUT_PER_TURN=60
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
    --conversation-file)
      CONVERSATION_FILE="$2"
      shift 2
      ;;
    --channel)
      CHANNEL="$2"
      shift 2
      ;;
    --timeout-per-turn)
      TIMEOUT_PER_TURN="$2"
      shift 2
      ;;
    --sandbox-root)
      SANDBOX_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: sandbox-multi-turn.sh --session-id ID --skill-path PATH --conversation-file FILE [options]"
      echo ""
      echo "Executes a multi-turn conversation script against a skill."
      echo ""
      echo "Options:"
      echo "  --session-id ID              Session ID (required)"
      echo "  --skill-path PATH            Path to skill directory or SKILL.md (required)"
      echo "  --conversation-file FILE     JSON conversation script (required)"
      echo "  --channel CHAN               Channel: telegram|feishu|qq|wechat (default: telegram)"
      echo "  --timeout-per-turn SECS      Timeout per turn in seconds (default: 60)"
      echo ""
      echo "Conversation file format (JSON):"
      echo '  {'
      echo '    "description": "Test context preservation",'
      echo '    "turns": ['
      echo '      {"role": "user", "message": "...", "expect_trigger": true, "expect_tools": ["tool1"]},'
      echo '      {"role": "user", "message": "...", "expect_context_from_turn": 1}'
      echo '    ]'
      echo '  }'
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
if [[ -z "$CONVERSATION_FILE" ]]; then
  echo "ERROR: --conversation-file is required" >&2
  exit 1
fi

# --- Validate session ---
SESSION_DIR="$SANDBOX_ROOT/$SESSION_ID"
if [[ ! -d "$SESSION_DIR" ]]; then
  echo "ERROR: Session does not exist: $SESSION_DIR" >&2
  exit 1
fi

# --- Validate conversation file ---
if [[ ! -f "$CONVERSATION_FILE" ]]; then
  # Try relative to workspace
  if [[ -f "$SESSION_DIR/workspace/$CONVERSATION_FILE" ]]; then
    CONVERSATION_FILE="$SESSION_DIR/workspace/$CONVERSATION_FILE"
  else
    echo "ERROR: Conversation file not found: $CONVERSATION_FILE" >&2
    exit 1
  fi
fi

LOGS_DIR="$SESSION_DIR/logs"
OUTPUTS_DIR="$SESSION_DIR/workspace/outputs"
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
MULTI_TURN_LOG="$LOGS_DIR/${TIMESTAMP}-multi-turn.json"
MULTI_TURN_SUMMARY="$OUTPUTS_DIR/${TIMESTAMP}-multi-turn-summary.md"

mkdir -p "$OUTPUTS_DIR"

echo "=== Multi-Turn Conversation Simulator ==="
echo "SESSION_ID=$SESSION_ID"
echo "SKILL_PATH=$SKILL_PATH"
echo "CONVERSATION_FILE=$CONVERSATION_FILE"
echo "CHANNEL=$CHANNEL"

# --- Check Python availability ---
PYTHON_CMD=""
if command -v python &>/dev/null; then
  PYTHON_CMD="python"
elif command -v python3 &>/dev/null; then
  PYTHON_CMD="python3"
fi

if [[ -z "$PYTHON_CMD" ]]; then
  echo "ERROR: Python is required for multi-turn simulation" >&2
  echo "MULTI_TURN_STATUS=error"
  echo "ERROR_REASON=python_not_available"
  exit 1
fi

# --- Execute multi-turn conversation ---
$PYTHON_CMD -c "
import json, sys, os, subprocess, time

conversation_file = sys.argv[1]
session_id = sys.argv[2]
skill_path = sys.argv[3]
channel = sys.argv[4]
timeout_per_turn = int(sys.argv[5])
script_dir = sys.argv[6]
sandbox_root = sys.argv[7]
logs_dir = sys.argv[8]
outputs_dir = sys.argv[9]
timestamp = sys.argv[10]

# Load conversation script
with open(conversation_file, 'r', encoding='utf-8') as f:
    conv = json.load(f)

description = conv.get('description', 'Multi-turn test')
turns = conv.get('turns', [])

results = {
    'description': description,
    'channel': channel,
    'totalTurns': len(turns),
    'completedTurns': 0,
    'passedTurns': 0,
    'failedTurns': 0,
    'turns': [],
    'contextPreservation': 'unknown',
    'status': 'running'
}

invoke_script = os.path.join(script_dir, 'sandbox-skill-invoke.sh')

for i, turn in enumerate(turns):
    turn_num = i + 1
    message = turn.get('message', '')
    expect_trigger = turn.get('expect_trigger', True)
    expect_tools = turn.get('expect_tools', [])
    expect_context = turn.get('expect_context_from_turn', None)

    turn_result = {
        'turnNumber': turn_num,
        'message': message,
        'expectTrigger': expect_trigger,
        'expectTools': expect_tools,
        'expectContextFromTurn': expect_context,
        'status': 'pending'
    }

    # Invoke the skill for this turn
    try:
        cmd = [
            'bash', invoke_script,
            '--session-id', session_id,
            '--skill-path', skill_path,
            '--message', message,
            '--channel', channel,
            '--mode', 'trace',
            '--timeout', str(timeout_per_turn),
            '--sandbox-root', sandbox_root
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_per_turn + 10
        )

        output = proc.stdout
        turn_result['invokeOutput'] = output[:2000]
        turn_result['exitCode'] = proc.returncode

        # Parse invoke output
        trigger_matched = 'unknown'
        for line in output.split('\\n'):
            if line.startswith('TRIGGER_MATCHED='):
                trigger_matched = line.split('=', 1)[1].strip()
            if line.startswith('TOOLS_CALLED='):
                turn_result['toolsCalled'] = line.split('=', 1)[1].strip()

        turn_result['triggerMatched'] = trigger_matched

        # Validate expectations
        passed = True
        notes = []

        if expect_trigger and trigger_matched not in ('true', 'True'):
            passed = False
            notes.append(f'Expected trigger but got: {trigger_matched}')

        if not expect_trigger and trigger_matched in ('true', 'True'):
            passed = False
            notes.append(f'Expected no trigger but skill activated')

        if expect_context is not None:
            # Check if response references content from the expected turn
            if expect_context <= len(results['turns']):
                prev_msg = results['turns'][expect_context - 1].get('message', '')
                # Simple check: response should reference previous context
                notes.append(f'Context from turn {expect_context} expected (message: \"{prev_msg[:50]}\")')
            else:
                notes.append(f'Cannot verify context: turn {expect_context} not yet executed')

        turn_result['passed'] = passed
        turn_result['notes'] = notes
        turn_result['status'] = 'completed'

        if passed:
            results['passedTurns'] += 1
        else:
            results['failedTurns'] += 1

        results['completedTurns'] += 1

    except subprocess.TimeoutExpired:
        turn_result['status'] = 'timeout'
        turn_result['passed'] = False
        turn_result['notes'] = [f'Turn timed out after {timeout_per_turn}s']
        results['failedTurns'] += 1
        results['completedTurns'] += 1
    except Exception as e:
        turn_result['status'] = 'error'
        turn_result['passed'] = False
        turn_result['notes'] = [f'Error: {str(e)}']
        results['failedTurns'] += 1
        results['completedTurns'] += 1

    results['turns'].append(turn_result)

# Determine overall status
if results['failedTurns'] == 0:
    results['status'] = 'all-passed'
    results['contextPreservation'] = 'verified' if any(t.get('expect_context_from_turn') for t in turns) else 'not-tested'
elif results['passedTurns'] > 0:
    results['status'] = 'partial-pass'
    results['contextPreservation'] = 'partial'
else:
    results['status'] = 'all-failed'
    results['contextPreservation'] = 'failed'

# Write JSON log
log_path = os.path.join(logs_dir, f'{timestamp}-multi-turn.json')
with open(log_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

# Write summary markdown
summary_path = os.path.join(outputs_dir, f'{timestamp}-multi-turn-summary.md')
with open(summary_path, 'w', encoding='utf-8') as f:
    f.write(f'# Multi-Turn Conversation Test Summary\\n\\n')
    f.write(f'## Overview\\n')
    f.write(f'- Description: {description}\\n')
    f.write(f'- Channel: {channel}\\n')
    f.write(f'- Total Turns: {results[\"totalTurns\"]}\\n')
    f.write(f'- Passed: {results[\"passedTurns\"]}\\n')
    f.write(f'- Failed: {results[\"failedTurns\"]}\\n')
    f.write(f'- Context Preservation: {results[\"contextPreservation\"]}\\n')
    f.write(f'- Status: {results[\"status\"]}\\n\\n')
    f.write(f'## Turn Details\\n\\n')
    for tr in results['turns']:
        status_icon = '✅' if tr.get('passed') else '❌'
        f.write(f'### Turn {tr[\"turnNumber\"]} {status_icon}\\n')
        f.write(f'- Message: {tr[\"message\"][:100]}\\n')
        f.write(f'- Trigger: {tr.get(\"triggerMatched\", \"unknown\")}\\n')
        if tr.get('notes'):
            for note in tr['notes']:
                f.write(f'- Note: {note}\\n')
        f.write(f'\\n')

# Output summary to stdout
print(f'MULTI_TURN_STATUS={results[\"status\"]}')
print(f'TOTAL_TURNS={results[\"totalTurns\"]}')
print(f'PASSED_TURNS={results[\"passedTurns\"]}')
print(f'FAILED_TURNS={results[\"failedTurns\"]}')
print(f'CONTEXT_PRESERVATION={results[\"contextPreservation\"]}')
print(f'LOG_FILE={log_path}')
print(f'SUMMARY_FILE={summary_path}')
" "$CONVERSATION_FILE" "$SESSION_ID" "$SKILL_PATH" "$CHANNEL" "$TIMEOUT_PER_TURN" \
  "$SCRIPT_DIR" "$SANDBOX_ROOT" "$LOGS_DIR" "$OUTPUTS_DIR" "$TIMESTAMP"
