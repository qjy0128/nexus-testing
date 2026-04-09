#!/usr/bin/env python3
"""Smoke tests for stage subagent plan generation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from test_helpers import assert_equal, make_temp_root, parse_kv_output, read_text

PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "scripts" / "generate_stage_subagent_plan.py"


def test_flow_a_plan() -> None:
    temp_root = make_temp_root("stage-plan-a-")
    try:
        output_path = temp_root / "STAGE-SUBAGENT-PLAN.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--flow", "skill", "--output-file", str(output_path)],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(proc.returncode, 0, "flow A plan exit code")
        parsed = parse_kv_output(proc.stdout)
        assert_equal(parsed.get("FLOW_ID"), "A", "flow A id")
        assert_equal(parsed.get("MODE"), "standard", "flow A mode")
        assert_equal(parsed.get("STAGE_COUNT"), "8", "flow A stage count")
        plan = json.loads(read_text(output_path))
        assert_equal(plan["stages"][0]["roles"][0]["id"], "environment-checker", "stage zero role")
        assert_equal(plan["stages"][1]["roles"][1]["id"], "spec-consistency-validator", "stage one validator role")
        assert_equal(plan["stages"][5]["dispatchMode"], "parallel", "stage five dispatch mode")
        print("  [PASS] test_flow_a_plan")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_flow_b_b_mode_plan() -> None:
    temp_root = make_temp_root("stage-plan-b-")
    try:
        output_path = temp_root / "STAGE-SUBAGENT-PLAN.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--flow", "web-api", "--mode", "b", "--output-file", str(output_path)],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(proc.returncode, 0, "flow B mode plan exit code")
        parsed = parse_kv_output(proc.stdout)
        assert_equal(parsed.get("FLOW_ID"), "B", "flow B id")
        assert_equal(parsed.get("MODE"), "b-mode", "flow B mode")
        assert_equal(parsed.get("STAGE_COUNT"), "11", "flow B mode stage count")
        plan = json.loads(read_text(output_path))
        assert_equal(plan["stages"][3]["roles"][0]["id"], "experience-tester-a", "b-stage-3 role a")
        assert_equal(plan["stages"][3]["roles"][1]["id"], "experience-tester-b", "b-stage-3 role b")
        assert_equal(plan["stages"][8]["postStageRoles"][0]["id"], "evidence-collector", "b-stage-8 evidence collector")
        assert_equal(plan["stages"][8]["postStageDeliverables"][0], "DEFECTS/evidence-collection.md", "b-stage-8 evidence deliverable")
        print("  [PASS] test_flow_b_b_mode_plan")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Stage Subagent Plan Smoke Tests")
    print("=" * 40)
    for test in (test_flow_a_plan, test_flow_b_b_mode_plan):
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
