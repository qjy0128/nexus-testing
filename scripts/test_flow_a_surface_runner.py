#!/usr/bin/env python3
"""Smoke test for Flow A surface runner."""

from __future__ import annotations

import json
import os
import stat
import shutil
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
                "    'notes': 'verified extension hook registration',",
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
        if find_runnable_bash():
            assert_equal(kind_status.get("skill"), "passed", "skill surface status")
        else:
            assert_equal(kind_status.get("skill"), "incomplete", "skill surface fallback status")
            assert_contains(skill_results, "runnable bash is unavailable", "skill fallback note")

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
        print("  [PASS] test_surface_runner")
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
    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
