#!/usr/bin/env python3
"""Smoke tests for nexus_stage_executor.py."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import nexus_stage_executor as executor_module
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


def test_init_and_next() -> None:
    temp_root = make_temp_root("stage-exec-")
    try:
        report_dir = temp_root / "reports"
        init_result = run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        assert_equal(init_result["status"], "initialized", "init status")
        assert_equal(init_result["executionProfile"], "internal-fast", "default execution profile")
        assert_equal(init_result["delivery"]["backend"], "relay-only", "default delivery backend")
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
        approval = run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--transport", "text")
        assert_equal(bool(approval["artifactValidation"]["fileSummaries"]), True, "approval request includes artifact summaries")
        run_json("record-approval-response", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--response", "approved")
        write_text(report_dir / "PRODUCT-FINGERPRINT.json", "{}\n")
        write_text(report_dir / "SPEC.md", "# Spec\n")
        write_text(report_dir / "SPEC-CONSISTENCY-REVIEW.md", "# Review\n")
        quality_meta = executor_module.parse_role_doc(PROJECT_DIR / "roles" / "quality-assessor.md")
        quality_lines = ["# Product Quality Review", ""]
        for heading in quality_meta["minimumOutput"]:
            quality_lines.extend([f"## {heading}", "This section contains substantive review content for the approval gate.", ""])
        write_text(
            report_dir / "PRODUCT-QUALITY-REVIEW.md",
            "\n".join(quality_lines),
        )

        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-2", "--transport", "text")
        run_json("record-approval-response", "--report-dir", str(report_dir), "--stage-id", "stage-2", "--response", "rejected", "--reason", "need-more-detail")
        rejections = json.loads(read_text(report_dir / "rejection-count.json"))
        assert_equal(rejections["stage_2"]["count"], 1, "rejection count")
        print("  [PASS] test_rejection_tracking")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_rejected_response_requires_reason() -> None:
    temp_root = make_temp_root("stage-exec-reject-reason-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json("mark-stage-complete", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--deliverable-file", "STAGE-SUBAGENT-PLAN.json")
        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--transport", "text")
        run_json("record-approval-response", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--response", "approved")
        write_text(report_dir / "PRODUCT-FINGERPRINT.json", "{}\n")
        write_text(report_dir / "SPEC.md", "# Spec\n")
        write_text(report_dir / "SPEC-CONSISTENCY-REVIEW.md", "# Review\n")
        quality_meta = executor_module.parse_role_doc(PROJECT_DIR / "roles" / "quality-assessor.md")
        quality_lines = ["# Product Quality Review", ""]
        for heading in quality_meta["minimumOutput"]:
            quality_lines.extend([f"## {heading}", "This section contains substantive review content for the approval gate.", ""])
        write_text(report_dir / "PRODUCT-QUALITY-REVIEW.md", "\n".join(quality_lines))

        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-2", "--transport", "text")
        proc = run_proc(
            "record-approval-response",
            "--report-dir",
            str(report_dir),
            "--stage-id",
            "stage-2",
            "--response",
            "rejected",
            "--reason",
            "too-short",
        )
        assert_equal(proc.returncode == 0, False, "short rejection reason should fail")
        assert_equal("rejection reason must be at least 10 characters" in (proc.stderr + proc.stdout), True, "short rejection reason error")
        print("  [PASS] test_rejected_response_requires_reason")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_three_rejections_yield_no_go() -> None:
    temp_root = make_temp_root("stage-exec-no-go-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json("mark-stage-complete", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--deliverable-file", "STAGE-SUBAGENT-PLAN.json")
        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--transport", "text")
        run_json("record-approval-response", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--response", "approved")
        write_text(report_dir / "PRODUCT-FINGERPRINT.json", "{}\n")
        write_text(report_dir / "SPEC.md", "# Spec\n")
        write_text(report_dir / "SPEC-CONSISTENCY-REVIEW.md", "# Review\n")
        quality_meta = executor_module.parse_role_doc(PROJECT_DIR / "roles" / "quality-assessor.md")
        quality_lines = ["# Product Quality Review", ""]
        for heading in quality_meta["minimumOutput"]:
            quality_lines.extend([f"## {heading}", "This section contains substantive review content for the approval gate.", ""])
        write_text(report_dir / "PRODUCT-QUALITY-REVIEW.md", "\n".join(quality_lines))

        for count in range(1, 4):
            run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-2", "--transport", "text")
            run_json(
                "record-approval-response",
                "--report-dir",
                str(report_dir),
                "--stage-id",
                "stage-2",
                "--response",
                "rejected",
                "--reason",
                f"need-more-detail-{count}",
            )

        next_result = run_json("next", "--report-dir", str(report_dir))
        assert_equal(next_result["status"], "no-go", "three rejections should trigger no-go")
        assert_equal(next_result["stageId"], "stage-2", "no-go stage id")
        print("  [PASS] test_three_rejections_yield_no_go")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_process_approval_timeout_records_reminder_once() -> None:
    temp_root = make_temp_root("stage-exec-reminder-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json("mark-stage-complete", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--deliverable-file", "STAGE-SUBAGENT-PLAN.json")
        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--transport", "text")
        overdue = timestamp_minutes_ago(11)
        update_approval_record(report_dir, "stage-0", sent_at=overdue, waiting_since=overdue)

        first = run_json("process-approval-timeout", "--report-dir", str(report_dir))
        assert_equal(first["status"], "reminder-recorded", "first reminder status")
        assert_equal(first["reminderCount"], 1, "first reminder count")

        second = run_json("process-approval-timeout", "--report-dir", str(report_dir))
        assert_equal(second["status"], "waiting", "duplicate reminder should not be recorded")
        approvals = json.loads(read_text(report_dir / "approval-records.json"))
        assert_equal(approvals["stage_0"]["reminder_count"], 1, "stored reminder count")
        stage_log = json.loads(read_text(report_dir / "stage-transition-log.json"))
        reminders = [entry for entry in stage_log if isinstance(entry, dict) and entry.get("event") == "approval-reminder"]
        assert_equal(len(reminders), 1, "single reminder event recorded")
        print("  [PASS] test_process_approval_timeout_records_reminder_once")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_process_approval_timeout_auto_continues_after_30_minutes() -> None:
    temp_root = make_temp_root("stage-exec-auto-continue-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json("mark-stage-complete", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--deliverable-file", "STAGE-SUBAGENT-PLAN.json")
        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--transport", "text")
        overdue = timestamp_minutes_ago(31)
        update_approval_record(report_dir, "stage-0", sent_at=overdue, waiting_since=overdue)

        timeout_result = run_json("process-approval-timeout", "--report-dir", str(report_dir))
        assert_equal(timeout_result["status"], "auto-continued", "auto continue status")
        approvals = json.loads(read_text(report_dir / "approval-records.json"))
        assert_equal(approvals["stage_0"]["user_response"], "auto-continue", "stored auto continue response")
        next_result = run_json("next", "--report-dir", str(report_dir))
        assert_equal(next_result["status"], "run-stage", "auto-continue should reopen execution")
        assert_equal(next_result["stageId"], "stage-1", "auto-continue next stage")
        print("  [PASS] test_process_approval_timeout_auto_continues_after_30_minutes")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_wait_response_resets_timeout_window() -> None:
    temp_root = make_temp_root("stage-exec-wait-reset-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json("mark-stage-complete", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--deliverable-file", "STAGE-SUBAGENT-PLAN.json")
        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--transport", "text")
        update_approval_record(report_dir, "stage-0", sent_at=timestamp_minutes_ago(45), waiting_since=timestamp_minutes_ago(45))
        run_json("record-approval-response", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--response", "wait")

        timeout_result = run_json("process-approval-timeout", "--report-dir", str(report_dir))
        assert_equal(timeout_result["status"], "waiting", "wait response should reset timeout window")
        approvals = json.loads(read_text(report_dir / "approval-records.json"))
        assert_equal(approvals["stage_0"]["reminder_count"], 0, "wait response resets reminder count")
        print("  [PASS] test_wait_response_resets_timeout_window")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_stage_cannot_enter_approval_when_artifact_validation_fails() -> None:
    temp_root = make_temp_root("stage-exec-artifact-validation-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json("mark-stage-complete", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--deliverable-file", "STAGE-SUBAGENT-PLAN.json")
        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--transport", "text")
        run_json("record-approval-response", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--response", "approved")
        write_text(report_dir / "PRODUCT-FINGERPRINT.json", "{}\n")
        write_text(report_dir / "SPEC.md", "# Spec\n")
        write_text(report_dir / "SPEC-CONSISTENCY-REVIEW.md", "# Review\n")
        write_text(report_dir / "PRODUCT-QUALITY-REVIEW.md", "\n")

        next_result = run_json("next", "--report-dir", str(report_dir))
        assert_equal(next_result["status"], "artifact-validation-failed", "artifact validation status")
        assert_equal(next_result["stageId"], "stage-2", "artifact validation stage")
        assert_equal("PRODUCT-QUALITY-REVIEW.md is empty" in " | ".join(next_result["artifactValidation"]["issues"]), True, "artifact validation issue")
        print("  [PASS] test_stage_cannot_enter_approval_when_artifact_validation_fails")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_stage_placeholder_only_sections_fail_artifact_validation() -> None:
    temp_root = make_temp_root("stage-exec-placeholder-validation-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json("mark-stage-complete", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--deliverable-file", "STAGE-SUBAGENT-PLAN.json")
        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--transport", "text")
        run_json("record-approval-response", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--response", "approved")
        write_text(report_dir / "PRODUCT-FINGERPRINT.json", "{}\n")
        write_text(report_dir / "SPEC.md", "# Spec\n")
        write_text(report_dir / "SPEC-CONSISTENCY-REVIEW.md", "# Review\n")
        quality_meta = executor_module.parse_role_doc(PROJECT_DIR / "roles" / "quality-assessor.md")
        quality_lines = ["# Product Quality Review", ""]
        for heading in quality_meta["minimumOutput"]:
            quality_lines.extend([f"## {heading}", "- mock", ""])
        write_text(report_dir / "PRODUCT-QUALITY-REVIEW.md", "\n".join(quality_lines))

        next_result = run_json("next", "--report-dir", str(report_dir))
        assert_equal(next_result["status"], "artifact-validation-failed", "placeholder-only quality review must fail")
        assert_equal("does not contain substantive content" in " | ".join(next_result["artifactValidation"]["issues"]), True, "placeholder validation issue")
        print("  [PASS] test_stage_placeholder_only_sections_fail_artifact_validation")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_invalid_executor_json_state_reports_clear_error() -> None:
    temp_root = make_temp_root("stage-exec-bad-json-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        write_text(report_dir / "approval-records.json", "{broken\n")
        proc = run_proc("next", "--report-dir", str(report_dir))
        assert_equal(proc.returncode == 0, False, "next should fail for invalid approval records")
        if "ERROR: invalid JSON in approval records" not in proc.stderr:
            raise AssertionError(f"stderr missing clear JSON error: {proc.stderr!r}")
        print("  [PASS] test_invalid_executor_json_state_reports_clear_error")
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
        assert_equal(payloads[0]["executionProfile"], "internal-fast", "dispatch execution profile")
        assert_equal(payloads[0]["executionPolicy"]["default_sender_backend"], "relay-only", "dispatch execution policy")
        assert_equal(payloads[0]["delivery"]["autoSendOnComplete"], True, "dispatch delivery auto-send")
        assert_equal(payloads[0]["artifactBaseDir"], str(report_dir.resolve()), "dispatch artifact base dir")
        assert_equal(payloads[0]["requiredArtifactPaths"], [], "dispatch required artifact paths")
        assert_equal(payloads[0]["upstreamOutputsVerified"], True, "dispatch upstream verification")
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


def test_serial_stage_dispatches_one_role_at_a_time() -> None:
    temp_root = make_temp_root("stage-exec-serial-role-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json("mark-stage-complete", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--deliverable-file", "STAGE-SUBAGENT-PLAN.json")
        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--transport", "text")
        run_json("record-approval-response", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--response", "approved")

        first_dispatch = run_json("dispatch", "--report-dir", str(report_dir))
        first_payloads = first_dispatch["dispatchPayloads"]
        assert_equal(len(first_payloads), 1, "serial stage should dispatch one role")
        assert_equal(first_payloads[0]["roleId"], "requirement-analyst", "requirement analyst dispatches first")
        assert_equal(first_payloads[0]["runMode"], "test", "default run mode is test")
        write_text(report_dir / "PRODUCT-FINGERPRINT.json", "{}\n")
        write_text(report_dir / "SPEC.md", "# Spec\n")

        second_dispatch = run_json("dispatch", "--report-dir", str(report_dir))
        second_payloads = second_dispatch["dispatchPayloads"]
        assert_equal(len(second_payloads), 1, "serial follow-up dispatch should still emit one role")
        assert_equal(second_payloads[0]["roleId"], "spec-consistency-validator", "validator dispatches second")
        assert_equal(
            "PRODUCT-FINGERPRINT.json" in second_payloads[0]["availableArtifacts"],
            True,
            "dispatch payload should list existing report artifacts",
        )
        print("  [PASS] test_serial_stage_dispatches_one_role_at_a_time")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_quality_assessor_dispatch_includes_required_artifact_paths() -> None:
    temp_root = make_temp_root("stage-exec-quality-paths-")
    try:
        report_dir = temp_root / "reports"
        run_json("init", "--report-dir", str(report_dir), "--flow", "skill")
        run_json("mark-stage-complete", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--deliverable-file", "STAGE-SUBAGENT-PLAN.json")
        run_json("record-approval-request", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--transport", "text")
        run_json("record-approval-response", "--report-dir", str(report_dir), "--stage-id", "stage-0", "--response", "approved")
        write_text(report_dir / "PRODUCT-FINGERPRINT.json", "{}\n")
        write_text(report_dir / "SPEC.md", "# Spec\n")
        write_text(report_dir / "SPEC-CONSISTENCY-REVIEW.md", "# Review\n")

        dispatch = run_json("dispatch", "--report-dir", str(report_dir))
        payload = dispatch["dispatchPayloads"][0]
        assert_equal(payload["roleId"], "quality-assessor", "stage two role id")
        expected = [
            str((report_dir / "PRODUCT-FINGERPRINT.json").resolve()),
            str((report_dir / "SPEC.md").resolve()),
            str((report_dir / "SPEC-CONSISTENCY-REVIEW.md").resolve()),
        ]
        assert_equal(payload["artifactBaseDir"], str(report_dir.resolve()), "quality artifact base dir")
        assert_equal(payload["requiredArtifactPaths"], expected, "quality required artifact paths")
        assert_equal(payload["upstreamOutputsVerified"], True, "quality upstream verification")
        print("  [PASS] test_quality_assessor_dispatch_includes_required_artifact_paths")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_parse_role_doc_minimum_output_structure() -> None:
    roles_dir = PROJECT_DIR / "roles"
    expectations = {
        "quality-assessor.md": {
            "minimumOutput": [
                "规格完整性",
                "可测试性",
                "主要风险",
                "测试设计建议",
                "结论与是否需要重新进入前一阶段",
            ],
            "aliases": {
                "结论与是否需要重新进入前一阶段": "结论",
            },
        },
        "test-designer.md": {
            "minimumOutput": [
                "测试策略",
                "测试用例集",
                "逻辑分支覆盖矩阵",
                "能力 × 维度覆盖矩阵（Flow A）",
                "测试数据方案（正常/异常/边界）",
                "测试夹具方案（如适用）",
                "风险与备注",
            ],
            "aliases": {
                "测试用例集": "测试用例",
                "风险与备注": "风险",
            },
        },
        "report-integrator.md": {
            "minimumOutput": [
                "测试概览",
                "各维度结果",
                "缺陷摘要",
                "未覆盖范围与残余风险",
                "发布建议",
            ],
            "aliases": {
                "未覆盖范围与残余风险": "残余风险",
            },
        },
    }
    for filename, expected in expectations.items():
        parsed = executor_module.parse_role_doc(roles_dir / filename)
        assert_equal(parsed["minimumOutput"], expected["minimumOutput"], f"{filename} minimumOutput")
        assert_equal(parsed["validateMarkdownStructure"], True, f"{filename} validateMarkdownStructure")
        assert_equal(parsed["minimumOutputAliases"], expected["aliases"], f"{filename} minimumOutputAliases")
    print("  [PASS] test_parse_role_doc_minimum_output_structure")


def test_parse_role_doc_takeover_policy() -> None:
    parsed = executor_module.parse_role_doc(PROJECT_DIR / "roles" / "skill-tester.md")
    assert_equal(parsed["mainAgentTakeoverPolicy"], {
        "enabled": True,
        "statuses": ["blocked-env", "blocked-policy", "stalled"],
        "patterns": [
            "blocked-no-openclaw",
            "blocked-live-telemetry",
            "blocked-no-real-exec",
            "blocked-no-adapter",
            "runtime unavailable",
            "gateway",
            "webreader",
            "mcp__",
            "environment limitation",
            "requires main-agent takeover",
        ],
        "onProcessFailure": False,
    }, "skill-tester takeover policy")
    print("  [PASS] test_parse_role_doc_takeover_policy")


def test_frontmatter_metadata_overrides_sections() -> None:
    temp_root = make_temp_root("stage-exec-role-frontmatter-")
    try:
        role_file = temp_root / "role.md"
        write_text(
            role_file,
            "\n".join(
                [
                    "---",
                    "name: temp-role",
                    "type: executor",
                    "description: temp",
                    "output_validation:",
                    '  - "markdown-headings"',
                    "minimum_output:",
                    '  - "Frontmatter A"',
                    '  - "Frontmatter B"',
                    "minimum_output_aliases:",
                    '  - "Frontmatter B => Alias B"',
                    "takeover_enabled: true",
                    "takeover_statuses:",
                    '  - "blocked"',
                    "takeover_patterns:",
                    '  - "gateway"',
                    "takeover_on_process_failure: false",
                    "---",
                    "",
                    "## 最低输出结构",
                    "```text",
                    "## Section Only",
                    "```",
                    "",
                    "## 输出结构校验",
                    "- markdown-headings",
                    "",
                    "## 输出结构校验别名",
                    "- Section Only => Section Alias",
                    "",
                    "## 主Agent接管策略",
                    "- enabled: false",
                    "- statuses: failed",
                    "- patterns: runtime unavailable",
                    "- onProcessFailure: true",
                    "",
                ]
            )
            + "\n",
        )
        parsed = executor_module.parse_role_doc(role_file)
        assert_equal(parsed["minimumOutput"], ["Frontmatter A", "Frontmatter B"], "frontmatter minimumOutput wins")
        assert_equal(parsed["minimumOutputAliases"], {"Frontmatter B": "Alias B"}, "frontmatter aliases win")
        assert_equal(parsed["mainAgentTakeoverPolicy"], {
            "enabled": True,
            "statuses": ["blocked"],
            "patterns": ["gateway"],
            "onProcessFailure": False,
        }, "frontmatter takeover policy wins")
        print("  [PASS] test_frontmatter_metadata_overrides_sections")
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
        test_rejected_response_requires_reason,
        test_three_rejections_yield_no_go,
        test_process_approval_timeout_records_reminder_once,
        test_process_approval_timeout_auto_continues_after_30_minutes,
        test_wait_response_resets_timeout_window,
        test_stage_cannot_enter_approval_when_artifact_validation_fails,
        test_stage_placeholder_only_sections_fail_artifact_validation,
        test_invalid_executor_json_state_reports_clear_error,
        test_approval_stage_must_match_current_gate,
        test_dispatch_payloads,
        test_bundle_dispatch,
        test_serial_stage_dispatches_one_role_at_a_time,
        test_quality_assessor_dispatch_includes_required_artifact_paths,
        test_parse_role_doc_minimum_output_structure,
        test_parse_role_doc_takeover_policy,
        test_frontmatter_metadata_overrides_sections,
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
