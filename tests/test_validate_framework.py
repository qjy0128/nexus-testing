#!/usr/bin/env python3
"""Smoke tests for validate-framework CLI shell syntax controls."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import importlib.util
import sys
from pathlib import Path

from test_helpers import assert_contains, assert_equal

ROOT = Path(__file__).resolve().parents[1]
VALIDATE_FRAMEWORK = ROOT / "scripts" / "validate-framework.py"


def load_validate_framework_module():
    spec = importlib.util.spec_from_file_location(
        "validate_framework_cli_test",
        VALIDATE_FRAMEWORK,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_validate_framework_module()

    args = module.parse_args(
        [
            "--json",
            "--shell-syntax",
            "require",
            "--bash-path",
            r"C:\Program Files\Git\usr\bin\bash.exe",
        ]
    )
    assert_equal(args.json, True, "parse_args json flag")
    assert_equal(args.shell_syntax, "require", "parse_args shell-syntax flag")
    assert_equal(
        args.bash_path,
        r"C:\Program Files\Git\usr\bin\bash.exe",
        "parse_args bash-path flag",
    )

    issues, warnings = module.validate_shell_script_syntax(shell_syntax_mode="skip")
    assert_equal(issues, [], "skip shell syntax issues")
    assert_equal(warnings, [], "skip shell syntax warnings")

    missing_bash = str(ROOT / ".tmp-validation" / "missing-bash.exe")
    issues, warnings = module.validate_shell_script_syntax(
        shell_syntax_mode="auto",
        bash_path=missing_bash,
    )
    assert_equal(issues, [], "auto missing bash issues")
    assert_equal(len(warnings), 1, "auto missing bash warning count")
    assert_contains(warnings[0], "requested bash path does not exist", "auto missing bash warning")

    issues, warnings = module.validate_shell_script_syntax(
        shell_syntax_mode="require",
        bash_path=missing_bash,
    )
    assert_equal(len(issues), 1, "require missing bash issue count")
    assert_contains(issues[0], "requested bash path does not exist", "require missing bash issue")
    assert_equal(warnings, [], "require missing bash warnings")

    print("validate-framework shell syntax smoke tests")
    print("=" * 40)
    print("  [PASS] parse_args accepts shell syntax controls")
    print("  [PASS] skip mode bypasses shell syntax validation")
    print("  [PASS] auto mode degrades missing requested bash to warning")
    print("  [PASS] require mode upgrades missing requested bash to issue")
    print("=" * 40)
    print("4 passed, 0 failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
