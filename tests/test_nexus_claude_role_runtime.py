#!/usr/bin/env python3
"""Smoke tests for nexus_claude_role_runtime.py dry-run prompt generation."""

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
SCRIPT = PROJECT_DIR / "scripts" / "nexus_claude_role_runtime.py"


def test_dry_run_builds_prompt_and_command() -> None:
    temp_root = make_temp_root("claude-role-runtime-")
    try:
        payload_path = temp_root / "payload.json"
        prompt_path = temp_root / "prompt.md"
        write_text(
            payload_path,
            json.dumps(
                {
                    "roleId": "test-designer",
                    "roleFile": str(PROJECT_DIR / "roles" / "test-designer.md"),
                    "stageLabel": "阶段三",
                    "stageName": "测试设计",
                    "reportDir": str(temp_root / "reports"),
                    "missingDeliverables": ["TEST-DESIGN.md", "SURFACE-EXECUTION-PLAN.json"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        write_text(prompt_path, "# Launch Prompt\n\nGenerate the role deliverables.\n")
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--payload-file",
                str(payload_path),
                "--prompt-file",
                str(prompt_path),
                "--claude-command",
                "claude",
                "--allowed-tools",
                "Read",
                "Write",
                "--dry-run",
            ],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(proc.returncode, 0, "dry-run exit code")
        data = json.loads(proc.stdout)
        assert_equal(data["command"][0], "claude", "claude command")
        assert_contains(data["prompt"], "You are the stage-role subagent `test-designer`", "prompt includes role")
        assert_contains(data["prompt"], "Generate the role deliverables.", "prompt includes source prompt")
        print("  [PASS] test_dry_run_builds_prompt_and_command")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Nexus Claude Role Runtime Smoke Tests")
    print("=" * 40)
    for test in (test_dry_run_builds_prompt_and_command,):
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
