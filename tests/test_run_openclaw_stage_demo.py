#!/usr/bin/env python3
"""Smoke tests for run_openclaw_stage_demo.py."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import json
import shutil
import subprocess
import sys
from pathlib import Path

from test_helpers import assert_equal, make_temp_root, write_text

PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "scripts" / "run_openclaw_stage_demo.py"


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


def write_mock_openclaw_config(path: Path) -> None:
    config = {
        "name": "openclaw-role-runtime",
        "default": {
            "command": [
                sys.executable,
                str(PROJECT_DIR / "scripts" / "nexus_openclaw_role_runtime.py"),
                "--payload-file",
                "{payload_file}",
                "--prompt-file",
                "{prompt_file}",
                "--openclaw-command",
                sys.executable,
                "--openclaw-args",
                str(PROJECT_DIR / "scripts" / "fixtures" / "mock_openclaw_cli.py"),
                "--skill-path",
                ".",
                "--channel",
                "telegram",
            ],
            "cwd": "{workspace_root}",
            "timeoutSeconds": 120,
        },
    }
    write_text(path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")


def test_start_and_approve_flow() -> None:
    temp_root = make_temp_root("openclaw-demo-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime-config.openclaw.mock.json"
        write_mock_openclaw_config(config_path)

        started = run_json(
            "start",
            "--report-dir",
            str(report_dir),
            "--runtime-config",
            str(config_path),
        )
        assert_equal(started["summary"]["status"], "await-approval", "start status")
        assert_equal(started["summary"]["runtimeResult"]["gateAction"]["stageId"], "stage-0", "first gate")

        approved = run_json(
            "approve",
            "--report-dir",
            str(report_dir),
            "--stage-id",
            "stage-0",
            "--runtime-config",
            str(config_path),
            "--continue-run",
        )
        assert_equal(approved["summary"]["status"], "await-approval", "second status")
        assert_equal(approved["summary"]["runtimeResult"]["gateAction"]["stageId"], "stage-2", "second gate")
        print("  [PASS] test_start_and_approve_flow")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_start_rejects_flow_mode_mismatch() -> None:
    temp_root = make_temp_root("openclaw-demo-mismatch-")
    try:
        report_dir = temp_root / "reports"
        config_path = temp_root / "runtime-config.openclaw.mock.json"
        write_mock_openclaw_config(config_path)

        run_json(
            "start",
            "--report-dir",
            str(report_dir),
            "--flow",
            "skill",
            "--runtime-config",
            str(config_path),
        )
        proc = run_proc(
            "start",
            "--report-dir",
            str(report_dir),
            "--flow",
            "web-api",
            "--runtime-config",
            str(config_path),
        )
        assert_equal(proc.returncode == 0, False, "flow mismatch should fail")
        assert_equal("does not match requested flow/mode" in (proc.stderr + proc.stdout), True, "flow mismatch error")
        print("  [PASS] test_start_rejects_flow_mode_mismatch")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("OpenClaw Stage Demo Smoke Tests")
    print("=" * 40)
    for test in (test_start_and_approve_flow, test_start_rejects_flow_mode_mismatch):
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
