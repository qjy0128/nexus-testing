#!/usr/bin/env python3
"""
Skill Structure Validator — Nexus Testing Framework
Validates skill directories against quality standards and Tier requirements.

Usage:
    python skill-structure-validator.py <skill_path> [--tier TIER] [--json] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import sys

from skill_structure_validator_core import (
    VERSION,
    SkillStructureValidator,
    ValidationReport,
)


def format_json(report: ValidationReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def format_human(report: ValidationReport) -> str:
    lines = [
        "=" * 60,
        "SKILL STRUCTURE VALIDATION REPORT",
        "=" * 60,
        f"Skill: {report.skill_path}",
        f"Timestamp: {report.timestamp}",
        f"Overall Score: {report.overall_score:.1f}/100 ({report.compliance_level})",
        f"Detected Tier: {report.detected_tier or '(unknown)'}",
        "",
    ]

    if report.checks:
        lines.append("CHECKS:")
        for result in report.checks.values():
            status = "✓" if result["passed"] else "✗"
            lines.append(f"  {status} {result['message']}")
        lines.append("")

    if report.warnings:
        lines.append("WARNINGS:")
        for warning in report.warnings:
            lines.append(f"  ⚠ {warning}")
        lines.append("")

    if report.errors:
        lines.append("ERRORS:")
        for error in report.errors:
            lines.append(f"  ✗ {error}")
        lines.append("")

    if report.suggestions:
        lines.append("SUGGESTIONS:")
        for suggestion in report.suggestions:
            lines.append(f"  → {suggestion}")
        lines.append("")

    if report.external_imports:
        lines.append("EXTERNAL IMPORTS DETECTED:")
        for script_name, imports in report.external_imports.items():
            lines.append(f"  {script_name}: {', '.join(imports)}")
        lines.append("")

    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate skill directory structure and Tier compliance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python skill-structure-validator.py my-skill\n"
            "  python skill-structure-validator.py my-skill --tier POWERFUL --json\n\n"
            "Tier Requirements:\n"
            "  BASIC     - 100+ lines SKILL.md, 1+ script (50-300 LOC)\n"
            "  STANDARD  - 200+ lines SKILL.md, 1+ script (150-500 LOC)\n"
            "  POWERFUL  - 300+ lines SKILL.md, 2+ scripts (300-800 LOC each)\n"
            f"Version: {VERSION}"
        ),
    )
    parser.add_argument("skill_path", help="Path to skill directory")
    parser.add_argument(
        "--tier",
        choices=["BASIC", "STANDARD", "POWERFUL"],
        help="Target tier for validation",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")

    args = parse_args(argv)
    try:
        validator = SkillStructureValidator(args.skill_path, args.tier, args.verbose)
        report = validator.validate_all()
        print(format_json(report) if args.json else format_human(report))
        return 1 if report.errors or report.overall_score < 60 else 0
    except KeyboardInterrupt:
        print("\nValidation interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
