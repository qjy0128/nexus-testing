#!/usr/bin/env python3
"""Lightweight pre-validation for skill-results.md before full validation.

This is an advisory tool — it always exits 0 and prints warnings for
structural issues. Run this before validate_flow_a_skill_results.py
to catch common problems early and reduce rework rounds.
"""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import argparse
import json
import re
import sys
from pathlib import Path

from nexus_testing.json_utils import load_json
from nexus_testing.sandbox_skill_invoke.core import read_text

REQUIRED_FIELDS = {"surface-id", "status", "execution-level", "evidence", "notes"}
VALID_STATUSES = {"pending", "passed", "blocked", "incomplete"}
PLACEHOLDER_PATTERNS = [
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\bFIXME\b", re.IGNORECASE),
    re.compile(r"\bTBD\b", re.IGNORECASE),
    re.compile(r"\[待填写\]"),
    re.compile(r"\[待补充\]"),
    re.compile(r"\bpending\.\.\.", re.IGNORECASE),
]

SURFACE_BLOCK_RE = re.compile(
    r"^###\s+(?P<title>[^\n]+)\n(?P<body>(?:- .*(?:\n|$))*)",
    re.MULTILINE,
)


def parse_surface_blocks(text: str) -> dict[str, dict[str, str]]:
    """Parse skill-results.md surface blocks into a dict keyed by surface-id."""
    results: dict[str, dict[str, str]] = {}
    for match in SURFACE_BLOCK_RE.finditer(text):
        block: dict[str, str] = {"title": match.group("title").strip()}
        for line in match.group("body").splitlines():
            if not line.startswith("- "):
                continue
            if ":" not in line:
                continue
            key, value = line[2:].split(":", 1)
            block[key.strip()] = value.strip().strip("`")
        surface_id = block.get("surface-id")
        if surface_id:
            results[surface_id] = block
    return results


def check_required_fields(surface_id: str, block: dict[str, str]) -> list[str]:
    """Check that all required fields are present in a surface block."""
    issues: list[str] = []
    missing = REQUIRED_FIELDS - set(block.keys())
    for field in sorted(missing):
        issues.append(f"[{surface_id}] missing required field: {field}")
    if "notes" in block and "case-coverage=" not in block["notes"]:
        issues.append(f"[{surface_id}] notes missing case-coverage= declaration")
    return issues


def check_status_values(surface_id: str, block: dict[str, str]) -> list[str]:
    """Check that status values are valid."""
    issues: list[str] = []
    status = block.get("status", "")
    if status and status not in VALID_STATUSES:
        issues.append(f"[{surface_id}] invalid status: '{status}'")
    return issues


def check_placeholders(surface_id: str, block: dict[str, str]) -> list[str]:
    """Check for placeholder text in field values."""
    issues: list[str] = []
    for field in ("evidence", "notes"):
        value = block.get(field, "")
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(value):
                issues.append(f"[{surface_id}] placeholder text in {field}: {pattern.pattern}")
                break
    return issues


def check_surface_ids_match_plan(
    parsed: dict[str, dict[str, str]], plan: dict[str, object]
) -> list[str]:
    """Check that surface IDs in results match the execution plan."""
    issues: list[str] = []
    planned_ids = {
        str(s.get("surfaceId", "")) for s in plan.get("surfaces", [])
    }
    result_ids = set(parsed.keys())

    extra = sorted(result_ids - planned_ids)
    for sid in extra:
        issues.append(f"surface {sid} not in SURFACE-EXECUTION-PLAN.json")

    missing = sorted(planned_ids - result_ids)
    for sid in missing:
        issues.append(f"surface {sid} from plan not in skill-results.md")

    return issues


def check_case_ids_consistency(
    parsed: dict[str, dict[str, str]], coverage: dict[str, object]
) -> list[str]:
    """Check that case IDs are consistent between skill-results and coverage."""
    issues: list[str] = []
    coverage_surfaces = {
        str(s.get("surfaceId", "")): s for s in coverage.get("surfaces", [])
    }

    for surface_id, block in parsed.items():
        coverage_entry = coverage_surfaces.get(surface_id)
        if not coverage_entry:
            continue

        coverage_case_ids = {
            str(c.get("caseId", ""))
            for c in coverage_entry.get("caseResults", [])
            if isinstance(c, dict)
        }

        # Check status match
        block_status = block.get("status", "")
        coverage_status = str(coverage_entry.get("status", ""))
        if block_status and coverage_status and block_status != coverage_status:
            issues.append(
                f"[{surface_id}] status mismatch: skill-results='{block_status}' vs coverage='{coverage_status}'"
            )

        # Check for pending cases in coverage when surface claims passed
        if block_status == "passed":
            pending_cases = [
                cid
                for cid in coverage_case_ids
                for c in coverage_entry.get("caseResults", [])
                if isinstance(c, dict) and str(c.get("caseId", "")) == cid and str(c.get("status", "")) == "pending"
            ]
            if pending_cases:
                issues.append(
                    f"[{surface_id}] surface claims 'passed' but has pending cases: {', '.join(sorted(pending_cases))}"
                )

    return issues


def prevalidate(
    skill_results_path: Path,
    surface_plan_path: Path,
    surface_coverage_path: Path,
) -> tuple[int, list[str]]:
    """Run all pre-validation checks. Returns (issue_count, issues_list)."""
    all_issues: list[str] = []

    # Load files
    if not skill_results_path.exists():
        return 1, [f"skill-results.md not found: {skill_results_path}"]
    skill_results_text = read_text(skill_results_path)

    surface_plan: dict[str, object] = {}
    if surface_plan_path.exists():
        try:
            surface_plan = load_json(surface_plan_path)
        except (json.JSONDecodeError, OSError) as exc:
            all_issues.append(f"Cannot parse SURFACE-EXECUTION-PLAN.json: {exc}")

    coverage: dict[str, object] = {}
    if surface_coverage_path.exists():
        try:
            coverage = load_json(surface_coverage_path)
        except (json.JSONDecodeError, OSError) as exc:
            all_issues.append(f"Cannot parse SURFACE-COVERAGE.json: {exc}")

    # Parse surface blocks
    parsed = parse_surface_blocks(skill_results_text)
    if not parsed:
        all_issues.append("No surface blocks found in skill-results.md")
        return len(all_issues), all_issues

    # Check each surface block
    for surface_id, block in sorted(parsed.items()):
        all_issues.extend(check_required_fields(surface_id, block))
        all_issues.extend(check_status_values(surface_id, block))
        all_issues.extend(check_placeholders(surface_id, block))

    # Cross-reference checks
    if surface_plan:
        all_issues.extend(check_surface_ids_match_plan(parsed, surface_plan))
    if coverage:
        all_issues.extend(check_case_ids_consistency(parsed, coverage))

    return len(all_issues), all_issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill-results",
        required=True,
        help="Path to skill-results.md",
    )
    parser.add_argument(
        "--surface-plan",
        required=True,
        help="Path to SURFACE-EXECUTION-PLAN.json",
    )
    parser.add_argument(
        "--surface-coverage",
        required=True,
        help="Path to SURFACE-COVERAGE.json",
    )
    args = parser.parse_args()

    issue_count, issues = prevalidate(
        Path(args.skill_results).resolve(),
        Path(args.surface_plan).resolve(),
        Path(args.surface_coverage).resolve(),
    )

    if issues:
        print(f"PREVALIDATION_STATUS=issues ({issue_count} found)")
        for issue in issues:
            print(f"  WARNING: {issue}")
    else:
        print("PREVALIDATION_STATUS=ok")
        print("All structural checks passed. Safe to run full validation.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
