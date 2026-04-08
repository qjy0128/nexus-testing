#!/usr/bin/env python3
"""Smoke test for Flow A stage-one artifact generation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from test_helpers import assert_contains, assert_equal, make_temp_root, read_text
from test_product_fingerprint import build_mixed_fixture

PROJECT_DIR = Path(__file__).resolve().parents[1]
GENERATOR = PROJECT_DIR / "scripts" / "generate_flow_a_stage1.py"


def test_stage1_generation() -> None:
    temp_root = make_temp_root("flowa-stage1-")
    try:
        target = build_mixed_fixture(temp_root) / "skills" / "agentguard"
        output_dir = temp_root / "reports"
        proc = subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                "--target",
                str(target),
                "--output-dir",
                str(output_dir),
                "--language",
                "en",
            ],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(proc.returncode, 0, "stage1 generator exit code")

        fingerprint_path = output_dir / "PRODUCT-FINGERPRINT.json"
        spec_path = output_dir / "SPEC.md"
        review_path = output_dir / "SPEC-CONSISTENCY-REVIEW.md"
        assert fingerprint_path.exists(), "PRODUCT-FINGERPRINT.json missing"
        assert spec_path.exists(), "SPEC.md missing"
        assert review_path.exists(), "SPEC-CONSISTENCY-REVIEW.md missing"

        fingerprint = json.loads(read_text(fingerprint_path))
        assert "skill" in fingerprint.get("productType", []), "missing skill product type"
        assert "plugin" in fingerprint.get("productType", []), "missing plugin product type"
        assert_equal(fingerprint.get("targetSkillPath"), "skills/agentguard", "target skill path")
        assert_equal(fingerprint.get("packageName"), "@example/agentguard-lite", "package name from repo root")

        spec_text = read_text(spec_path)
        assert_contains(spec_text, "Real Entry Surfaces", "spec real entry section")
        assert_contains(spec_text, "agentguard-lite", "spec package/bin mention")
        assert_contains(spec_text, "scan", "spec capability mention")

        review_text = read_text(review_path)
        assert_contains(review_text, "`passed`", "consistency review passed")
        assert_contains(review_text, "Allow Flow A to continue to stage two.", "gate decision")
        print("  [PASS] test_stage1_generation")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Flow A Stage-One Smoke Tests")
    print("=" * 40)
    try:
        test_stage1_generation()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_stage1_generation: {exc}")
        failed += 1
    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
