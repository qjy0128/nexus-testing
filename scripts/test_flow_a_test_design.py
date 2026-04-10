#!/usr/bin/env python3
"""Smoke test for Flow A stage-three surface-aware test design generation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from test_helpers import assert_contains, assert_equal, make_temp_root, read_text
from test_product_fingerprint import (
    build_companion_inventory_fixture,
    build_mixed_fixture,
    build_rule_dense_fixture,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
STAGE1 = PROJECT_DIR / "scripts" / "generate_flow_a_stage1.py"
STAGE3 = PROJECT_DIR / "scripts" / "generate_flow_a_test_design.py"


def test_surface_aware_test_design() -> None:
    temp_root = make_temp_root("flowa-design-")
    try:
        target = build_mixed_fixture(temp_root)
        reports_dir = temp_root / "reports"

        stage1 = subprocess.run(
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
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(stage1.returncode, 0, "stage1 generator exit code")

        stage3 = subprocess.run(
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
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(stage3.returncode, 0, "stage3 generator exit code")

        test_design_path = reports_dir / "TEST-DESIGN.md"
        plan_path = reports_dir / "SURFACE-EXECUTION-PLAN.json"
        case_plan_path = reports_dir / "CASE-EXECUTION-PLAN.json"
        assert test_design_path.exists(), "TEST-DESIGN.md missing"
        assert plan_path.exists(), "SURFACE-EXECUTION-PLAN.json missing"
        assert case_plan_path.exists(), "CASE-EXECUTION-PLAN.json missing"

        test_design = read_text(test_design_path)
        assert_contains(test_design, "Surface Inventory", "surface inventory section")
        assert_contains(test_design, "Skill Entry", "skill surface section")
        assert_contains(test_design, "Plugin Extension", "plugin surface section")
        assert_contains(test_design, "CLI Entry", "cli surface section")
        assert_contains(test_design, "MCP Surface", "mcp surface section")
        assert_contains(test_design, "probe-only evidence", "probe-only requirement")

        plan = json.loads(read_text(plan_path))
        assert_equal(plan.get("parallelRoles"), ["skill-tester", "security-tester"], "parallel roles")
        kinds = [surface.get("kind") for surface in plan.get("surfaces", [])]
        for expected in ("skill", "bin", "openclaw-extension", "plugin-manifest", "package", "mcp"):
            assert expected in kinds, f"missing surface kind {expected}: {kinds}"
        by_kind = {str(surface.get("kind")): surface for surface in plan.get("surfaces", [])}
        assert_equal(by_kind["bin"].get("command"), "./dist/mcp-server.js", "bin command metadata")
        assert_equal(by_kind["plugin-manifest"].get("path"), "openclaw.plugin.json", "plugin manifest path metadata")
        assert_equal(by_kind["package"].get("path"), "package.json", "package path metadata")
        assert_equal(by_kind["mcp"].get("command"), "./dist/mcp-server.js", "mcp command metadata")
        case_plan = json.loads(read_text(case_plan_path))
        assert_equal(case_plan.get("totalCaseCount"), plan.get("totalCaseCount"), "case plan count sync")
        fingerprint = json.loads(read_text(reports_dir / "PRODUCT-FINGERPRINT.json"))
        assert_equal(plan.get("resolvedRootPath"), fingerprint.get("resolvedRootPath"), "plan root path metadata")
        assert_equal(plan.get("targetSkillPath"), fingerprint.get("targetSkillPath"), "plan target skill path metadata")
        assert_equal(case_plan.get("resolvedRootPath"), fingerprint.get("resolvedRootPath"), "case plan root path metadata")
        assert case_plan.get("cases"), "case execution plan should include cases"
        first_case = case_plan.get("cases", [])[0]
        assert "executionHints" in first_case, "case execution hints missing"
        host_takeover = first_case["executionHints"].get("hostTakeover", {})
        assert_equal(isinstance(host_takeover, dict), True, "host takeover hints present")
        assert_equal(host_takeover.get("enabled"), True, "skill case enables host takeover")
        print("  [PASS] test_surface_aware_test_design")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_data_driven_rule_expansion_and_language_switch() -> None:
    temp_root = make_temp_root("flowa-design-rule-dense-")
    try:
        target = build_rule_dense_fixture(temp_root)
        reports_dir = temp_root / "reports"

        stage1 = subprocess.run(
            [
                sys.executable,
                str(STAGE1),
                "--target",
                str(target),
                "--output-dir",
                str(reports_dir),
            ],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(stage1.returncode, 0, "stage1 dense generator exit code")

        stage3 = subprocess.run(
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
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(stage3.returncode, 0, "stage3 dense generator exit code")

        test_design = read_text(reports_dir / "TEST-DESIGN.md")
        plan = json.loads(read_text(reports_dir / "SURFACE-EXECUTION-PLAN.json"))
        case_plan = json.loads(read_text(reports_dir / "CASE-EXECUTION-PLAN.json"))
        assert_contains(test_design, "## 测试策略", "default language switched to Chinese")
        assert_contains(test_design, "规则 `prompt-injection` 检出", "rule-positive expansion")
        assert_contains(test_design, "规则 `prompt-injection` 不误报", "rule false-positive expansion")
        assert_contains(test_design, "决策路径 `DENY`", "decision-path expansion")
        assert_contains(test_design, "检查项 `runtime-hook-installed`", "check expansion")
        total_case_count = int(plan.get("totalCaseCount", 0))
        assert total_case_count >= 16, f"dense fixture should expand to >=16 cases, got {total_case_count}"
        assert_equal(case_plan.get("totalCaseCount"), total_case_count, "dense case plan count sync")
        print("  [PASS] test_data_driven_rule_expansion_and_language_switch")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_companion_inventory_expansion() -> None:
    temp_root = make_temp_root("flowa-design-companion-")
    try:
        target = build_companion_inventory_fixture(temp_root)
        reports_dir = temp_root / "reports"

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
        ):
            proc = subprocess.run(
                command,
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert_equal(proc.returncode, 0, f"companion design exit code: {' '.join(command[1:3])}")

        test_design = read_text(reports_dir / "TEST-DESIGN.md")
        plan = json.loads(read_text(reports_dir / "SURFACE-EXECUTION-PLAN.json"))
        case_plan = json.loads(read_text(reports_dir / "CASE-EXECUTION-PLAN.json"))
        assert_contains(test_design, "rule `RULE_01` detection", "companion scan rule expansion")
        assert_contains(test_design, "decision path `Invalid URL -> DENY`", "companion decision expansion")
        assert_contains(test_design, "check `Patrol Check 1`", "companion patrol check expansion")
        total_case_count = int(plan.get("totalCaseCount", 0))
        assert total_case_count >= 60, f"companion fixture should expand to >=60 cases, got {total_case_count}"
        assert_equal(case_plan.get("totalCaseCount"), total_case_count, "companion case plan count sync")
        print("  [PASS] test_companion_inventory_expansion")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Flow A Stage-Three Smoke Tests")
    print("=" * 40)
    try:
        test_surface_aware_test_design()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_surface_aware_test_design: {exc}")
        failed += 1
    try:
        test_data_driven_rule_expansion_and_language_switch()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_data_driven_rule_expansion_and_language_switch: {exc}")
        failed += 1
    try:
        test_companion_inventory_expansion()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_companion_inventory_expansion: {exc}")
        failed += 1
    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
