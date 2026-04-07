#!/usr/bin/env python3
"""Generate Flow A stage-five skill execution worklist from the surface plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_json(path: Path) -> dict[str, object]:
    return json.loads(read_text(path))


def render_surface(surface: dict[str, object]) -> str:
    source = surface.get("source", {})
    source_path = source.get("path", "unknown")
    source_key = source.get("key", "unknown")
    source_line = source.get("line")
    source_suffix = f":{source_line}" if isinstance(source_line, int) else ""
    target = surface.get("command") or surface.get("path") or surface.get("identifier")
    case_ids = ", ".join(str(item) for item in surface.get("testCaseIds", []))
    lines = [
        f"### {surface.get('surfaceId')} - {surface.get('kind')} (`{surface.get('identifier')}`)",
        f"- minimum-mode: `{surface.get('minimumMode')}`",
        f"- primary-executor: `{surface.get('primaryExecutor')}`",
        f"- secondary-executor: `{surface.get('secondaryExecutor')}`",
        f"- execution-target: `{target}`",
        f"- focus-areas: {', '.join(str(item) for item in surface.get('focusAreas', []))}",
        f"- security-focus: {', '.join(str(item) for item in surface.get('securityFocus', []))}",
        f"- linked-capabilities: {', '.join(str(item) for item in surface.get('linkedCapabilityNames', [])) or '(none)'}",
        f"- source: `{source_path}{source_suffix} ({source_key})`",
        f"- required-test-cases: {case_ids or '(none)'}",
        "- execution-template:",
        f"  - surface-id: `{surface.get('surfaceId')}`",
        f"  - execution-level: `{surface.get('minimumMode')}`",
        "  - status: `passed|blocked|incomplete`",
        "  - evidence: `<trace/output/log path>`",
        "  - notes: `<brief outcome>`",
        "",
    ]
    return "\n".join(lines)


def build_coverage(plan: dict[str, object]) -> dict[str, object]:
    surfaces = []
    for surface in plan.get("surfaces", []):
        surfaces.append(
            {
                "surfaceId": surface.get("surfaceId"),
                "kind": surface.get("kind"),
                "identifier": surface.get("identifier"),
                "name": surface.get("name"),
                "path": surface.get("path"),
                "command": surface.get("command"),
                "minimumMode": surface.get("minimumMode"),
                "requiredCaseIds": list(surface.get("testCaseIds", [])),
                "status": "pending",
                "executionLevel": None,
                "evidence": [],
                "notes": "",
            }
        )
    return {
        "packageName": plan.get("packageName", "unknown"),
        "parallelRoles": list(plan.get("parallelRoles", [])),
        "surfaces": surfaces,
    }


def build_worklist(plan: dict[str, object]) -> str:
    title = str(plan.get("packageName", "unknown"))
    surfaces = list(plan.get("surfaces", []))
    lines = [
        f"# SKILL-SURFACE-WORKLIST - {title}",
        "",
        "## Stage-Five Rules",
        "",
        "- Execute surfaces in order; do not cherry-pick a single entry point.",
        "- Every surface must produce one structured block in `skill-results.md`.",
        "- Each block must include `surface-id`, `execution-level`, `status`, `evidence`, and `notes`.",
        "- If a surface only reached trace or probe-only evidence, the final conclusion must not treat it as a functional pass.",
        "",
        "## Ordered Surface Worklist",
        "",
    ]
    for surface in surfaces:
        lines.append(render_surface(surface))

    lines.extend(
        [
            "## skill-results.md Required Shape",
            "",
            "```text",
            "### SURFACE-XX - <kind> (`<identifier>`)",
            "- surface-id: `SURFACE-XX`",
            "- execution-level: `live|shim-live|trace`",
            "- status: `passed|blocked|incomplete`",
            "- evidence: `<path1>, <path2>`",
            "- notes: <brief outcome>",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface-plan", required=True, help="Path to SURFACE-EXECUTION-PLAN.json")
    parser.add_argument("--output-dir", required=True, help="Report root directory")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    surface_plan_path = Path(args.surface_plan).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not surface_plan_path.exists():
        raise SystemExit(f"ERROR: surface plan does not exist: {surface_plan_path}")

    plan = load_json(surface_plan_path)
    execution_dir = output_dir / "TEST-EXECUTION"
    execution_dir.mkdir(parents=True, exist_ok=True)

    worklist_path = execution_dir / "SKILL-SURFACE-WORKLIST.md"
    coverage_path = execution_dir / "SURFACE-COVERAGE.json"
    write_text(worklist_path, build_worklist(plan) + "\n")
    write_text(coverage_path, json.dumps(build_coverage(plan), ensure_ascii=False, indent=2) + "\n")

    print(f"OUTPUT_DIR={output_dir}")
    print(f"WORKLIST={worklist_path}")
    print(f"SURFACE_COVERAGE={coverage_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
