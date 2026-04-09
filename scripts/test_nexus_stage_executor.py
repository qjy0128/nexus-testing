#!/usr/bin/env python3
"""Smoke tests for nexus_stage_executor.py."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
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
        "statuses": ["blocked"],
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
        test_approval_stage_must_match_current_gate,
        test_dispatch_payloads,
        test_bundle_dispatch,
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
