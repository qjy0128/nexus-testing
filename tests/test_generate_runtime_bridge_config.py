#!/usr/bin/env python3
"""Smoke tests for generate_runtime_bridge_config.py."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import json
import shutil
import subprocess
import sys
from pathlib import Path

from test_helpers import assert_equal, make_temp_root

PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "scripts" / "generate_runtime_bridge_config.py"


def test_generate_mock_config() -> None:
    temp_root = make_temp_root("runtime-config-")
    try:
        output_path = temp_root / "mock-runtime.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--preset", "mock", "--output-file", str(output_path)],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(proc.returncode, 0, "mock config exit")
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert_equal(payload["name"], "mock-runtime", "mock config name")
        assert_equal(payload["default"]["stallTimeoutSeconds"], 10, "mock stall timeout")
        print("  [PASS] test_generate_mock_config")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_generate_claude_config() -> None:
    temp_root = make_temp_root("runtime-config-claude-")
    try:
        output_path = temp_root / "claude-runtime.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--preset",
                "claude",
                "--output-file",
                str(output_path),
                "--claude-command",
                "claude",
                "--permission-mode",
                "bypassPermissions",
                "--allowed-tools",
                "Read",
                "Write",
            ],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(proc.returncode, 0, "claude config exit")
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        command = payload["default"]["command"]
        assert_equal("nexus_claude_role_runtime.py" in " ".join(command), True, "claude adapter referenced")
        assert_equal(payload["default"]["stallTimeoutSeconds"], 300, "claude stall timeout")
        print("  [PASS] test_generate_claude_config")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_generate_openclaw_config() -> None:
    temp_root = make_temp_root("runtime-config-openclaw-")
    try:
        output_path = temp_root / "openclaw-runtime.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--preset",
                "openclaw",
                "--output-file",
                str(output_path),
                "--openclaw-command",
                "openclaw",
                "--channel",
                "telegram",
            ],
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert_equal(proc.returncode, 0, "openclaw config exit")
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        command = payload["default"]["command"]
        assert_equal("nexus_openclaw_role_runtime.py" in " ".join(command), True, "openclaw adapter referenced")
        assert_equal(payload["default"]["stallTimeoutSeconds"], 300, "openclaw stall timeout")
        print("  [PASS] test_generate_openclaw_config")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Runtime Bridge Config Generator Smoke Tests")
    print("=" * 40)
    for test in (test_generate_mock_config, test_generate_claude_config, test_generate_openclaw_config):
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
