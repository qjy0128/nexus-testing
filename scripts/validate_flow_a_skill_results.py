#!/usr/bin/env python3
"""Validate Flow A skill-results coverage against SURFACE-EXECUTION-PLAN.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from sandbox_skill_invoke.core import read_text


SURFACE_BLOCK_RE = re.compile(
    r"^###\s+(?P<title>[^\n]+)\n(?P<body>(?:- .*(?:\n|$))+)",
    re.MULTILINE,
)


def load_json(path: Path) -> dict[str, object]:
    return json.loads(read_text(path))


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


def validate(surface_plan: dict[str, object], skill_results: str) -> list[str]:
    issues: list[str] = []
    parsed = parse_surface_results(skill_results)
    for surface in surface_plan.get("surfaces", []):
        surface_id = str(surface.get("surfaceId", ""))
        surface_kind = str(surface.get("kind", "unknown"))
        minimum_mode = str(surface.get("minimumMode", "unknown"))
        block = parsed.get(surface_id)
        if block is None:
            issues.append(f"Missing surface execution block for {surface_id}")
            continue

        execution_level = block.get("execution-level")
        status = block.get("status")
        evidence = block.get("evidence", "")
        notes = block.get("notes", "")
        if not execution_level:
            issues.append(f"{surface_id} is missing execution-level")
        if not status:
            issues.append(f"{surface_id} is missing status")
        if not evidence:
            issues.append(f"{surface_id} is missing evidence")
        if not notes:
            issues.append(f"{surface_id} is missing notes")

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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    surface_plan_path = Path(args.surface_plan).expanduser().resolve()
    skill_results_path = Path(args.skill_results).expanduser().resolve()
    if not surface_plan_path.exists():
        raise SystemExit(f"ERROR: surface plan does not exist: {surface_plan_path}")
    if not skill_results_path.exists():
        raise SystemExit(f"ERROR: skill results do not exist: {skill_results_path}")

    plan = load_json(surface_plan_path)
    issues = validate(plan, read_text(skill_results_path))
    if issues:
        for issue in issues:
            print(f"ISSUE={issue}")
        return 1

    print("STATUS=passed")
    print(f"SURFACE_COUNT={len(plan.get('surfaces', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
