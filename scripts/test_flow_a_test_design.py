#!/usr/bin/env python3
"""Smoke test for Flow A stage-three surface-aware test design generation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from test_helpers import assert_contains, assert_equal, make_temp_root, read_text
from test_product_fingerprint import build_mixed_fixture

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
        assert test_design_path.exists(), "TEST-DESIGN.md missing"
        assert plan_path.exists(), "SURFACE-EXECUTION-PLAN.json missing"

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
        print("  [PASS] test_surface_aware_test_design")
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
    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
