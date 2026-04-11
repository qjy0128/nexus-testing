#!/usr/bin/env python3
"""Smoke test for report-artifact relay into workspace `files/`."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import shutil
import subprocess
import sys
import time
from pathlib import Path

from test_helpers import assert_equal, parse_kv_output, read_text, write_text

PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "scripts" / "prepare_report_delivery.py"


def test_prepare_report_delivery() -> None:
    stamp = f"2099-01-01-delivery-test-{time.time_ns()}"
    source = PROJECT_DIR / "memory" / "nexus-reports" / stamp / "SPEC.md"
    target_dir = PROJECT_DIR / "files" / "nexus-reports" / stamp
    try:
        write_text(source, "# Demo report\n")
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--report-file",
                str(source),
            ],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(proc.returncode, 0, "prepare_report_delivery exit code")
        output = parse_kv_output(proc.stdout)
        assert_equal(
            output.get("SENDABLE_PATH"),
            f"files/nexus-reports/{stamp}/SPEC.md",
            "sendable relative path",
        )
        mirrored = Path(output["SENDABLE_ABS"])
        assert mirrored.exists(), f"mirrored file missing: {mirrored}"
        assert_equal(read_text(mirrored), "# Demo report\n", "mirrored file content")
        print("  [PASS] test_prepare_report_delivery")
    finally:
        shutil.rmtree(source.parent, ignore_errors=True)
        shutil.rmtree(target_dir, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Report Delivery Smoke Tests")
    print("=" * 40)
    try:
        test_prepare_report_delivery()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_prepare_report_delivery: {exc}")
        failed += 1
    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
