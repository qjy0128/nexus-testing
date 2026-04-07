#!/usr/bin/env python3
"""Behavior smoke tests for Flow A live-mode telemetry protocol."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from test_helpers import (
    assert_contains,
    assert_equal,
    create_session,
    parse_kv_output,
    write_text,
    read_text,
)

ROOT = Path(__file__).resolve().parents[1]
INVOKE_SCRIPT = ROOT / "scripts" / "sandbox_skill_invoke.py"


def build_skill(skill_dir: Path) -> Path:
    skill_dir.mkdir(parents=True, exist_ok=True)
    write_text(
        skill_dir / "SKILL.md",
        "\n".join(
            [
                "---",
                "name: Flow A Live Telemetry Skill",
                "---",
                "",
                "# Flow A Live Telemetry Skill",
                "",
                "allowed_tools:",
                "  - runtime_search",
                "",
                "## Description",
                "Test-only skill for OpenClaw runtime telemetry smoke tests.",
                "",
                "## Usage",
                "- Used only by scripts/test_flow_a_live_telemetry.py.",
                "",
                "## Examples",
                "- Input: protocol-pass",
                "  Output: structured runtime telemetry",
                "",
            ]
        )
        + "\n",
    )
    return skill_dir


def build_mock_openclaw(bin_dir: Path, outside_evidence: Path) -> Path:
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
                "channel = ''",
                "skill = ''",
                "for index, item in enumerate(args):",
                "    if item == '--message' and index + 1 < len(args):",
                "        message = args[index + 1]",
                "    elif item == '--channel' and index + 1 < len(args):",
                "        channel = args[index + 1]",
                "    elif item == '--skill' and index + 1 < len(args):",
                "        skill = args[index + 1]",
                "",
                "output_file = Path(os.environ['NEXUS_OUTPUT_FILE'])",
                "result_file = Path(os.environ['NEXUS_RESULT_JSON_FILE'])",
                "artifacts_dir = Path(os.environ['NEXUS_ARTIFACTS_DIR'])",
                "outside_evidence = os.environ.get('MOCK_LIVE_OUTSIDE_EVIDENCE', '')",
                "protocol_version = os.environ.get('NEXUS_TELEMETRY_PROTOCOL_VERSION', '')",
                "protocol_source = os.environ.get('NEXUS_TELEMETRY_SOURCE', '')",
                "artifacts_dir.mkdir(parents=True, exist_ok=True)",
                "",
                "if 'no-protocol' in message:",
                "    output_file.write_text('live without telemetry\\n', encoding='utf-8')",
                "    print('live without telemetry')",
                "    raise SystemExit(0)",
                "",
                "proof_file = artifacts_dir / 'live-delivery-proof.txt'",
                "proof_file.write_text('delivered\\n', encoding='utf-8')",
                "delivery_evidence = [outside_evidence] if 'bad-evidence' in message else [str(proof_file)]",
                "payload = {",
                "    'telemetryProtocolVersion': protocol_version,",
                "    'telemetrySource': protocol_source,",
                "    'triggerMatched': True,",
                "    'toolsCalled': ['runtime_search'],",
                "    'contextReferences': [1] if 'context-pass' in message else [],",
                "    'assistantMessage': f'OpenClaw handled: {message}',",
                "    'deliveryStatus': 'delivered',",
                "    'deliveryReceipts': ['runtime-receipt-001'],",
                "    'deliveryEvidence': delivery_evidence,",
                "    'notes': [f'channel={channel}', f'skill={skill}'],",
                "}",
                "output_file.write_text(payload['assistantMessage'] + '\\n', encoding='utf-8')",
                "result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')",
                "print(json.dumps(payload, ensure_ascii=False))",
                "",
            ]
        ),
    )

    if os.name == "nt":
        wrapper = bin_dir / "openclaw.cmd"
        write_text(
            wrapper,
            "@echo off\r\n"
            f"\"{sys.executable}\" \"{driver}\" %*\r\n",
        )
    else:
        wrapper = bin_dir / "openclaw"
        write_text(
            wrapper,
            "#!/usr/bin/env bash\n"
            f"\"{sys.executable}\" \"{driver}\" \"$@\"\n",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    outside_evidence.write_text("outside-live-proof\n", encoding="utf-8")
    return wrapper


def run_process(args: list[str], env: dict[str, str]) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    proc = subprocess.run(
        args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return proc, parse_kv_output(proc.stdout)


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="nexus-flow-a-live-"))
    try:
        sandbox_root = temp_root / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        skill_dir = build_skill(temp_root / "live-skill")
        outside_evidence = temp_root / "outside-live-proof.txt"
        mock_cli = build_mock_openclaw(temp_root / "mock-bin", outside_evidence)

        env = os.environ.copy()
        env["PATH"] = str(mock_cli.parent) + os.pathsep + env.get("PATH", "")
        env["MOCK_LIVE_OUTSIDE_EVIDENCE"] = str(outside_evidence)

        create_session(sandbox_root, "flowa-live-no-protocol")
        no_protocol_proc, no_protocol = run_process(
            [
                sys.executable,
                str(INVOKE_SCRIPT),
                "--session-id",
                "flowa-live-no-protocol",
                "--skill-path",
                str(skill_dir),
                "--message",
                "no-protocol please",
                "--channel",
                "telegram",
                "--mode",
                "live",
                "--timeout",
                "30",
                "--strict-real",
                "--sandbox-root",
                str(sandbox_root),
            ],
            env,
        )
        assert_equal(no_protocol_proc.returncode, 2, "live no protocol return code")
        assert_equal(no_protocol.get("INVOKE_STATUS"), "blocked-live-telemetry-missing", "live no protocol status")
        assert_contains(
            no_protocol.get("BLOCKER_REASON", ""),
            "did not emit runtime telemetry protocol",
            "live no protocol blocker",
        )

        create_session(sandbox_root, "flowa-live-protocol-pass")
        protocol_pass_proc, protocol_pass = run_process(
            [
                sys.executable,
                str(INVOKE_SCRIPT),
                "--session-id",
                "flowa-live-protocol-pass",
                "--skill-path",
                str(skill_dir),
                "--message",
                "protocol-pass",
                "--channel",
                "telegram",
                "--mode",
                "live",
                "--timeout",
                "30",
                "--strict-real",
                "--expect-trigger",
                "true",
                "--require-tools",
                "runtime_search",
                "--require-delivery-status",
                "delivered",
                "--require-delivery-evidence",
                "--sandbox-root",
                str(sandbox_root),
            ],
            env,
        )
        assert_equal(protocol_pass_proc.returncode, 0, "live protocol pass return code")
        assert_equal(protocol_pass.get("INVOKE_STATUS"), "success", "live protocol pass status")
        assert_equal(protocol_pass.get("TELEMETRY_PROTOCOL_STATUS"), "passed", "live protocol status")
        assert_equal(protocol_pass.get("TELEMETRY_PROTOCOL_VERSION"), "nexus-live-telemetry/v1", "live protocol version")
        assert_equal(protocol_pass.get("TELEMETRY_SOURCE"), "openclaw-runtime", "live telemetry source")
        assert_equal(protocol_pass.get("TRIGGER_MATCHED"), "true", "live trigger matched")
        assert_equal(
            read_text(Path(protocol_pass["OUTPUT_FILE"])).strip(),
            "OpenClaw handled: protocol-pass",
            "live output file content",
        )

        create_session(sandbox_root, "flowa-live-bad-evidence")
        bad_evidence_proc, bad_evidence = run_process(
            [
                sys.executable,
                str(INVOKE_SCRIPT),
                "--session-id",
                "flowa-live-bad-evidence",
                "--skill-path",
                str(skill_dir),
                "--message",
                "protocol-pass bad-evidence",
                "--channel",
                "telegram",
                "--mode",
                "live",
                "--timeout",
                "30",
                "--strict-real",
                "--require-delivery-status",
                "delivered",
                "--require-delivery-evidence",
                "--sandbox-root",
                str(sandbox_root),
            ],
            env,
        )
        assert_equal(bad_evidence_proc.returncode, 3, "live bad evidence return code")
        assert_equal(bad_evidence.get("INVOKE_STATUS"), "assertion-failed", "live bad evidence status")
        assert_contains(
            bad_evidence.get("INVALID_DELIVERY_EVIDENCE", ""),
            str(outside_evidence),
            "live bad evidence invalid path",
        )

        summary = {
            "live_no_protocol_code": no_protocol_proc.returncode,
            "live_no_protocol_status": no_protocol.get("INVOKE_STATUS"),
            "live_protocol_pass_code": protocol_pass_proc.returncode,
            "live_protocol_pass_status": protocol_pass.get("INVOKE_STATUS"),
            "live_protocol_version": protocol_pass.get("TELEMETRY_PROTOCOL_VERSION"),
            "live_protocol_output": read_text(Path(protocol_pass["OUTPUT_FILE"])).strip(),
            "live_bad_evidence_code": bad_evidence_proc.returncode,
            "live_bad_evidence_status": bad_evidence.get("INVOKE_STATUS"),
            "live_bad_invalid_delivery_evidence": bad_evidence.get("INVALID_DELIVERY_EVIDENCE"),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
