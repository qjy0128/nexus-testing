#!/usr/bin/env python3
"""Behavior smoke tests for Flow A strict shim-live verification."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVOKE_SCRIPT = ROOT / "scripts" / "sandbox_skill_invoke.py"
MULTI_TURN_SCRIPT = ROOT / "scripts" / "sandbox_multi_turn.py"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def parse_kv_output(output: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: expected to find {needle!r} in {text!r}")


def create_session(sandbox_root: Path, session_id: str) -> Path:
    session_dir = sandbox_root / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir)
    for relative in (
        "workspace/fixtures",
        "workspace/outputs",
        "workspace/temp",
        "workspace/state",
        "workspace/artifacts",
        "runtime",
        "logs",
    ):
        (session_dir / relative).mkdir(parents=True, exist_ok=True)
    write_text(session_dir / "logs" / "exit-codes.json", "[]\n")
    write_text(session_dir / "logs" / "file-ops.json", "[]\n")
    write_text(
        session_dir / "META.json",
        json.dumps(
            {
                "sessionId": session_id,
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                "status": "active",
                "platform": sys.platform,
                "runtime": {"python": sys.version.split()[0], "node": ""},
                "capabilities": "full",
                "parentTestReport": None,
                "commandCount": 0,
                "totalDurationMs": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return session_dir


def build_mock_skill(base_dir: Path, outside_evidence: Path) -> tuple[Path, Path]:
    skill_dir = base_dir / "mock-skill"
    verifier_dir = base_dir / "external-verifier"
    skill_dir.mkdir(parents=True, exist_ok=True)
    verifier_dir.mkdir(parents=True, exist_ok=True)

    write_text(
        skill_dir / "SKILL.md",
        "\n".join(
            [
                "---",
                "name: Flow A Strict Smoke Skill",
                "---",
                "",
                "# Flow A Strict Smoke Skill",
                "",
                "## Trigger",
                "- Respond to all messages in the smoke test harness.",
                "",
                "allowed_tools:",
                "  - search_docs",
                "",
                "## Description",
                "Test-only mock skill for strict shim-live verification.",
                "",
                "## Usage",
                "- Used only by scripts/test_flow_a_strict.py.",
                "",
                "## Examples",
                "- Input: remember alpha for later",
                "  Output: stores context for the next turn",
                "",
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
                "",
                "def read_json(path: Path) -> object:",
                "    if not path.exists():",
                "        return []",
                "    return json.loads(path.read_text(encoding='utf-8-sig'))",
                "",
                "",
                "message = os.environ.get('NEXUS_MESSAGE', '')",
                "history_file = Path(os.environ.get('NEXUS_HISTORY_FILE', '')) if os.environ.get('NEXUS_HISTORY_FILE') else None",
                "output_file = Path(os.environ['NEXUS_OUTPUT_FILE'])",
                "result_file = Path(os.environ['NEXUS_RESULT_JSON_FILE'])",
                "artifacts_dir = Path(os.environ['NEXUS_ARTIFACTS_DIR'])",
                "outside_evidence = os.environ.get('MOCK_OUTSIDE_EVIDENCE', '')",
                "history = read_json(history_file) if history_file else []",
                "context_refs = []",
                "if 'context-check' in message and isinstance(history, list) and history:",
                "    context_refs = [1]",
                "trigger = 'do not trigger' not in message.lower()",
                "proof_file = artifacts_dir / 'delivery-proof.txt'",
                "proof_file.parent.mkdir(parents=True, exist_ok=True)",
                "proof_file.write_text('delivered\\n', encoding='utf-8')",
                "delivery_evidence = [outside_evidence] if 'outside-evidence' in message else [str(proof_file)]",
                "payload = {",
                "    'triggerMatched': trigger,",
                "    'toolsCalled': ['search_docs'],",
                "    'contextReferences': context_refs,",
                "    'assistantMessage': f'Handled: {message}',",
                "    'deliveryStatus': 'delivered',",
                "    'deliveryReceipts': ['receipt-001'],",
                "    'deliveryEvidence': delivery_evidence,",
                "    'notes': ['adapter-self-report'],",
                "}",
                "output_file.parent.mkdir(parents=True, exist_ok=True)",
                "output_file.write_text(payload['assistantMessage'] + '\\n', encoding='utf-8')",
                "result_file.parent.mkdir(parents=True, exist_ok=True)",
                "result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')",
                "print(json.dumps(payload, ensure_ascii=False))",
                "",
            ]
        ),
    )

    python_cmd = shlex.quote(Path(sys.executable).as_posix())
    verifier_cmd = f"{python_cmd} verify.py"
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
                "verified = {",
                "    'triggerMatched': payload.get('triggerMatched'),",
                "    'toolsCalled': payload.get('toolsCalled', []),",
                "    'contextReferences': payload.get('contextReferences', []),",
                "    'assistantMessage': payload.get('assistantMessage', ''),",
                "    'deliveryStatus': payload.get('deliveryStatus', 'unknown'),",
                "    'deliveryReceipts': payload.get('deliveryReceipts', []),",
                "    'deliveryEvidence': payload.get('deliveryEvidence', []),",
                "    'notes': ['verified-by-external-manifest'],",
                "}",
                "verifier_result.parent.mkdir(parents=True, exist_ok=True)",
                "verifier_result.write_text(json.dumps(verified, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')",
                "print(json.dumps(verified, ensure_ascii=False))",
                "",
            ]
        ),
    )
    write_text(
        verifier_dir / "shim-verifier.json",
        json.dumps(
            {
                "verify": {
                    "command": verifier_cmd,
                    "cwd": ".",
                    "timeoutSeconds": 30,
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    outside_evidence.write_text("outside-session\n", encoding="utf-8")
    return skill_dir, verifier_dir / "shim-verifier.json"


def build_mock_openclaw_without_telemetry(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    driver = bin_dir / "mock_openclaw_driver.py"
    write_text(
        driver,
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "",
                "print('mock live runtime without telemetry')",
                "raise SystemExit(0)",
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
    return wrapper


def run_process(args: list[str], env: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
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
    temp_root = Path(tempfile.mkdtemp(prefix="nexus-flow-a-strict-"))
    try:
        sandbox_root = temp_root / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        outside_evidence = temp_root / "outside-proof.txt"
        skill_dir, verifier_manifest = build_mock_skill(temp_root, outside_evidence)

        env = os.environ.copy()
        env["MOCK_OUTSIDE_EVIDENCE"] = str(outside_evidence)
        mock_live = build_mock_openclaw_without_telemetry(temp_root / "mock-live-bin")
        strict_auto_env = env.copy()
        strict_auto_env["PATH"] = str(mock_live.parent) + os.pathsep + strict_auto_env.get("PATH", "")

        create_session(sandbox_root, "flowa-strict-no-verifier")
        no_verifier_proc, no_verifier = run_process(
            [
                sys.executable,
                str(INVOKE_SCRIPT),
                "--session-id",
                "flowa-strict-no-verifier",
                "--skill-path",
                str(skill_dir),
                "--message",
                "basic shim-live strict run",
                "--channel",
                "telegram",
                "--mode",
                "shim-live",
                "--timeout",
                "30",
                "--strict-real",
                "--sandbox-root",
                str(sandbox_root),
            ],
            env=env,
        )
        assert_equal(no_verifier_proc.returncode, 3, "no verifier return code")
        assert_equal(no_verifier.get("INVOKE_STATUS"), "assertion-failed", "no verifier status")
        assert_equal(no_verifier.get("TELEMETRY_TRUST"), "self-reported", "no verifier telemetry trust")
        assert_equal(no_verifier.get("VERIFICATION_STATUS"), "not-configured", "no verifier verification status")
        assert_contains(
            no_verifier.get("ASSERTION_FAILURES", ""),
            "shim-live --strict-real requires an independent verification manifest",
            "no verifier failure message",
        )

        create_session(sandbox_root, "flowa-strict-with-verifier")
        with_verifier_proc, with_verifier = run_process(
            [
                sys.executable,
                str(INVOKE_SCRIPT),
                "--session-id",
                "flowa-strict-with-verifier",
                "--skill-path",
                str(skill_dir),
                "--message",
                "verify tool and delivery",
                "--channel",
                "telegram",
                "--mode",
                "shim-live",
                "--timeout",
                "30",
                "--strict-real",
                "--verification-manifest",
                str(verifier_manifest),
                "--expect-trigger",
                "true",
                "--require-tools",
                "search_docs",
                "--require-delivery-status",
                "delivered",
                "--require-delivery-evidence",
                "--sandbox-root",
                str(sandbox_root),
            ],
            env=env,
        )
        assert_equal(with_verifier_proc.returncode, 0, "with verifier return code")
        assert_equal(with_verifier.get("INVOKE_STATUS"), "success", "with verifier status")
        assert_equal(with_verifier.get("TELEMETRY_TRUST"), "independent", "with verifier telemetry trust")
        assert_equal(with_verifier.get("VERIFICATION_STATUS"), "passed", "with verifier verification status")
        assert_equal(with_verifier.get("ASSERTIONS_PASSED"), "true", "with verifier assertions")

        create_session(sandbox_root, "flowa-strict-auto-prefers-shim")
        auto_prefers_shim_proc, auto_prefers_shim = run_process(
            [
                sys.executable,
                str(INVOKE_SCRIPT),
                "--session-id",
                "flowa-strict-auto-prefers-shim",
                "--skill-path",
                str(skill_dir),
                "--message",
                "auto strict should prefer shim verification",
                "--channel",
                "telegram",
                "--mode",
                "auto",
                "--timeout",
                "30",
                "--strict-real",
                "--verification-manifest",
                str(verifier_manifest),
                "--expect-trigger",
                "true",
                "--require-tools",
                "search_docs",
                "--require-delivery-status",
                "delivered",
                "--require-delivery-evidence",
                "--sandbox-root",
                str(sandbox_root),
            ],
            env=strict_auto_env,
        )
        assert_equal(auto_prefers_shim_proc.returncode, 0, "auto strict shim preference return code")
        assert_equal(auto_prefers_shim.get("SELECTED_MODE"), "shim-live", "auto strict selected mode")
        assert_equal(auto_prefers_shim.get("TELEMETRY_TRUST"), "independent", "auto strict telemetry trust")
        assert_equal(auto_prefers_shim.get("INVOKE_STATUS"), "success", "auto strict status")

        create_session(sandbox_root, "flowa-strict-bad-evidence")
        bad_evidence_proc, bad_evidence = run_process(
            [
                sys.executable,
                str(INVOKE_SCRIPT),
                "--session-id",
                "flowa-strict-bad-evidence",
                "--skill-path",
                str(skill_dir),
                "--message",
                "outside-evidence please",
                "--channel",
                "telegram",
                "--mode",
                "shim-live",
                "--timeout",
                "30",
                "--strict-real",
                "--verification-manifest",
                str(verifier_manifest),
                "--require-delivery-status",
                "delivered",
                "--require-delivery-evidence",
                "--sandbox-root",
                str(sandbox_root),
            ],
            env=env,
        )
        assert_equal(bad_evidence_proc.returncode, 3, "bad evidence return code")
        assert_equal(bad_evidence.get("INVOKE_STATUS"), "assertion-failed", "bad evidence status")
        assert_contains(
            bad_evidence.get("INVALID_DELIVERY_EVIDENCE", ""),
            str(outside_evidence),
            "bad evidence invalid evidence path",
        )
        assert_contains(
            bad_evidence.get("ASSERTION_FAILURES", ""),
            "delivery evidence",
            "bad evidence assertion failure",
        )

        create_session(sandbox_root, "flowa-strict-multi-turn")
        conversation_file = temp_root / "conversation.json"
        write_text(
            conversation_file,
            json.dumps(
                {
                    "description": "Flow A strict multi-turn smoke",
                    "turns": [
                        {
                            "message": "remember alpha for later",
                            "expect_trigger": True,
                            "expect_tools": ["search_docs"],
                            "expect_delivery_status": "delivered",
                            "require_delivery_evidence": True,
                        },
                        {
                            "message": "context-check what did i ask before?",
                            "expect_trigger": True,
                            "expect_tools": ["search_docs"],
                            "expect_context_from_turn": 1,
                            "expect_delivery_status": "delivered",
                            "require_delivery_evidence": True,
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        multi_turn_proc, multi_turn = run_process(
            [
                sys.executable,
                str(MULTI_TURN_SCRIPT),
                "--session-id",
                "flowa-strict-multi-turn",
                "--skill-path",
                str(skill_dir),
                "--conversation-file",
                str(conversation_file),
                "--channel",
                "telegram",
                "--mode",
                "shim-live",
                "--timeout-per-turn",
                "30",
                "--strict-real",
                "--verification-manifest",
                str(verifier_manifest),
                "--sandbox-root",
                str(sandbox_root),
            ],
            env=env,
        )
        assert_equal(multi_turn_proc.returncode, 0, "multi-turn return code")
        assert_equal(multi_turn.get("MULTI_TURN_STATUS"), "all-passed", "multi-turn status")
        assert_equal(multi_turn.get("CONTEXT_PRESERVATION"), "verified", "multi-turn context preservation")

        same_repo_root = temp_root / "same-repo-fixture"
        (same_repo_root / ".git").mkdir(parents=True, exist_ok=True)
        same_repo_outside = same_repo_root / "outside-proof.txt"
        same_repo_skill, same_repo_verifier = build_mock_skill(same_repo_root, same_repo_outside)
        create_session(sandbox_root, "flowa-strict-same-repo")
        same_repo_proc, same_repo = run_process(
            [
                sys.executable,
                str(INVOKE_SCRIPT),
                "--session-id",
                "flowa-strict-same-repo",
                "--skill-path",
                str(same_repo_skill),
                "--message",
                "same repo verifier should fail",
                "--channel",
                "telegram",
                "--mode",
                "shim-live",
                "--timeout",
                "30",
                "--strict-real",
                "--verification-manifest",
                str(same_repo_verifier),
                "--sandbox-root",
                str(sandbox_root),
            ],
            env=env,
        )
        assert_equal(same_repo_proc.returncode, 1, "same repo verifier return code")
        assert_contains(
            same_repo_proc.stderr,
            "verification manifest must live outside the skill source repository to be independent",
            "same repo verifier failure",
        )

        summary = {
            "no_verifier_code": no_verifier_proc.returncode,
            "no_verifier_status": no_verifier.get("INVOKE_STATUS"),
            "no_verifier_trust": no_verifier.get("TELEMETRY_TRUST"),
            "with_verifier_code": with_verifier_proc.returncode,
            "with_verifier_status": with_verifier.get("INVOKE_STATUS"),
            "with_verifier_trust": with_verifier.get("TELEMETRY_TRUST"),
            "auto_strict_code": auto_prefers_shim_proc.returncode,
            "auto_strict_selected_mode": auto_prefers_shim.get("SELECTED_MODE"),
            "auto_strict_status": auto_prefers_shim.get("INVOKE_STATUS"),
            "bad_evidence_code": bad_evidence_proc.returncode,
            "bad_evidence_status": bad_evidence.get("INVOKE_STATUS"),
            "bad_invalid_delivery_evidence": bad_evidence.get("INVALID_DELIVERY_EVIDENCE"),
            "multi_turn_code": multi_turn_proc.returncode,
            "multi_turn_status": multi_turn.get("MULTI_TURN_STATUS"),
            "context_preservation": multi_turn.get("CONTEXT_PRESERVATION"),
            "same_repo_verifier_code": same_repo_proc.returncode,
            "same_repo_verifier_error": same_repo_proc.stderr.strip(),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
