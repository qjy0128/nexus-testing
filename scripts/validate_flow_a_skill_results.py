#!/usr/bin/env python3
"""Validate Flow A stage-five execution against the declared surface and case plan."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from json_utils import load_json
from sandbox_skill_invoke.core import read_text


SURFACE_BLOCK_RE = re.compile(
    r"^###\s+(?P<title>[^\n]+)\n(?P<body>(?:- .*(?:\n|$))+)",
    re.MULTILINE,
)
CASE_STATUS_VALUES = {"pending", "passed", "blocked", "incomplete"}


def parse_surface_results(text: str) -> dict[str, dict[str, str]]:
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


def parse_case_results(coverage_surface: dict[str, object]) -> dict[str, dict[str, object]]:
    parsed: dict[str, dict[str, object]] = {}
    for item in coverage_surface.get("caseResults", []):
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("caseId", "")).strip()
        if not case_id:
            continue
        parsed[case_id] = item
    return parsed


def normalize_executed_case_ids(value: str) -> str:
    text = value.strip()
    if text in {"", "(none)", "none", "None"}:
        return ""
    return text


def validate(surface_plan: dict[str, object], skill_results: str, coverage: dict[str, object]) -> list[str]:
    issues: list[str] = []
    parsed_results = parse_surface_results(skill_results)
    planned_surfaces = {
        str(surface.get("surfaceId", "")): surface for surface in surface_plan.get("surfaces", [])
    }
    coverage_surfaces = {
        str(surface.get("surfaceId", "")): surface for surface in coverage.get("surfaces", [])
    }

    unknown_result_surfaces = sorted(surface_id for surface_id in parsed_results if surface_id not in planned_surfaces)
    for surface_id in unknown_result_surfaces:
        issues.append(f"skill-results includes undeclared surface {surface_id}")

    unknown_coverage_surfaces = sorted(surface_id for surface_id in coverage_surfaces if surface_id not in planned_surfaces)
    for surface_id in unknown_coverage_surfaces:
        issues.append(f"SURFACE-COVERAGE.json includes undeclared surface {surface_id}")

    for surface_id, surface in planned_surfaces.items():
        surface_kind = str(surface.get("kind", "unknown"))
        minimum_mode = str(surface.get("minimumMode", "unknown"))
        required_case_ids = [str(item) for item in surface.get("testCaseIds", []) if str(item).strip()]

        block = parsed_results.get(surface_id)
        if block is None:
            issues.append(f"Missing surface execution block for {surface_id}")
            continue

        coverage_entry = coverage_surfaces.get(surface_id)
        if coverage_entry is None:
            issues.append(f"SURFACE-COVERAGE.json is missing {surface_id}")
            continue

        execution_level = block.get("execution-level")
        status = block.get("status")
        evidence = block.get("evidence", "")
        notes = block.get("notes", "")
        executed_case_ids = normalize_executed_case_ids(block.get("executed-case-ids", ""))
        if not execution_level:
            issues.append(f"{surface_id} is missing execution-level")
        if not status:
            issues.append(f"{surface_id} is missing status")
        if not evidence:
            issues.append(f"{surface_id} is missing evidence")
        if not notes:
            issues.append(f"{surface_id} is missing notes")
        if "case-coverage=" not in notes:
            issues.append(f"{surface_id} is missing case-coverage notes")

        coverage_status = str(coverage_entry.get("status", ""))
        coverage_level = str(coverage_entry.get("executionLevel", ""))
        if coverage_status == "pending":
            issues.append(f"{surface_id} is still pending in SURFACE-COVERAGE.json")
        if status and coverage_status and coverage_status != status:
            issues.append(f"{surface_id} status mismatch between skill-results and SURFACE-COVERAGE.json")
        if execution_level and coverage_level and coverage_level != execution_level:
            issues.append(f"{surface_id} execution-level mismatch between skill-results and SURFACE-COVERAGE.json")

        coverage_required_case_ids = [
            str(item) for item in coverage_entry.get("requiredCaseIds", []) if str(item).strip()
        ]
        if coverage_required_case_ids != required_case_ids:
            issues.append(f"{surface_id} requiredCaseIds drifted from SURFACE-EXECUTION-PLAN.json")

        coverage_case_results = parse_case_results(coverage_entry)
        missing_case_rows = [case_id for case_id in required_case_ids if case_id not in coverage_case_results]
        if missing_case_rows:
            issues.append(f"{surface_id} is missing case rows for: {', '.join(missing_case_rows)}")

        pending_case_ids: list[str] = []
        failed_case_ids: list[str] = []
        executed_case_ids_from_coverage: list[str] = []
        for case_id in required_case_ids:
            row = coverage_case_results.get(case_id)
            if row is None:
                continue
            case_status = str(row.get("status", "pending"))
            if case_status not in CASE_STATUS_VALUES:
                issues.append(f"{surface_id} case {case_id} has invalid status `{case_status}`")
                continue
            if case_status == "pending":
                pending_case_ids.append(case_id)
            else:
                executed_case_ids_from_coverage.append(case_id)
            if case_status != "passed":
                failed_case_ids.append(case_id)

        expected_executed_count = len(executed_case_ids_from_coverage)
        recorded_executed_count = int(coverage_entry.get("executedCaseCount", 0) or 0)
        if recorded_executed_count != expected_executed_count:
            issues.append(f"{surface_id} executedCaseCount does not match caseResults")

        coverage_executed_ids = [str(item) for item in coverage_entry.get("executedCaseIds", []) if str(item).strip()]
        if coverage_executed_ids != executed_case_ids_from_coverage:
            issues.append(f"{surface_id} executedCaseIds do not match caseResults")

        if status == "passed" and pending_case_ids:
            issues.append(f"{surface_id} cannot pass with pending cases: {', '.join(pending_case_ids)}")
        if status == "passed" and failed_case_ids:
            issues.append(f"{surface_id} cannot pass without all required cases passing")

        if status == "passed" and "surface-smoke-only=true" in notes:
            issues.append(f"{surface_id} cannot pass when notes declare surface-smoke-only=true")
        if status == "incomplete" and not pending_case_ids and len(failed_case_ids) == 0 and required_case_ids:
            issues.append(f"{surface_id} is incomplete even though all required cases are marked passed")

        if executed_case_ids and executed_case_ids != ", ".join(executed_case_ids_from_coverage):
            issues.append(f"{surface_id} executed-case-ids do not match SURFACE-COVERAGE.json")

        if minimum_mode in {"live", "shim-live"} and execution_level == "trace" and status == "passed":
            issues.append(f"{surface_id} cannot pass at trace level when minimum mode is {minimum_mode}")
        if surface_kind == "openclaw-extension" and status == "passed":
            if "behavior-verified=true" not in notes:
                issues.append(
                    f"{surface_id} cannot pass as openclaw-extension without behavior-verified=true notes"
                )
            if "registered-hooks=" not in notes:
                issues.append(
                    f"{surface_id} cannot pass as openclaw-extension without registered-hooks evidence notes"
                )
            if execution_level == "live":
                if "runtime-verified=true" not in notes:
                    issues.append(
                        f"{surface_id} cannot pass as live openclaw-extension without runtime-verified=true notes"
                    )
                if "runtime-transport=" not in notes:
                    issues.append(
                        f"{surface_id} cannot pass as live openclaw-extension without runtime-transport notes"
                    )
        if surface_kind == "mcp" and status == "passed":
            if "protocol-verified=true" not in notes:
                issues.append(
                    f"{surface_id} cannot pass as mcp without protocol-verified=true notes"
                )
            if "protocol-version=" not in notes or "tools=" not in notes:
                issues.append(
                    f"{surface_id} cannot pass as mcp without protocol-version and tools evidence notes"
                )

    return issues


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface-plan", required=True, help="Path to SURFACE-EXECUTION-PLAN.json")
    parser.add_argument("--skill-results", required=True, help="Path to TEST-EXECUTION/skill-results.md")
    parser.add_argument("--surface-coverage", help="Optional path to TEST-EXECUTION/SURFACE-COVERAGE.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    surface_plan_path = Path(args.surface_plan).expanduser().resolve()
    skill_results_path = Path(args.skill_results).expanduser().resolve()
    coverage_path = (
        Path(args.surface_coverage).expanduser().resolve()
        if args.surface_coverage
        else skill_results_path.parent / "SURFACE-COVERAGE.json"
    )
    if not surface_plan_path.exists():
        raise SystemExit(f"ERROR: surface plan does not exist: {surface_plan_path}")
    if not skill_results_path.exists():
        raise SystemExit(f"ERROR: skill results do not exist: {skill_results_path}")
    if not coverage_path.exists():
        raise SystemExit(f"ERROR: surface coverage does not exist: {coverage_path}")

    plan = load_json(surface_plan_path)
    coverage = load_json(coverage_path)
    issues = validate(plan, read_text(skill_results_path), coverage)
    if issues:
        for issue in issues:
            print(f"ISSUE={issue}")
        return 1

    print("STATUS=passed")
    print(f"SURFACE_COUNT={len(plan.get('surfaces', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
