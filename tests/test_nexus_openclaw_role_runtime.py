#!/usr/bin/env python3
"""Smoke tests for nexus_openclaw_role_runtime.py."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import json
import shutil
import subprocess
import sys
from pathlib import Path

from test_helpers import assert_contains, assert_equal, make_temp_root, write_text

PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "scripts" / "nexus_openclaw_role_runtime.py"
MOCK = PROJECT_DIR / "scripts" / "fixtures" / "mock_openclaw_cli.py"


def build_payload(temp_root: Path) -> tuple[Path, Path]:
    payload_path = temp_root / "payload.json"
    prompt_path = temp_root / "prompt.md"
    report_dir = temp_root / "reports"
    write_text(
        payload_path,
        json.dumps(
            {
                "roleId": "test-designer",
                "roleFile": str(PROJECT_DIR / "roles" / "test-designer.md"),
                "stageId": "stage-3",
                "stageLabel": "阶段三",
                "stageName": "测试设计",
                "reportDir": str(report_dir),
                "missingDeliverables": ["TEST-DESIGN.md", "SURFACE-EXECUTION-PLAN.json"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    write_text(prompt_path, "# Launch Prompt\n\nGenerate role deliverables.\n")
    return payload_path, prompt_path


def test_dry_run_builds_openclaw_invoke() -> None:
    temp_root = make_temp_root("openclaw-role-runtime-")
    try:
        payload_path, prompt_path = build_payload(temp_root)
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--payload-file",
                str(payload_path),
                "--prompt-file",
                str(prompt_path),
                "--openclaw-command",
                "openclaw",
                "--dry-run",
            ],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(proc.returncode, 0, "dry-run exit")
        data = json.loads(proc.stdout)
        assert_contains(" ".join(data["command"]), "invoke", "invoke command present")
        assert_contains(data["prompt"], "你现在是阶段角色 subagent", "prompt includes openclaw role framing")
        print("  [PASS] test_dry_run_builds_openclaw_invoke")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_mock_openclaw_run_returns_result() -> None:
    temp_root = make_temp_root("openclaw-role-runtime-run-")
    try:
        payload_path, prompt_path = build_payload(temp_root)
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--payload-file",
                str(payload_path),
                "--prompt-file",
                str(prompt_path),
                "--openclaw-command",
                sys.executable,
                "--openclaw-args",
                str(MOCK),
            ],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(proc.returncode, 0, "mock run exit")
        data = json.loads(proc.stdout)
        assert_equal(data["resultFile"].endswith(("TEST-DESIGN.md", "SURFACE-EXECUTION-PLAN.json")), True, "result file detected")
        assert_contains(data["note"], "mock openclaw handled", "note propagated")
        print("  [PASS] test_mock_openclaw_run_returns_result")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Nexus OpenClaw Role Runtime Smoke Tests")
    print("=" * 40)
    for test in (test_dry_run_builds_openclaw_invoke, test_mock_openclaw_run_returns_result):
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
