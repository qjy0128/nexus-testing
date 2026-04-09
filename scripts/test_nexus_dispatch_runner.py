#!/usr/bin/env python3
"""Smoke tests for nexus_dispatch_runner.py."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from test_helpers import assert_equal, make_temp_root

PROJECT_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = PROJECT_DIR / "scripts" / "nexus_stage_executor.py"
RUNNER = PROJECT_DIR / "scripts" / "nexus_dispatch_runner.py"


def run_json(script: Path, *args: str) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert_equal(proc.returncode, 0, f"command exit code: {script.name} {' '.join(args)}")
    return json.loads(proc.stdout)


def test_prepare_and_status() -> None:
    temp_root = make_temp_root("dispatch-runner-")
    try:
        report_dir = temp_root / "reports"
        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        prepared = run_json(RUNNER, "prepare", "--report-dir", str(report_dir))
        assert_equal(prepared["status"], "run-stage", "prepare status")
        status = run_json(RUNNER, "status", "--report-dir", str(report_dir))
        assert_equal(status["totalCount"], 1, "runner role count")
        print("  [PASS] test_prepare_and_status")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_role_lifecycle_and_advance() -> None:
    temp_root = make_temp_root("dispatch-runner-advance-")
    try:
        report_dir = temp_root / "reports"
        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json(RUNNER, "prepare", "--report-dir", str(report_dir))
        run_json(RUNNER, "start-role", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--role-id", "environment-checker")
        result_file = report_dir / "STAGE-SUBAGENT-PLAN.json"
        run_json(
            RUNNER,
            "complete-role",
            "--report-dir",
            str(report_dir),
            "--stage-id",
            "stage-0",
            "--role-id",
            "environment-checker",
            "--result-file",
            str(result_file),
        )
        advanced = run_json(RUNNER, "advance", "--report-dir", str(report_dir))
        assert_equal(advanced["status"], "advanced", "advance status")
        assert_equal(advanced["completedStageId"], "stage-0", "completed stage id")
        assert_equal(advanced["stageCompleteEvent"]["event"], "stage-complete", "stage complete event")
        assert_equal(advanced["nextAction"]["status"], "await-approval", "next action after stage zero")
        assert_equal(advanced["nextAction"]["stageId"], "stage-0", "approval stage id")
        print("  [PASS] test_role_lifecycle_and_advance")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_waiting_for_completion() -> None:
    temp_root = make_temp_root("dispatch-runner-wait-")
    try:
        report_dir = temp_root / "reports"
        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json(RUNNER, "prepare", "--report-dir", str(report_dir))
        waiting = run_json(RUNNER, "advance", "--report-dir", str(report_dir))
        assert_equal(waiting["status"], "waiting-role-completion", "waiting status")
        print("  [PASS] test_waiting_for_completion")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_failed_role_state() -> None:
    temp_root = make_temp_root("dispatch-runner-fail-")
    try:
        report_dir = temp_root / "reports"
        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json(RUNNER, "prepare", "--report-dir", str(report_dir))
        failed = run_json(
            RUNNER,
            "fail-role",
            "--report-dir",
            str(report_dir),
            "--stage-id",
            "stage-0",
            "--role-id",
            "environment-checker",
            "--note",
            "mock failure",
        )
        assert_equal(failed["status"], "failed", "failed role status")
        status = run_json(RUNNER, "status", "--report-dir", str(report_dir))
        assert_equal(status["failedCount"], 1, "failed role count")
        assert_equal(status["allCompleted"], False, "failed role prevents advance")
        print("  [PASS] test_failed_role_state")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_takeover_role_state() -> None:
    temp_root = make_temp_root("dispatch-runner-takeover-")
    try:
        report_dir = temp_root / "reports"
        takeover_file = report_dir / "RUNS" / "stage-0" / "environment-checker.takeover.json"
        takeover_file.parent.mkdir(parents=True, exist_ok=True)
        takeover_file.write_text('{"status":"takeover-required"}\n', encoding="utf-8")
        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json(RUNNER, "prepare", "--report-dir", str(report_dir))
        takeover = run_json(
            RUNNER,
            "takeover-role",
            "--report-dir",
            str(report_dir),
            "--stage-id",
            "stage-0",
            "--role-id",
            "environment-checker",
            "--note",
            "needs main-agent takeover",
            "--takeover-file",
            str(takeover_file),
        )
        assert_equal(takeover["status"], "takeover-required", "takeover role status")
        status = run_json(RUNNER, "status", "--report-dir", str(report_dir))
        assert_equal(status["takeoverRequiredCount"], 1, "takeover role count")
        assert_equal(status["allCompleted"], False, "takeover role prevents advance")
        print("  [PASS] test_takeover_role_state")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Nexus Dispatch Runner Smoke Tests")
    print("=" * 40)
    for test in (
        test_prepare_and_status,
        test_role_lifecycle_and_advance,
        test_waiting_for_completion,
        test_failed_role_state,
        test_takeover_role_state,
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
