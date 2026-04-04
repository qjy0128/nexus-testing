#!/usr/bin/env bash
# sandbox-mock-service.sh — Nexus Testing External Service Mock
# POSIX-compatible, Windows Git Bash compatible
# Creates mock response files for skills that depend on external APIs.
# Does NOT start a real server — writes mock responses to files that
# the testing agent can reference when simulating skill invocations.

set -euo pipefail

# --- Defaults ---
SESSION_ID=""
MOCK_CONFIG=""
ACTION="start"  # start | stop | status
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
    --mock-config)
      MOCK_CONFIG="$2"
      shift 2
      ;;
    --action)
      ACTION="$2"
      shift 2
      ;;
    --sandbox-root)
      SANDBOX_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: sandbox-mock-service.sh --session-id ID --mock-config FILE --action start|stop|status"
      echo ""
      echo "Creates mock response files for external service simulation."
      echo ""
      echo "Options:"
      echo "  --session-id ID         Session ID (required)"
      echo "  --mock-config FILE      JSON mock config file (required for start)"
      echo "  --action ACTION         Action: start|stop|status (default: start)"
      echo ""
      echo "Mock config format (JSON):"
      echo '  {'
      echo '    "services": ['
      echo '      {'
      echo '        "name": "weather-api",'
      echo '        "scenarios": ['
      echo '          {"name": "success", "status": 200, "body": {"temp": 25}},'
      echo '          {"name": "timeout", "status": 0, "error": "connection_timeout"},'
      echo '          {"name": "error", "status": 500, "body": {"error": "internal"}}'
      echo '        ]'
      echo '      }'
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

# --- Validate ---
if [[ -z "$SESSION_ID" ]]; then
  echo "ERROR: --session-id is required" >&2
  exit 1
fi

SESSION_DIR="$SANDBOX_ROOT/$SESSION_ID"
if [[ ! -d "$SESSION_DIR" ]]; then
  echo "ERROR: Session does not exist: $SESSION_DIR" >&2
  exit 1
fi

MOCK_DIR="$SESSION_DIR/workspace/mocks"
MOCK_REGISTRY="$MOCK_DIR/registry.json"

case "$ACTION" in
  start)
    if [[ -z "$MOCK_CONFIG" ]]; then
      echo "ERROR: --mock-config is required for start action" >&2
      exit 1
    fi

    # Resolve config path
    if [[ ! -f "$MOCK_CONFIG" ]]; then
      if [[ -f "$SESSION_DIR/workspace/$MOCK_CONFIG" ]]; then
        MOCK_CONFIG="$SESSION_DIR/workspace/$MOCK_CONFIG"
      else
        echo "ERROR: Mock config not found: $MOCK_CONFIG" >&2
        exit 1
      fi
    fi

    # Create mock directory
    mkdir -p "$MOCK_DIR"

    echo "=== Mock Service Setup ==="

    # Check Python availability
    PYTHON_CMD=""
    if command -v python &>/dev/null; then
      PYTHON_CMD="python"
    elif command -v python3 &>/dev/null; then
      PYTHON_CMD="python3"
    fi

    if [[ -n "$PYTHON_CMD" ]]; then
      $PYTHON_CMD -c "
import json, sys, os

config_file = sys.argv[1]
mock_dir = sys.argv[2]

with open(config_file, 'r', encoding='utf-8') as f:
    config = json.load(f)

registry = {
    'status': 'active',
    'services': [],
    'createdAt': '$(date -u +"%Y-%m-%dT%H:%M:%S")'
}

services = config.get('services', [])
for svc in services:
    name = svc.get('name', 'unknown')
    svc_dir = os.path.join(mock_dir, name)
    os.makedirs(svc_dir, exist_ok=True)

    scenarios = svc.get('scenarios', [])
    svc_info = {
        'name': name,
        'path': svc_dir,
        'scenarios': []
    }

    for scenario in scenarios:
        sc_name = scenario.get('name', 'default')
        sc_file = os.path.join(svc_dir, f'{sc_name}.json')

        with open(sc_file, 'w', encoding='utf-8') as sf:
            json.dump(scenario, sf, ensure_ascii=False, indent=2)

        svc_info['scenarios'].append({
            'name': sc_name,
            'file': sc_file,
            'status': scenario.get('status', 200),
            'hasError': 'error' in scenario
        })

        print(f'  Created: {name}/{sc_name}.json (status={scenario.get(\"status\", 200)})')

    registry['services'].append(svc_info)

# Write registry
registry_file = os.path.join(mock_dir, 'registry.json')
with open(registry_file, 'w', encoding='utf-8') as rf:
    json.dump(registry, rf, ensure_ascii=False, indent=2)

print(f'MOCK_STATUS=active')
print(f'SERVICES_COUNT={len(services)}')
print(f'MOCK_DIR={mock_dir}')
print(f'REGISTRY_FILE={registry_file}')
" "$MOCK_CONFIG" "$MOCK_DIR"
    else
      # Fallback: simple file copy without Python
      echo "WARNING: Python not available. Creating minimal mock structure."
      cp "$MOCK_CONFIG" "$MOCK_DIR/config.json"
      echo '{"status": "active", "services": [], "note": "minimal-no-python"}' > "$MOCK_REGISTRY"
      echo "MOCK_STATUS=active-minimal"
      echo "MOCK_DIR=$MOCK_DIR"
    fi
    ;;

  stop)
    echo "=== Mock Service Teardown ==="
    if [[ -d "$MOCK_DIR" ]]; then
      # Update registry status
      if [[ -f "$MOCK_REGISTRY" ]]; then
        if command -v python &>/dev/null || command -v python3 &>/dev/null; then
          PYTHON_CMD="python"
          command -v python &>/dev/null || PYTHON_CMD="python3"
          $PYTHON_CMD -c "
import json, sys
reg_file = sys.argv[1]
with open(reg_file, 'r', encoding='utf-8') as f:
    reg = json.load(f)
reg['status'] = 'stopped'
reg['stoppedAt'] = '$(date -u +"%Y-%m-%dT%H:%M:%S")'
with open(reg_file, 'w', encoding='utf-8') as f:
    json.dump(reg, f, ensure_ascii=False, indent=2)
" "$MOCK_REGISTRY"
        fi
      fi
      echo "MOCK_STATUS=stopped"
      echo "MOCK_DIR=$MOCK_DIR"
    else
      echo "MOCK_STATUS=not-found"
      echo "NOTE=No mock services were active"
    fi
    ;;

  status)
    echo "=== Mock Service Status ==="
    if [[ -f "$MOCK_REGISTRY" ]]; then
      cat "$MOCK_REGISTRY"
      echo ""
      echo "MOCK_STATUS=exists"
    else
      echo "MOCK_STATUS=not-found"
    fi
    ;;

  *)
    echo "ERROR: Unknown action: $ACTION. Use: start|stop|status" >&2
    exit 1
    ;;
esac
