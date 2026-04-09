#!/usr/bin/env python3
"""Smoke tests for nexus_runtime_bridge.py."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from test_helpers import assert_equal, make_temp_root, read_text, write_text

PROJECT_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = PROJECT_DIR / "scripts" / "nexus_stage_executor.py"
BRIDGE = PROJECT_DIR / "scripts" / "nexus_runtime_bridge.py"
MOCK_RUNTIME = PROJECT_DIR / "scripts" / "fixtures" / "mock_role_runtime.py"


def run_json(script: Path, *args: str) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"command exit code: {script.name} {' '.join(args)} returned {proc.returncode}; "
            f"stdout={proc.stdout!r}; stderr={proc.stderr!r}"
        )
    return json.loads(proc.stdout)


def write_runtime_config(
    path: Path,
    fail_role: str | None = None,
    takeover_role: str | None = None,
    fallback_role: str | None = None,
    blocked_role: str | None = None,
    weak_role: str | None = None,
) -> None:
    command = [
        sys.executable,
        str(MOCK_RUNTIME),
        "--payload-file",
        "{payload_file}",
        "--prompt-file",
        "{prompt_file}",
    ]
    config: dict[str, object] = {
        "name": "mock-runtime",
        "default": {
            "command": command,
            "cwd": "{workspace_root}",
            "timeoutSeconds": 30,
        }
    }
    roles: dict[str, object] = {}
    if fail_role:
        role_config: dict[str, object] = {
            "name": "mock-runtime",
            "command": command + ["--fail-role", fail_role],
            "cwd": "{workspace_root}",
            "timeoutSeconds": 30,
        }
        if fallback_role and fallback_role == fail_role:
            role_config["fallback"] = {
                "name": "mock-runtime-fallback",
                "command": command,
                "cwd": "{workspace_root}",
                "timeoutSeconds": 30,
            }
        roles[fail_role] = role_config
    if takeover_role:
        roles[takeover_role] = {
            "name": "mock-runtime",
            "command": command + ["--takeover-role", takeover_role],
            "cwd": "{workspace_root}",
            "timeoutSeconds": 30,
        }
    if blocked_role:
        roles[blocked_role] = {
            "name": "mock-runtime",
            "command": command + ["--blocked-role", blocked_role],
            "cwd": "{workspace_root}",
            "timeoutSeconds": 30,
        }
    if weak_role:
        roles[weak_role] = {
            "name": "mock-runtime",
            "command": command + ["--weak-role", weak_role],
            "cwd": "{workspace_root}",
            "timeoutSeconds": 30,
        }
    if roles:
        config["roles"] = roles
    write_text(path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")


def approve_stage(report_dir: Path, stage_id: str) -> None:
    run_json(EXECUTOR, "record-approval-request", "--report-dir", str(report_dir), "--stage-id", stage_id, "--transport", "text")
    run_json(EXECUTOR, "record-approval-response", "--report-dir", str(report_dir), "--stage-id", stage_id, "--response", "approved")


def test_run_until_gate_flow_a() -> None:
    temp_root = make_temp_root("runtime-bridge-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime.json"
        write_runtime_config(config_path)

        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        first = run_json(BRIDGE, "run-until-gate", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(first["status"], "await-approval", "first gate status")
        assert_equal(first["gateAction"]["stageId"], "stage-0", "stage zero gate")

        approve_stage(report_dir, "stage-0")
        second = run_json(BRIDGE, "run-until-gate", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(second["status"], "await-approval", "second gate status")
        assert_equal(second["gateAction"]["stageId"], "stage-2", "stage two gate")

        approve_stage(report_dir, "stage-2")
        third = run_json(BRIDGE, "run-until-gate", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(third["status"], "await-approval", "third gate status")
        assert_equal(third["gateAction"]["stageId"], "stage-4", "stage four gate")

        approve_stage(report_dir, "stage-4")
        final = run_json(BRIDGE, "run-until-gate", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(final["status"], "complete", "final flow status")
        report_path = report_dir / "FINAL-TEST-REPORT.md"
        assert_equal(report_path.exists(), True, "final report exists")
        print("  [PASS] test_run_until_gate_flow_a")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_role_failure_stops_runtime_bridge() -> None:
    temp_root = make_temp_root("runtime-bridge-fail-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime.json"
        write_runtime_config(config_path, fail_role="environment-checker")

        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        failed = run_json(BRIDGE, "run-once", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(failed["status"], "role-failed", "failed bridge status")
        assert_equal(failed["runStatus"]["failedCount"], 1, "failed count")
        state = json.loads(read_text(report_dir / "RUNS" / "stage-0" / "environment-checker.state.json"))
        assert_equal(state["status"], "failed", "failed role state file")
        print("  [PASS] test_role_failure_stops_runtime_bridge")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_missing_stage_outputs_trigger_rerun() -> None:
    temp_root = make_temp_root("runtime-bridge-rerun-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime.json"
        write_runtime_config(config_path)

        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json(BRIDGE, "run-until-gate", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        approve_stage(report_dir, "stage-0")
        run_json(BRIDGE, "run-until-gate", "--report-dir", str(report_dir), "--runtime-config", str(config_path))

        for relative in ("PRODUCT-FINGERPRINT.json", "SPEC.md", "SPEC-CONSISTENCY-REVIEW.md"):
            target = report_dir / relative
            if target.exists():
                target.unlink()

        rerun = run_json(BRIDGE, "run-until-gate", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(rerun["status"], "await-approval", "rerun reaches next gate")
        assert_equal(rerun["gateAction"]["stageId"], "stage-2", "rerun next gate stage")
        assert_equal((report_dir / "PRODUCT-FINGERPRINT.json").exists(), True, "fingerprint regenerated")
        assert_equal((report_dir / "SPEC.md").exists(), True, "spec regenerated")
        assert_equal((report_dir / "SPEC-CONSISTENCY-REVIEW.md").exists(), True, "consistency review regenerated")
        print("  [PASS] test_missing_stage_outputs_trigger_rerun")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_missing_runtime_command_marks_failure() -> None:
    temp_root = make_temp_root("runtime-bridge-missing-cmd-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime.json"
        write_text(
            config_path,
            json.dumps(
                {
                    "name": "missing-command-runtime",
                    "default": {
                        "command": ["definitely-missing-runtime-command-xyz", "--payload-file", "{payload_file}"],
                        "cwd": "{workspace_root}",
                        "timeoutSeconds": 30,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )

        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        failed = run_json(BRIDGE, "run-once", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(failed["status"], "role-failed", "missing command bridge status")
        state = json.loads(read_text(report_dir / "RUNS" / "stage-0" / "environment-checker.state.json"))
        assert_equal(state["status"], "failed", "missing command role state file")
        assert_equal("FileNotFoundError" in str(state["note"]), True, "missing command failure note")
        print("  [PASS] test_missing_runtime_command_marks_failure")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_invalid_runtime_config_rejected_before_execution() -> None:
    temp_root = make_temp_root("runtime-bridge-invalid-config-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime.json"
        write_text(
            config_path,
            json.dumps(
                {
                    "name": "broken-runtime",
                    "default": {
                        "command": [],
                        "cwd": "{workspace_root}",
                        "timeoutSeconds": 30,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )

        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        proc = subprocess.run(
            [sys.executable, str(BRIDGE), "run-once", "--report-dir", str(report_dir), "--runtime-config", str(config_path)],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(proc.returncode == 0, False, "invalid config should fail fast")
        assert_equal("ERROR: invalid runtime config:" in proc.stderr, True, "invalid config error surfaced")
        print("  [PASS] test_invalid_runtime_config_rejected_before_execution")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_role_takeover_stops_runtime_bridge() -> None:
    temp_root = make_temp_root("runtime-bridge-takeover-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime.json"
        write_runtime_config(config_path, takeover_role="environment-checker")

        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        takeover = run_json(BRIDGE, "run-once", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(takeover["status"], "takeover-required", "takeover bridge status")
        state = json.loads(read_text(report_dir / "RUNS" / "stage-0" / "environment-checker.state.json"))
        assert_equal(state["status"], "takeover-required", "takeover role state file")
        assert_equal((report_dir / "RUNS" / "stage-0" / "environment-checker.takeover.json").exists(), True, "takeover file exists")
        print("  [PASS] test_role_takeover_stops_runtime_bridge")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_fallback_runtime_recovers_failed_role() -> None:
    temp_root = make_temp_root("runtime-bridge-fallback-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime.json"
        write_runtime_config(config_path, fail_role="environment-checker", fallback_role="environment-checker")

        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        recovered = run_json(BRIDGE, "run-once", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(recovered["status"], "stage-run-finished", "fallback recovers bridge status")
        state = json.loads(read_text(report_dir / "RUNS" / "stage-0" / "environment-checker.state.json"))
        assert_equal(state["status"], "completed", "fallback role state file")
        print("  [PASS] test_fallback_runtime_recovers_failed_role")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_blocked_skill_tester_becomes_takeover_required() -> None:
    temp_root = make_temp_root("runtime-bridge-blocked-skill-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime.json"
        write_runtime_config(config_path, blocked_role="skill-tester")

        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        first = run_json(BRIDGE, "run-until-gate", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(first["status"], "await-approval", "first gate status")
        approve_stage(report_dir, "stage-0")
        second = run_json(BRIDGE, "run-until-gate", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(second["status"], "await-approval", "second gate status")
        approve_stage(report_dir, "stage-2")
        third = run_json(BRIDGE, "run-until-gate", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(third["status"], "await-approval", "third gate status")
        approve_stage(report_dir, "stage-4")
        final = run_json(BRIDGE, "run-once", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(final["status"], "takeover-required", "blocked skill tester becomes takeover")
        print("  [PASS] test_blocked_skill_tester_becomes_takeover_required")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_blocked_environment_checker_remains_failure() -> None:
    temp_root = make_temp_root("runtime-bridge-blocked-env-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime.json"
        write_runtime_config(config_path, blocked_role="environment-checker")

        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        final = run_json(BRIDGE, "run-once", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(final["status"], "role-failed", "blocked environment checker stays failed")
        state = json.loads(read_text(report_dir / "RUNS" / "stage-0" / "environment-checker.state.json"))
        assert_equal(state["status"], "failed", "blocked environment checker state file")
        print("  [PASS] test_blocked_environment_checker_remains_failure")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_quality_assessor_missing_required_sections_fails() -> None:
    temp_root = make_temp_root("runtime-bridge-weak-quality-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime.json"
        write_runtime_config(config_path, weak_role="quality-assessor")

        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        first = run_json(BRIDGE, "run-until-gate", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(first["status"], "await-approval", "first gate status")
        approve_stage(report_dir, "stage-0")
        second = run_json(BRIDGE, "run-until-gate", "--report-dir", str(report_dir), "--runtime-config", str(config_path))
        assert_equal(second["status"], "role-failed", "weak quality assessor should fail validation")
        state = json.loads(read_text(report_dir / "RUNS" / "stage-2" / "quality-assessor.state.json"))
        assert_equal(state["status"], "failed", "weak quality assessor state file")
        assert_equal("missing required sections" in str(state["note"]), True, "validator note recorded")
        print("  [PASS] test_quality_assessor_missing_required_sections_fails")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Nexus Runtime Bridge Smoke Tests")
    print("=" * 40)
    for test in (
        test_run_until_gate_flow_a,
        test_role_failure_stops_runtime_bridge,
        test_missing_stage_outputs_trigger_rerun,
        test_missing_runtime_command_marks_failure,
        test_invalid_runtime_config_rejected_before_execution,
        test_role_takeover_stops_runtime_bridge,
        test_fallback_runtime_recovers_failed_role,
        test_blocked_skill_tester_becomes_takeover_required,
        test_blocked_environment_checker_remains_failure,
        test_quality_assessor_missing_required_sections_fails,
    ):
        try:
            test()
            passed += 1
        except AssertionError as exc:
            print(f"  [FAIL] {test.__name__}: {exc}")
            failed += 1
    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
