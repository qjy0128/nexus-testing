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


def build_skill_results(plan: dict[str, object]) -> str:
    lines = ["# skill-results", ""]
    for surface in plan.get("surfaces", []):
        kind = str(surface.get("kind"))
        status = "passed"
        notes = f"covered {surface.get('surfaceId')}"
        if kind == "openclaw-extension":
            notes = f"covered {surface.get('surfaceId')}; registered-hooks=2; behavior-verified=true"
        if kind == "mcp":
            notes = (
                f"covered {surface.get('surfaceId')}; protocol-version=2025-03-26; "
                "tools=1; tool-call=called:ping; protocol-verified=true"
            )
        lines.extend(
            [
                f"### {surface.get('surfaceId')} - {surface.get('kind')} (`{surface.get('identifier')}`)",
                f"- surface-id: `{surface.get('surfaceId')}`",
                f"- execution-level: `{surface.get('minimumMode')}`",
                f"- status: `{status}`",
                f"- evidence: `workspace/artifacts/{surface.get('surfaceId')}.json`",
                f"- notes: {notes}",
                "",
            ]
        )
    return "\n".join(lines)


def test_surface_execution_workflow() -> None:
    temp_root = make_temp_root("flowa-exec-")
    try:
        target = build_mixed_fixture(temp_root)
        reports_dir = temp_root / "reports"

        for command in (
            [
                sys.executable,
                str(STAGE1),
                "--target",
                str(target),
                "--output-dir",
                str(reports_dir),
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
            ],
            [
                sys.executable,
                str(STAGE5),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--output-dir",
                str(reports_dir),
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

        worklist_path = reports_dir / "TEST-EXECUTION" / "SKILL-SURFACE-WORKLIST.md"
        coverage_path = reports_dir / "TEST-EXECUTION" / "SURFACE-COVERAGE.json"
        assert worklist_path.exists(), "SKILL-SURFACE-WORKLIST.md missing"
        assert coverage_path.exists(), "SURFACE-COVERAGE.json missing"

        worklist_text = read_text(worklist_path)
        assert_contains(worklist_text, "Ordered Surface Worklist", "worklist section")
        assert_contains(worklist_text, "SURFACE-01", "surface id listed")
        assert_contains(worklist_text, "- execution-target:", "execution target recorded")

        coverage = json.loads(read_text(coverage_path))
        assert_equal(coverage.get("parallelRoles"), ["skill-tester", "security-tester"], "coverage roles")

        plan = json.loads(read_text(reports_dir / "SURFACE-EXECUTION-PLAN.json"))
        skill_results_path = reports_dir / "TEST-EXECUTION" / "skill-results.md"
        write_text(skill_results_path, build_skill_results(plan))

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

        for command in (
            [
                sys.executable,
                str(STAGE1),
                "--target",
                str(target),
                "--output-dir",
                str(reports_dir),
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
            ],
            [
                sys.executable,
                str(STAGE5),
                "--surface-plan",
                str(reports_dir / "SURFACE-EXECUTION-PLAN.json"),
                "--output-dir",
                str(reports_dir),
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
        lines = ["# skill-results", ""]
        for surface in plan.get("surfaces", []):
            kind = str(surface.get("kind"))
            notes = f"covered {surface.get('surfaceId')}"
            if kind == "openclaw-extension":
                notes = f"covered {surface.get('surfaceId')}; behavior-verified=true"
            if kind == "mcp":
                notes = f"covered {surface.get('surfaceId')}; protocol-verified=true"
            lines.extend(
                [
                    f"### {surface.get('surfaceId')} - {surface.get('kind')} (`{surface.get('identifier')}`)",
                    f"- surface-id: `{surface.get('surfaceId')}`",
                    f"- execution-level: `{surface.get('minimumMode')}`",
                    "- status: `passed`",
                    f"- evidence: `workspace/artifacts/{surface.get('surfaceId')}.json`",
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
        assert_contains(
            validator.stdout,
            "registered-hooks evidence notes",
            "extension evidence-note rejection",
        )
        assert_contains(
            validator.stdout,
            "protocol-version and tools evidence notes",
            "mcp evidence-note rejection",
        )
        print("  [PASS] test_surface_execution_validator_rejects_weak_verified_notes")
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
    try:
        test_surface_execution_workflow()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_surface_execution_workflow: {exc}")
        failed += 1
    try:
        test_surface_execution_validator_rejects_weak_verified_notes()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_surface_execution_validator_rejects_weak_verified_notes: {exc}")
        failed += 1
    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
