#!/usr/bin/env python3
"""Smoke tests for role_metadata.py."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import shutil
import sys
from pathlib import Path

from test_helpers import assert_contains, assert_equal, make_temp_root, write_text

import nexus_testing.role_metadata as role_metadata

PROJECT_DIR = Path(__file__).resolve().parents[1]


def test_parse_real_role_metadata() -> None:
    parsed = role_metadata.parse_role_doc(PROJECT_DIR / "roles" / "skill-tester.md")
    assert_equal(parsed["mainAgentTakeoverPolicy"]["enabled"], True, "skill-tester takeover enabled")
    assert_equal("blocked" in parsed["mainAgentTakeoverPolicy"]["statuses"], True, "skill-tester blocked status")

    parsed_quality = role_metadata.parse_role_doc(PROJECT_DIR / "roles" / "quality-assessor.md")
    assert_equal(parsed_quality["validateMarkdownStructure"], True, "quality-assessor validation enabled")
    assert_equal(parsed_quality["minimumOutput"][0], "\u89c4\u683c\u5b8c\u6574\u6027", "quality-assessor first heading")
    print("  [PASS] test_parse_real_role_metadata")


def test_frontmatter_priority() -> None:
    temp_root = make_temp_root("role-metadata-")
    try:
        role_file = temp_root / "role.md"
        write_text(
            role_file,
            "\n".join(
                [
                    "---",
                    "name: temp-role",
                    "type: executor",
                    "description: temp",
                    "output_validation:",
                    '  - "markdown-headings"',
                    "minimum_output:",
                    '  - "Frontmatter A"',
                    '  - "Frontmatter B"',
                    "minimum_output_aliases:",
                    '  - "Frontmatter B => Alias B"',
                    "takeover_enabled: true",
                    "takeover_statuses:",
                    '  - "blocked"',
                    "takeover_patterns:",
                    '  - "gateway"',
                    "takeover_on_process_failure: false",
                    "---",
                    "",
                    f"## {role_metadata.SECTION_MINIMUM_OUTPUT}",
                    "```text",
                    "## Section Only",
                    "```",
                    "",
                    f"## {role_metadata.SECTION_OUTPUT_VALIDATION}",
                    "- markdown-headings",
                    "",
                    f"## {role_metadata.SECTION_OUTPUT_VALIDATION_ALIASES}",
                    "- Section Only => Section Alias",
                    "",
                    f"## {role_metadata.SECTION_TAKEOVER_POLICY}",
                    "- enabled: false",
                    "- statuses: failed",
                    "- patterns: runtime unavailable",
                    "- onProcessFailure: true",
                    "",
                ]
            )
            + "\n",
        )
        parsed = role_metadata.parse_role_doc(role_file)
        assert_equal(parsed["minimumOutput"], ["Frontmatter A", "Frontmatter B"], "frontmatter minimum output")
        assert_equal(parsed["minimumOutputAliases"], {"Frontmatter B": "Alias B"}, "frontmatter aliases")
        assert_equal(
            parsed["mainAgentTakeoverPolicy"],
            {
                "enabled": True,
                "statuses": ["blocked"],
                "patterns": ["gateway"],
                "onProcessFailure": False,
            },
            "frontmatter takeover policy",
        )
        print("  [PASS] test_frontmatter_priority")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_all_repo_roles_parse() -> None:
    for role_file in sorted((PROJECT_DIR / "roles").glob("*.md")):
        parsed = role_metadata.parse_role_doc(role_file)
        assert_equal(bool(parsed["name"]), True, f"{role_file.name} name present")
        assert_equal(bool(parsed["type"]), True, f"{role_file.name} type present")
        assert_equal(bool(parsed["description"]), True, f"{role_file.name} description present")
    print("  [PASS] test_all_repo_roles_parse")


def test_all_repo_roles_have_input_flow_metadata() -> None:
    for role_file in sorted((PROJECT_DIR / "roles").glob("*.md")):
        parsed = role_metadata.parse_role_doc(role_file)
        assert_equal(bool(parsed["inputSources"]), True, f"{role_file.name} inputSources present")
        assert_equal(bool(parsed["consumers"]), True, f"{role_file.name} consumers present")
    print("  [PASS] test_all_repo_roles_have_input_flow_metadata")


def test_invalid_frontmatter_schema_rejected() -> None:
    temp_root = make_temp_root("role-metadata-invalid-")
    try:
        role_file = temp_root / "role.md"
        write_text(
            role_file,
            "\n".join(
                [
                    "---",
                    "name: broken-role",
                    "type: broken",
                    "description: temp",
                    "output_validation:",
                    '  - "unsupported-rule"',
                    "minimum_output_aliases:",
                    '  - "Missing => Alias"',
                    "takeover_statuses:",
                    '  - "blocked"',
                    "---",
                    "",
                ]
            )
            + "\n",
        )
        try:
            role_metadata.parse_role_doc(role_file)
        except ValueError as exc:
            message = str(exc)
            assert_contains(message, "invalid role metadata schema", "schema validation prefix")
            assert_contains(message, "frontmatter 'type' must be one of", "invalid type reported")
            assert_contains(message, "unsupported output_validation rules", "invalid output rule reported")
            assert_contains(message, "minimum_output_aliases source 'Missing' must exist in minimum_output", "invalid alias reported")
            assert_contains(
                message,
                "takeover_statuses/takeover_patterns/takeover_on_process_failure require 'takeover_enabled'",
                "missing takeover_enabled reported",
            )
        else:
            raise AssertionError("invalid schema should raise ValueError")
        print("  [PASS] test_invalid_frontmatter_schema_rejected")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Role Metadata Smoke Tests")
    print("=" * 40)
    for test in (
        test_parse_real_role_metadata,
        test_frontmatter_priority,
        test_all_repo_roles_parse,
        test_all_repo_roles_have_input_flow_metadata,
        test_invalid_frontmatter_schema_rejected,
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
