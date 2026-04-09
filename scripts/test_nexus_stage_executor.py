#!/usr/bin/env python3
"""Smoke tests for nexus_stage_executor.py."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from test_helpers import assert_equal, make_temp_root, read_text, write_text

PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "scripts" / "nexus_stage_executor.py"


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


def test_init_and_next() -> None:
    temp_root = make_temp_root("stage-exec-")
    try:
        report_dir = temp_root / "reports"
        init_result = run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        assert_equal(init_result["status"], "initialized", "init status")
        next_result = run_json("next", "--report-dir", str(report_dir))
        assert_equal(next_result["status"], "run-stage", "next status")
        assert_equal(next_result["stageId"], "stage-0", "next stage id")
        print("  [PASS] test_init_and_next")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_stage_progression_with_approval() -> None:
    temp_root = make_temp_root("stage-exec-approval-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")

        run_json("mark-stage-complete", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--deliverable-file", "STAGE-SUBAGENT-PLAN.json")
        next_result = run_json("next", "--report-dir", str(report_dir))
        assert_equal(next_result["status"], "await-approval", "stage zero approval wait")

        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--transport", "text")
        run_json("record-approval-response", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--response", "approved")

        write_text(report_dir / "PRODUCT-FINGERPRINT.json", "{}\n")
        write_text(report_dir / "SPEC.md", "# Spec\n")
        write_text(report_dir / "SPEC-CONSISTENCY-REVIEW.md", "# Review\n")
        next_after_stage1 = run_json("next", "--report-dir", str(report_dir))
        assert_equal(next_after_stage1["stageId"], "stage-2", "stage two becomes next")
        print("  [PASS] test_stage_progression_with_approval")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_rejection_tracking() -> None:
    temp_root = make_temp_root("stage-exec-reject-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json("mark-stage-complete", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--deliverable-file", "STAGE-SUBAGENT-PLAN.json")
        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--transport", "text")
        run_json("record-approval-response", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--response", "approved")
        write_text(report_dir / "PRODUCT-FINGERPRINT.json", "{}\n")
        write_text(report_dir / "SPEC.md", "# Spec\n")
        write_text(report_dir / "SPEC-CONSISTENCY-REVIEW.md", "# Review\n")
        write_text(report_dir / "PRODUCT-QUALITY-REVIEW.md", "# Quality\n")

        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-2", "--transport", "text")
        run_json("record-approval-response", "--report-dir", str(report_dir), "--stage-id", "stage-2", "--response", "rejected", "--reason", "need-more-detail")
        rejections = json.loads(read_text(report_dir / "rejection-count.json"))
        assert_equal(rejections["stage_2"]["count"], 1, "rejection count")
        print("  [PASS] test_rejection_tracking")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_approval_stage_must_match_current_gate() -> None:
    temp_root = make_temp_root("stage-exec-invalid-approval-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        write_text(report_dir / "STAGE-SUBAGENT-PLAN.json", read_text(report_dir / "STAGE-SUBAGENT-PLAN.json"))
        run_json("mark-stage-complete", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--deliverable-file", "STAGE-SUBAGENT-PLAN.json")
        proc = run_proc("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-7", "--transport", "text")
        assert_equal(proc.returncode == 0, False, "invalid approval request should fail")
        assert_equal("current gate is stage-0" in (proc.stderr + proc.stdout), True, "invalid approval request error")
        print("  [PASS] test_approval_stage_must_match_current_gate")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dispatch_payloads() -> None:
    temp_root = make_temp_root("stage-exec-dispatch-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        dispatch = run_json("dispatch", "--report-dir", str(report_dir))
        assert_equal(dispatch["status"], "run-stage", "dispatch status")
        payloads = dispatch["dispatchPayloads"]
        assert_equal(len(payloads), 1, "dispatch payload count")
        assert_equal(payloads[0]["roleId"], "environment-checker", "dispatch role id")
        print("  [PASS] test_dispatch_payloads")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_bundle_dispatch() -> None:
    temp_root = make_temp_root("stage-exec-bundle-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        bundled = run_json("bundle-dispatch", "--report-dir", str(report_dir))
        manifest_path = Path(str(bundled["manifestFile"]))
        assert_equal(manifest_path.exists(), True, "bundle manifest exists")
        manifest = json.loads(read_text(manifest_path))
        assert_equal(manifest["roles"][0]["roleId"], "environment-checker", "bundle role id")
        prompt_path = manifest_path.parent / manifest["roles"][0]["promptFile"]
        assert_equal(prompt_path.exists(), True, "bundle prompt exists")
        print("  [PASS] test_bundle_dispatch")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Nexus Stage Executor Smoke Tests")
    print("=" * 40)
    for test in (
        test_init_and_next,
        test_stage_progression_with_approval,
        test_rejection_tracking,
        test_approval_stage_must_match_current_gate,
        test_dispatch_payloads,
        test_bundle_dispatch,
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
