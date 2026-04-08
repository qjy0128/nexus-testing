#!/usr/bin/env python3
"""Smoke test for Flow A stage-five surface worklist and result validation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from test_helpers import assert_contains, assert_equal, make_temp_root, read_text, write_text
from test_product_fingerprint import build_mixed_fixture

PROJECT_DIR = Path(__file__).resolve().parents[1]
STAGE1 = PROJECT_DIR / "scripts" / "generate_flow_a_stage1.py"
STAGE3 = PROJECT_DIR / "scripts" / "generate_flow_a_test_design.py"
STAGE5 = PROJECT_DIR / "scripts" / "generate_flow_a_skill_execution.py"
VALIDATOR = PROJECT_DIR / "scripts" / "validate_flow_a_skill_results.py"


def build_full_skill_results(plan: dict[str, object]) -> str:
    lines = ["# skill-results", ""]
    for surface in plan.get("surfaces", []):
        kind = str(surface.get("kind"))
        case_ids = [str(item) for item in surface.get("testCaseIds", []) if str(item).strip()]
        notes = f"covered {surface.get('surfaceId')}; case-coverage={len(case_ids)}/{len(case_ids)}"
        if kind == "openclaw-extension":
            notes = (
                f"covered {surface.get('surfaceId')}; registered-hooks=2; behavior-verified=true; "
                "runtime-verified=true; runtime-transport=openclaw-subagent; "
                f"case-coverage={len(case_ids)}/{len(case_ids)}"
            )
        if kind == "mcp":
            notes = (
                f"covered {surface.get('surfaceId')}; protocol-version=2025-03-26; "
                f"tools=1; tool-call=called:ping; protocol-verified=true; case-coverage={len(case_ids)}/{len(case_ids)}"
            )
        lines.extend(
            [
                f"### {surface.get('surfaceId')} - {surface.get('kind')} (`{surface.get('identifier')}`)",
                f"- surface-id: `{surface.get('surfaceId')}`",
                f"- execution-level: `{surface.get('minimumMode')}`",
                "- status: `passed`",
                f"- evidence: `workspace/artifacts/{surface.get('surfaceId')}.json`",
                f"- executed-case-ids: `{', '.join(case_ids)}`",
                f"- notes: {notes}",
                "",
            ]
        )
    return "\n".join(lines)


def write_full_coverage(plan: dict[str, object], coverage_path: Path) -> None:
    coverage = json.loads(read_text(coverage_path))
    for surface in coverage.get("surfaces", []):
        required_case_ids = [str(item) for item in surface.get("requiredCaseIds", []) if str(item).strip()]
        case_results = []
        for case_id in required_case_ids:
            case_results.append(
                {
                    "caseId": case_id,
                    "status": "passed",
                    "evidence": [f"workspace/artifacts/{surface.get('surfaceId')}-{case_id}.json"],
                }
            )
        surface["executedCaseIds"] = required_case_ids
        surface["executedCaseCount"] = len(required_case_ids)
        surface["requiredCaseCount"] = len(required_case_ids)
        surface["caseResults"] = case_results
        surface["status"] = "passed"
        surface["executionLevel"] = surface.get("minimumMode")
        surface["evidence"] = [f"workspace/artifacts/{surface.get('surfaceId')}.json"]
        surface["notes"] = f"case-coverage={len(required_case_ids)}/{len(required_case_ids)}"
    write_text(coverage_path, json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")


def run_stage_five_setup(target: Path, reports_dir: Path) -> tuple[dict[str, object], Path]:
    for command in (
        [
            sys.executable,
            str(STAGE1),
            "--target",
            str(target),
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
    ):
        proc = subprocess.run(
            command,
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(proc.returncode, 0, f"command exit code: {' '.join(command[1:3])}")
    plan = json.loads(read_text(reports_dir / "SURFACE-EXECUTION-PLAN.json"))
    coverage_path = reports_dir / "TEST-EXECUTION" / "SURFACE-COVERAGE.json"
    return plan, coverage_path


def test_surface_execution_workflow() -> None:
    temp_root = make_temp_root("flowa-exec-")
    try:
        target = build_mixed_fixture(temp_root)
        reports_dir = temp_root / "reports"
        plan, coverage_path = run_stage_five_setup(target, reports_dir)

        worklist_path = reports_dir / "TEST-EXECUTION" / "SKILL-SURFACE-WORKLIST.md"
        assert worklist_path.exists(), "SKILL-SURFACE-WORKLIST.md missing"
        assert coverage_path.exists(), "SURFACE-COVERAGE.json missing"

        worklist_text = read_text(worklist_path)
        assert_contains(worklist_text, "Ordered Surface Worklist", "worklist section")
        assert_contains(worklist_text, "SURFACE-01", "surface id listed")
        assert_contains(worklist_text, "- execution-target:", "execution target recorded")
        assert_contains(worklist_text, "executed-case-ids", "case execution template recorded")

        coverage = json.loads(read_text(coverage_path))
        assert_equal(coverage.get("parallelRoles"), ["skill-tester", "security-tester"], "coverage roles")
        first_surface = coverage.get("surfaces", [])[0]
        assert_equal(first_surface.get("executedCaseCount"), 0, "initial executed case count")
        assert_equal(first_surface.get("caseResults", [])[0].get("status"), "pending", "initial case pending")

        write_full_coverage(plan, coverage_path)
        skill_results_path = reports_dir / "TEST-EXECUTION" / "skill-results.md"
        write_text(skill_results_path, build_full_skill_results(plan))

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
        assert_equal(validator.returncode, 0, "surface result validator exit code")
        assert_contains(validator.stdout, "STATUS=passed", "surface result validator status")
        print("  [PASS] test_surface_execution_workflow")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_surface_execution_validator_rejects_weak_verified_notes() -> None:
    temp_root = make_temp_root("flowa-exec-invalid-")
    try:
        target = build_mixed_fixture(temp_root)
        reports_dir = temp_root / "reports"
        plan, coverage_path = run_stage_five_setup(target, reports_dir)
        write_full_coverage(plan, coverage_path)

        lines = ["# skill-results", ""]
        for surface in plan.get("surfaces", []):
            kind = str(surface.get("kind"))
            case_ids = [str(item) for item in surface.get("testCaseIds", []) if str(item).strip()]
            notes = f"covered {surface.get('surfaceId')}; case-coverage={len(case_ids)}/{len(case_ids)}"
            if kind == "openclaw-extension":
                notes = f"covered {surface.get('surfaceId')}; behavior-verified=true; case-coverage={len(case_ids)}/{len(case_ids)}"
            if kind == "mcp":
                notes = f"covered {surface.get('surfaceId')}; protocol-verified=true; case-coverage={len(case_ids)}/{len(case_ids)}"
            lines.extend(
                [
                    f"### {surface.get('surfaceId')} - {surface.get('kind')} (`{surface.get('identifier')}`)",
                    f"- surface-id: `{surface.get('surfaceId')}`",
                    f"- execution-level: `{surface.get('minimumMode')}`",
                    "- status: `passed`",
                    f"- evidence: `workspace/artifacts/{surface.get('surfaceId')}.json`",
                    f"- executed-case-ids: `{', '.join(case_ids)}`",
                    f"- notes: {notes}",
                    "",
                ]
            )

        skill_results_path = reports_dir / "TEST-EXECUTION" / "skill-results.md"
        write_text(skill_results_path, "\n".join(lines))
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
        assert_equal(validator.returncode, 1, "weak verified notes validator exit code")
        assert_contains(validator.stdout, "registered-hooks evidence notes", "extension evidence-note rejection")
        assert_contains(validator.stdout, "protocol-version and tools evidence notes", "mcp evidence-note rejection")
        print("  [PASS] test_surface_execution_validator_rejects_weak_verified_notes")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_surface_execution_validator_rejects_live_extension_without_runtime_notes() -> None:
    temp_root = make_temp_root("flowa-exec-live-extension-invalid-")
    try:
        target = build_mixed_fixture(temp_root)
        reports_dir = temp_root / "reports"
        plan, coverage_path = run_stage_five_setup(target, reports_dir)
        write_full_coverage(plan, coverage_path)

        lines = ["# skill-results", ""]
        for surface in plan.get("surfaces", []):
            kind = str(surface.get("kind"))
            execution_level = str(surface.get("minimumMode"))
            case_ids = [str(item) for item in surface.get("testCaseIds", []) if str(item).strip()]
            notes = f"covered {surface.get('surfaceId')}; case-coverage={len(case_ids)}/{len(case_ids)}"
            if kind == "openclaw-extension":
                execution_level = "live"
                notes = f"covered {surface.get('surfaceId')}; registered-hooks=2; behavior-verified=true; case-coverage={len(case_ids)}/{len(case_ids)}"
            if kind == "mcp":
                notes = (
                    f"covered {surface.get('surfaceId')}; protocol-version=2025-03-26; "
                    f"tools=1; tool-call=called:ping; protocol-verified=true; case-coverage={len(case_ids)}/{len(case_ids)}"
                )
            lines.extend(
                [
                    f"### {surface.get('surfaceId')} - {surface.get('kind')} (`{surface.get('identifier')}`)",
                    f"- surface-id: `{surface.get('surfaceId')}`",
                    f"- execution-level: `{execution_level}`",
                    "- status: `passed`",
                    f"- evidence: `workspace/artifacts/{surface.get('surfaceId')}.json`",
                    f"- executed-case-ids: `{', '.join(case_ids)}`",
                    f"- notes: {notes}",
                    "",
                ]
            )

        skill_results_path = reports_dir / "TEST-EXECUTION" / "skill-results.md"
        write_text(skill_results_path, "\n".join(lines))
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
        assert_equal(validator.returncode, 1, "live extension note validator exit code")
        assert_contains(validator.stdout, "runtime-verified=true notes", "live extension runtime note rejection")
        assert_contains(validator.stdout, "runtime-transport notes", "live extension runtime transport rejection")
        print("  [PASS] test_surface_execution_validator_rejects_live_extension_without_runtime_notes")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_surface_execution_validator_rejects_plan_drift_and_pending_cases() -> None:
    temp_root = make_temp_root("flowa-exec-plan-drift-")
    try:
        target = build_mixed_fixture(temp_root)
        reports_dir = temp_root / "reports"
        plan, coverage_path = run_stage_five_setup(target, reports_dir)

        lines = ["# skill-results", ""]
        first_surface = plan.get("surfaces", [])[0]
        required_case_ids = [str(item) for item in first_surface.get("testCaseIds", []) if str(item).strip()]
        lines.extend(
            [
                f"### {first_surface.get('surfaceId')} - {first_surface.get('kind')} (`{first_surface.get('identifier')}`)",
                f"- surface-id: `{first_surface.get('surfaceId')}`",
                f"- execution-level: `{first_surface.get('minimumMode')}`",
                "- status: `passed`",
                f"- evidence: `workspace/artifacts/{first_surface.get('surfaceId')}.json`",
                f"- executed-case-ids: `{required_case_ids[0]}`",
                "- notes: case-coverage=1/3; surface-smoke-only=true",
                "",
                "### SURFACE-99 - cli (`manual-added`)",
                "- surface-id: `SURFACE-99`",
                "- execution-level: `shim-live`",
                "- status: `passed`",
                "- evidence: `workspace/artifacts/SURFACE-99.json`",
                "- executed-case-ids: `TC-999`",
                "- notes: case-coverage=1/1",
                "",
            ]
        )
        skill_results_path = reports_dir / "TEST-EXECUTION" / "skill-results.md"
        write_text(skill_results_path, "\n".join(lines))

        validator = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--skill-results",
                str(skill_results_path),
                "--surface-coverage",
                str(coverage_path),
            ],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(validator.returncode, 1, "plan drift validator exit code")
        assert_contains(validator.stdout, "undeclared surface SURFACE-99", "extra surface rejection")
        assert_contains(validator.stdout, "is still pending in SURFACE-COVERAGE.json", "pending coverage rejection")
        print("  [PASS] test_surface_execution_validator_rejects_plan_drift_and_pending_cases")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_surface_execution_validator_allows_none_executed_case_ids() -> None:
    temp_root = make_temp_root("flowa-exec-none-case-ids-")
    try:
        target = build_mixed_fixture(temp_root)
        reports_dir = temp_root / "reports"
        plan, coverage_path = run_stage_five_setup(target, reports_dir)
        write_full_coverage(plan, coverage_path)

        coverage = json.loads(read_text(coverage_path))
        extension_surface = next(
            surface for surface in coverage.get("surfaces", []) if str(surface.get("kind")) == "openclaw-extension"
        )
        required_case_ids = [str(item) for item in extension_surface.get("requiredCaseIds", []) if str(item).strip()]
        extension_surface["status"] = "blocked"
        extension_surface["executionLevel"] = "live"
        extension_surface["executedCaseIds"] = []
        extension_surface["executedCaseCount"] = 0
        extension_surface["caseResults"] = [
            {"caseId": case_id, "status": "pending", "evidence": []} for case_id in required_case_ids
        ]
        extension_surface["evidence"] = ["workspace/artifacts/SURFACE-03-blocked.json"]
        extension_surface["notes"] = "invoke-status=blocked-no-openclaw; runtime-probed=false; case-coverage=0/3"
        write_text(coverage_path, json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")

        lines = ["# skill-results", ""]
        for surface in plan.get("surfaces", []):
            surface_id = str(surface.get("surfaceId"))
            kind = str(surface.get("kind"))
            case_ids = [str(item) for item in surface.get("testCaseIds", []) if str(item).strip()]
            status = "passed"
            execution_level = str(surface.get("minimumMode"))
            evidence = f"workspace/artifacts/{surface_id}.json"
            executed_case_ids = ", ".join(case_ids)
            notes = f"covered {surface_id}; case-coverage={len(case_ids)}/{len(case_ids)}"
            if kind == "openclaw-extension":
                status = "blocked"
                execution_level = "live"
                evidence = "workspace/artifacts/SURFACE-03-blocked.json"
                executed_case_ids = "(none)"
                notes = "invoke-status=blocked-no-openclaw; runtime-probed=false; case-coverage=0/3"
            elif kind == "mcp":
                notes = (
                    f"covered {surface_id}; protocol-version=2025-03-26; "
                    f"tools=1; tool-call=called:ping; protocol-verified=true; case-coverage={len(case_ids)}/{len(case_ids)}"
                )
            lines.extend(
                [
                    f"### {surface_id} - {kind} (`{surface.get('identifier')}`)",
                    f"- surface-id: `{surface_id}`",
                    f"- execution-level: `{execution_level}`",
                    f"- status: `{status}`",
                    f"- evidence: `{evidence}`",
                    f"- executed-case-ids: `{executed_case_ids}`",
                    f"- notes: {notes}",
                    "",
                ]
            )

        skill_results_path = reports_dir / "TEST-EXECUTION" / "skill-results.md"
        write_text(skill_results_path, "\n".join(lines))

        validator = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--skill-results",
                str(skill_results_path),
                "--surface-coverage",
                str(coverage_path),
            ],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(validator.returncode, 0, "none executed-case-ids validator exit code")
        assert_contains(validator.stdout, "STATUS=passed", "none executed-case-ids validator status")
        print("  [PASS] test_surface_execution_validator_allows_none_executed_case_ids")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Flow A Stage-Five Smoke Tests")
    print("=" * 40)
    for test in (
        test_surface_execution_workflow,
        test_surface_execution_validator_rejects_weak_verified_notes,
        test_surface_execution_validator_rejects_live_extension_without_runtime_notes,
        test_surface_execution_validator_rejects_plan_drift_and_pending_cases,
        test_surface_execution_validator_allows_none_executed_case_ids,
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
