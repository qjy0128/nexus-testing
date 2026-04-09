#!/usr/bin/env python3
"""Smoke tests for runtime_config_schema.py."""

from __future__ import annotations

import sys

import runtime_config_schema
from generate_runtime_bridge_config import claude_config, mock_config, openclaw_config
from test_helpers import assert_contains, assert_equal


def test_generated_presets_validate() -> None:
    mock = runtime_config_schema.validate_runtime_config(mock_config())
    claude = runtime_config_schema.validate_runtime_config(
        claude_config("claude", "bypassPermissions", None, ["Read", "Write"])
    )
    openclaw = runtime_config_schema.validate_runtime_config(
        openclaw_config("openclaw", "telegram", "D:/repo/nexus-testing")
    )
    assert_equal(mock["name"], "mock-runtime", "mock runtime name")
    assert_equal("default" in claude, True, "claude default exists")
    assert_equal("default" in openclaw, True, "openclaw default exists")
    print("  [PASS] test_generated_presets_validate")


def test_invalid_runtime_config_rejected() -> None:
    invalid = {
        "name": "broken-runtime",
        "default": {
            "command": [],
            "timeoutSeconds": "fast",
        },
        "roles": {
            "skill-tester": {
                "command": ["python", "runner.py"],
                "mainAgentTakeoverPolicy": {"enabled": True},
            }
        },
    }
    try:
        runtime_config_schema.validate_runtime_config(invalid)
    except ValueError as exc:
        message = str(exc)
        assert_contains(message, "runtime config.default.command must be a non-empty list", "empty command")
    else:
        raise AssertionError("invalid runtime config should raise ValueError")
    print("  [PASS] test_invalid_runtime_config_rejected")


def test_invalid_runtime_role_policy_rejected() -> None:
    invalid = {
        "default": {
            "command": ["python", "runner.py"],
            "cwd": "{workspace_root}",
            "timeoutSeconds": 30,
        },
        "roles": {
            "skill-tester": {
                "command": ["python", "runner.py"],
                "mainAgentTakeoverPolicy": {"enabled": True},
            }
        },
    }
    try:
        runtime_config_schema.validate_runtime_config(invalid)
    except ValueError as exc:
        message = str(exc)
        assert_contains(
            message,
            "runtime config.roles[skill-tester].mainAgentTakeoverPolicy enabled policy must define statuses, patterns, or onProcessFailure",
            "invalid takeover policy",
        )
    else:
        raise AssertionError("invalid takeover policy should raise ValueError")
    print("  [PASS] test_invalid_runtime_role_policy_rejected")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Runtime Config Schema Smoke Tests")
    print("=" * 40)
    for test in (
        test_generated_presets_validate,
        test_invalid_runtime_config_rejected,
        test_invalid_runtime_role_policy_rejected,
    ):
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
