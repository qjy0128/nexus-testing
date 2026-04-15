#!/usr/bin/env python3
"""Smoke tests for run_openclaw_stage_demo.py."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from test_helpers import assert_equal, make_temp_root, read_text, write_text

PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "scripts" / "run_openclaw_stage_demo.py"
MOCK_RUNTIME = PROJECT_DIR / "scripts" / "fixtures" / "mock_role_runtime.py"


def run_json(*args: str) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert_equal(proc.returncode, 0, f"command exit code: {' '.join(args)}")
    return json.loads(proc.stdout)


def run_proc(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def timestamp_minutes_ago(minutes: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - minutes * 60))


def update_approval_record(report_dir: Path, stage_id: str, **updates: object) -> dict[str, object]:
    approvals = json.loads(read_text(report_dir / "approval-records.json"))
    key = stage_id.replace("-", "_")
    record = approvals.get(key, {})
    record.update(updates)
    approvals[key] = record
    write_text(report_dir / "approval-records.json", json.dumps(approvals, ensure_ascii=False, indent=2) + "\n")
    return record


def write_mock_openclaw_config(path: Path) -> None:
    config = {
        "name": "openclaw-role-runtime",
        "default": {
            "command": [
                sys.executable,
                str(PROJECT_DIR / "scripts" / "nexus_openclaw_role_runtime.py"),
                "--payload-file",
                "{payload_file}",
                "--prompt-file",
                "{prompt_file}",
                "--openclaw-command",
                sys.executable,
                "--openclaw-args",
                str(PROJECT_DIR / "scripts" / "fixtures" / "mock_openclaw_cli.py"),
                "--skill-path",
                ".",
                "--channel",
                "telegram",
            ],
            "cwd": "{workspace_root}",
            "timeoutSeconds": 120,
        },
    }
    write_text(path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")


def write_full_mock_runtime_config(path: Path) -> None:
    config = {
        "name": "mock-runtime",
        "default": {
            "command": [
                sys.executable,
                str(MOCK_RUNTIME),
                "--payload-file",
                "{payload_file}",
                "--prompt-file",
                "{prompt_file}",
            ],
            "cwd": "{workspace_root}",
            "timeoutSeconds": 30,
            "stallTimeoutSeconds": 10,
        },
    }
    write_text(path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")


def complete_demo_flow(report_dir: Path, config_path: Path) -> dict[str, object]:
    started = run_json(
        "start",
        "--report-dir",
        str(report_dir),
        "--runtime-config",
        str(config_path),
    )
    assert_equal(started["summary"]["status"], "await-approval", "start status")
    assert_equal(started["summary"]["runtimeResult"]["gateAction"]["stageId"], "stage-0", "first gate")

    second = run_json(
        "approve",
        "--report-dir",
        str(report_dir),
        "--stage-id",
        "stage-0",
        "--runtime-config",
        str(config_path),
        "--continue-run",
    )
    assert_equal(second["summary"]["status"], "await-approval", "second status")
    assert_equal(second["summary"]["runtimeResult"]["gateAction"]["stageId"], "stage-2", "second gate")

    third = run_json(
        "approve",
        "--report-dir",
        str(report_dir),
        "--stage-id",
        "stage-2",
        "--runtime-config",
        str(config_path),
        "--continue-run",
    )
    assert_equal(third["summary"]["status"], "await-approval", "third status")
    assert_equal(third["summary"]["runtimeResult"]["gateAction"]["stageId"], "stage-4", "third gate")

    final = run_json(
        "approve",
        "--report-dir",
        str(report_dir),
        "--stage-id",
        "stage-4",
        "--runtime-config",
        str(config_path),
        "--continue-run",
    )
    assert_equal(final["summary"]["status"], "complete", "final status")
    return final


def test_start_and_approve_flow() -> None:
    temp_root = make_temp_root("openclaw-demo-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime-config.openclaw.mock.json"
        write_mock_openclaw_config(config_path)

        started = run_json(
            "start",
            "--report-dir",
            str(report_dir),
            "--runtime-config",
            str(config_path),
        )
        assert_equal(started["summary"]["status"], "await-approval", "start status")
        assert_equal(started["summary"]["runtimeResult"]["gateAction"]["stageId"], "stage-0", "first gate")
        assert_equal(bool(started["summary"]["approvalRecords"]["stage_0"]["sent_at"]), True, "approval request recorded at gate")

        approved = run_json(
            "approve",
            "--report-dir",
            str(report_dir),
            "--stage-id",
            "stage-0",
            "--runtime-config",
            str(config_path),
            "--continue-run",
        )
        assert_equal(approved["summary"]["status"], "await-approval", "second status")
        assert_equal(approved["summary"]["runtimeResult"]["gateAction"]["stageId"], "stage-2", "second gate")
        print("  [PASS] test_start_and_approve_flow")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_detect_existing_without_session() -> None:
    temp_root = make_temp_root("openclaw-demo-detect-")
    try:
        report_dir = temp_root / "reports"
        detected = run_json(
            "detect-existing",
            "--report-dir",
            str(report_dir),
        )
        assert_equal(detected["status"], "no-session", "detect-existing status")
        print("  [PASS] test_detect_existing_without_session")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_detect_existing_completed_session() -> None:
    temp_root = make_temp_root("openclaw-demo-complete-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime-config.mock.json"
        write_full_mock_runtime_config(config_path)

        complete_demo_flow(report_dir, config_path)
        detected = run_json(
            "detect-existing",
            "--report-dir",
            str(report_dir),
        )
        assert_equal(detected["status"], "session-complete", "completed session detect status")
        assert_equal(detected["lastCompletedStage"], "stage-7", "completed session last stage")
        print("  [PASS] test_detect_existing_completed_session")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_continue_auto_continues_overdue_gate() -> None:
    temp_root = make_temp_root("openclaw-demo-timeout-continue-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime-config.mock.json"
        write_full_mock_runtime_config(config_path)

        started = run_json(
            "start",
            "--report-dir",
            str(report_dir),
            "--runtime-config",
            str(config_path),
        )
        assert_equal(started["summary"]["status"], "await-approval", "initial gate status")
        overdue = timestamp_minutes_ago(31)
        update_approval_record(report_dir, "stage-0", sent_at=overdue, waiting_since=overdue)

        continued = run_json(
            "continue",
            "--report-dir",
            str(report_dir),
            "--runtime-config",
            str(config_path),
        )
        assert_equal(continued["summary"]["status"], "await-approval", "continue should reach next gate")
        assert_equal(continued["summary"]["runtimeResult"]["gateAction"]["stageId"], "stage-2", "continue should auto-advance to stage two gate")
        approvals = json.loads(read_text(report_dir / "approval-records.json"))
        assert_equal(approvals["stage_0"]["user_response"], "auto-continue", "overdue gate auto-continued")
        print("  [PASS] test_continue_auto_continues_overdue_gate")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_detect_existing_reconciles_overdue_gate() -> None:
    temp_root = make_temp_root("openclaw-demo-timeout-detect-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime-config.mock.json"
        write_full_mock_runtime_config(config_path)

        started = run_json(
            "start",
            "--report-dir",
            str(report_dir),
            "--runtime-config",
            str(config_path),
        )
        assert_equal(started["summary"]["status"], "await-approval", "initial gate status")
        overdue = timestamp_minutes_ago(31)
        update_approval_record(report_dir, "stage-0", sent_at=overdue, waiting_since=overdue)

        detected = run_json(
            "detect-existing",
            "--report-dir",
            str(report_dir),
        )
        assert_equal(detected["status"], "recoverable", "overdue gate should become recoverable after auto-continue")
        assert_equal(detected["pendingStageId"], "stage-1", "next pending stage after auto-continue")
        assert_equal(detected["timeoutAction"]["status"], "auto-continued", "timeout action recorded")
        print("  [PASS] test_detect_existing_reconciles_overdue_gate")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_recover_from_stage_archives_outputs_and_reopens_gate() -> None:
    temp_root = make_temp_root("openclaw-demo-recover-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime-config.mock.json"
        write_full_mock_runtime_config(config_path)

        complete_demo_flow(report_dir, config_path)
        recovered = run_json(
            "recover",
            "--report-dir",
            str(report_dir),
            "--from-stage",
            "stage-3",
            "--runtime-config",
            str(config_path),
        )
        assert_equal(recovered["resumedAt"], "stage-3", "recovery resumed stage")
        assert_equal(recovered["recovery"]["fromStage"], "stage-3", "recovery from stage echo")
        assert_equal(recovered["summary"]["status"], "await-approval", "recovery gate status")
        assert_equal(
            recovered["summary"]["runtimeResult"]["gateAction"]["stageId"],
            "stage-4",
            "recovery should reopen stage four gate",
        )

        stage_log = json.loads(read_text(report_dir / "stage-transition-log.json"))
        manual_recovery = [entry for entry in stage_log if isinstance(entry, dict) and entry.get("event") == "manual-recovery"]
        assert_equal(len(manual_recovery) > 0, True, "manual recovery event exists")
        archive_dir = Path(str(manual_recovery[-1]["archive_dir"]))
        assert_equal(archive_dir.exists(), True, "recovery archive exists")
        assert_equal((archive_dir / "TEST-DESIGN.md").exists(), True, "archived test design exists")
        assert_equal((archive_dir / "TEST-CASE-REVIEW.md").exists(), True, "archived test case review exists")
        assert_equal((archive_dir / "FINAL-TEST-REPORT.md").exists(), True, "archived final report exists")
        print("  [PASS] test_recover_from_stage_archives_outputs_and_reopens_gate")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_approve_without_continue_does_not_load_runtime_config() -> None:
    temp_root = make_temp_root("openclaw-demo-approve-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime-config.openclaw.mock.json"
        missing_config_path = temp_root / "missing-runtime.json"
        write_mock_openclaw_config(config_path)

        run_json(
            "start",
            "--report-dir",
            str(report_dir),
            "--runtime-config",
            str(config_path),
        )
        approved = run_json(
            "approve",
            "--report-dir",
            str(report_dir),
            "--stage-id",
            "stage-0",
            "--runtime-config",
            str(missing_config_path),
        )
        assert_equal(approved["approval"]["status"], "approved", "approve-only status")
        print("  [PASS] test_approve_without_continue_does_not_load_runtime_config")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_start_rejects_flow_mode_mismatch() -> None:
    temp_root = make_temp_root("openclaw-demo-mismatch-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime-config.openclaw.mock.json"
        write_mock_openclaw_config(config_path)

        run_json(
            "start",
            "--report-dir",
            str(report_dir),
            "--flow",
            "skill",
            "--runtime-config",
            str(config_path),
        )
        proc = run_proc(
            "start",
            "--report-dir",
            str(report_dir),
            "--flow",
            "web-api",
            "--runtime-config",
            str(config_path),
        )
        assert_equal(proc.returncode == 0, False, "flow mismatch should fail")
        assert_equal("does not match requested flow/mode" in (proc.stderr + proc.stdout), True, "flow mismatch error")
        print("  [PASS] test_start_rejects_flow_mode_mismatch")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("OpenClaw Stage Demo Smoke Tests")
    print("=" * 40)
    for test in (
        test_start_and_approve_flow,
        test_detect_existing_without_session,
        test_detect_existing_completed_session,
        test_continue_auto_continues_overdue_gate,
        test_detect_existing_reconciles_overdue_gate,
        test_recover_from_stage_archives_outputs_and_reopens_gate,
        test_approve_without_continue_does_not_load_runtime_config,
        test_start_rejects_flow_mode_mismatch,
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
