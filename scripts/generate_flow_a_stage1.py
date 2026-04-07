#!/usr/bin/env python3
"""Generate Flow A stage-one artifacts from repository facts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from extract_product_fingerprint import extract_product_fingerprint, resolve_target_root


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def render_source(source: dict[str, object] | None) -> str:
    if not source:
        return "unknown"
    path = str(source.get("path", "unknown"))
    line = source.get("line")
    key = source.get("key")
    suffix = ""
    if isinstance(line, int):
        suffix += f":{line}"
    if key:
        suffix += f" ({key})"
    return f"`{path}{suffix}`"


def render_sources(sources: list[dict[str, object]]) -> str:
    if not sources:
        return "unknown"
    return ", ".join(render_source(item) for item in sources)


def joined(values: list[object], fallback: str = "unknown") -> str:
    text = ", ".join(str(item) for item in values if str(item).strip())
    return text or fallback


def package_name_source(fingerprint: dict[str, object]) -> str:
    if str(fingerprint.get("packageName", "unknown")) != "unknown":
        return "`package.json (name)`"
    return render_sources(list(fingerprint.get("version", {}).get("sources", [])))


def render_fact_summary(fingerprint: dict[str, object]) -> str:
    version = fingerprint.get("version", {})
    license_info = fingerprint.get("license", {})
    package_name = str(fingerprint.get("packageName", "unknown"))
    product_type = joined(list(fingerprint.get("productType", [])))
    runtime = joined(list(fingerprint.get("runtime", [])))
    return "\n".join(
        [
            "| Field | Value | Evidence |",
            "|------|-------|----------|",
            f"| Package name | {package_name} | {package_name_source(fingerprint)} |",
            f"| Product type | {product_type} | `PRODUCT-FINGERPRINT.json` |",
            f"| Runtime | {runtime} | `PRODUCT-FINGERPRINT.json` |",
            f"| Version | {version.get('value', 'unknown')} | {render_sources(list(version.get('sources', [])))} |",
            f"| License | {license_info.get('value', 'unknown')} | {render_sources(list(license_info.get('sources', [])))} |",
        ]
    )


def render_entry_surfaces(fingerprint: dict[str, object]) -> str:
    surfaces = list(fingerprint.get("entrySurfaces", []))
    if not surfaces:
        return "_No real entry surfaces were discovered._"
    lines = ["| Kind | Identifier | Evidence |", "|------|------------|----------|"]
    for surface in surfaces:
        identifier = surface.get("path") or surface.get("name") or surface.get("command") or "unknown"
        lines.append(
            f"| {surface.get('kind', 'unknown')} | {identifier} | {render_source(surface.get('source'))} |"
        )
    return "\n".join(lines)


def render_capability_surfaces(fingerprint: dict[str, object]) -> str:
    surfaces = list(fingerprint.get("capabilitySurfaces", []))
    if not surfaces:
        return "_No capability surfaces were discovered._"
    lines = ["| Name | Kind | Evidence |", "|------|------|----------|"]
    for surface in surfaces:
        lines.append(
            f"| {surface.get('name', 'unknown')} | {surface.get('kind', 'unknown')} | {render_source(surface.get('source'))} |"
        )
    return "\n".join(lines)


def render_runtime_requirements(fingerprint: dict[str, object]) -> str:
    requirements = list(fingerprint.get("runtimeRequirements", []))
    if not requirements:
        return "- No explicit runtime version constraints were discovered."
    return "\n".join(
        f"- `{item.get('name', 'runtime')}`: `{item.get('value', 'unknown')}` from {render_source(item.get('source'))}"
        for item in requirements
    )


def render_test_implications(fingerprint: dict[str, object]) -> str:
    product_types = set(str(item) for item in fingerprint.get("productType", []))
    implications: list[str] = []
    if "skill" in product_types:
        implications.append(
            "- Cover SKILL routing, argument-hint behavior, subcommands, and deliverable-send behavior."
        )
    if "cli" in product_types:
        implications.append(
            "- Treat bin commands and package scripts as first-class surfaces instead of collapsing them into a single skill test."
        )
    if "plugin" in product_types:
        implications.append(
            "- Validate plugin manifest integrity, extension registration, and hook-facing behavior instead of testing documentation only."
        )
    if "mcp" in product_types:
        implications.append(
            "- Model MCP/server behavior explicitly; do not reinterpret the target as an HTTP API without evidence."
        )
    if "package" in product_types:
        implications.append(
            "- Pull installation contract, dependencies, and runtime requirements into the stage-zero environment check."
        )
    if not implications:
        implications.append(
            "- No reliable product surfaces were discovered yet; Flow A should block until the fingerprint is corrected."
        )
    return "\n".join(implications)


def render_open_questions(fingerprint: dict[str, object]) -> str:
    questions: list[str] = []
    if fingerprint.get("version", {}).get("value") == "unknown":
        questions.append("- Version is still unknown; later reports must not invent one.")
    if fingerprint.get("license", {}).get("value") == "unknown":
        questions.append("- License is still unknown; later reports must not invent one.")
    if not fingerprint.get("runtimeRequirements", []):
        questions.append("- No explicit runtime version constraint was found; stage zero should confirm the real environment.")
    if not questions:
        questions.append("- No blocking open questions were discovered at stage one.")
    return "\n".join(questions)


def build_spec_markdown(target_root: Path, fingerprint: dict[str, object]) -> str:
    title = str(fingerprint.get("packageName", "unknown"))
    if not title or title == "unknown":
        title = target_root.name
    lines = [
        f"# SPEC.md - {title}",
        "",
        "## 1. Fact Summary",
        "",
        render_fact_summary(fingerprint),
        "",
        "## 2. Product Surfaces",
        "",
        "### 2.1 Real Entry Surfaces",
        "",
        render_entry_surfaces(fingerprint),
        "",
        "### 2.2 Capability Surfaces",
        "",
        render_capability_surfaces(fingerprint),
        "",
        "## 3. Runtime and Dependency Constraints",
        "",
        render_runtime_requirements(fingerprint),
        "",
        "## 4. Testing Implications",
        "",
        render_test_implications(fingerprint),
        "",
        "## 5. Open Questions",
        "",
        render_open_questions(fingerprint),
        "",
        "## 6. Constraints",
        "",
        "- `SPEC.md` may extend only facts already present in `PRODUCT-FINGERPRINT.json`.",
        "- Any API, SDK, subcommand, route, Go library, or core interface not present in the fingerprint remains unverified.",
        "",
    ]
    return "\n".join(lines)


def evaluate_consistency(fingerprint: dict[str, object]) -> tuple[str, list[str], list[str], list[str]]:
    verified: list[str] = []
    gaps: list[str] = []
    blockers: list[str] = []

    product_type = list(fingerprint.get("productType", []))
    if product_type and product_type != ["unknown"]:
        verified.append(f"Product type identified: {joined(product_type)}")
    else:
        blockers.append("No reliable product type was identified.")

    runtime = list(fingerprint.get("runtime", []))
    if runtime and runtime != ["unknown"]:
        verified.append(f"Runtime identified: {joined(runtime)}")
    else:
        blockers.append("No reliable runtime was identified.")

    entry_surfaces = list(fingerprint.get("entrySurfaces", []))
    if entry_surfaces:
        verified.append(f"Discovered {len(entry_surfaces)} real entry surfaces.")
    else:
        blockers.append("No real entry surfaces were discovered.")

    capabilities = list(fingerprint.get("capabilitySurfaces", []))
    if capabilities:
        verified.append(f"Discovered {len(capabilities)} capability surfaces.")
    else:
        blockers.append("No capability surfaces were discovered.")

    version = fingerprint.get("version", {})
    if version.get("value") == "unknown":
        gaps.append("Version remains unknown.")
    else:
        verified.append(f"Version identified: {version.get('value')}")

    license_info = fingerprint.get("license", {})
    if license_info.get("value") == "unknown":
        gaps.append("License remains unknown.")
    else:
        verified.append(f"License identified: {license_info.get('value')}")

    status = "passed" if not blockers else "blocked-spec-invalid"
    return status, verified, gaps, blockers


def build_consistency_review(target_root: Path, fingerprint: dict[str, object]) -> str:
    status, verified, gaps, blockers = evaluate_consistency(fingerprint)
    title = str(fingerprint.get("packageName", "unknown"))
    if not title or title == "unknown":
        title = target_root.name

    lines = [
        f"# SPEC-CONSISTENCY-REVIEW - {title}",
        "",
        f"- decision: `{status}`",
        "",
        "## Fingerprint Summary",
        "",
        f"- product-type: {joined(list(fingerprint.get('productType', [])))}",
        f"- runtime: {joined(list(fingerprint.get('runtime', [])))}",
        f"- version: {fingerprint.get('version', {}).get('value', 'unknown')}",
        f"- license: {fingerprint.get('license', {}).get('value', 'unknown')}",
        "",
        "## Verified Facts",
        "",
    ]
    lines.extend(f"- {item}" for item in verified) if verified else lines.append("- None")
    lines.extend(["", "## Non-blocking Gaps", ""])
    lines.extend(f"- {item}" for item in gaps) if gaps else lines.append("- None")
    lines.extend(["", "## Blocking Issues", ""])
    lines.extend(f"- {item}" for item in blockers) if blockers else lines.append("- None")
    lines.extend(["", "## Gate Decision", ""])
    if status == "passed":
        lines.append("- Allow Flow A to continue to stage two.")
    else:
        lines.append("- Block stage two until the fingerprint and SPEC are corrected.")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Target repository or SKILL.md path")
    parser.add_argument("--output-dir", required=True, help="Directory for stage-one artifacts")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    target_root = resolve_target_root(args.target)
    if not target_root.exists():
        raise SystemExit(f"ERROR: target does not exist: {args.target}")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    fingerprint = extract_product_fingerprint(target_root)
    write_text(
        output_dir / "PRODUCT-FINGERPRINT.json",
        json.dumps(fingerprint, ensure_ascii=False, indent=2) + "\n",
    )
    write_text(output_dir / "SPEC.md", build_spec_markdown(target_root, fingerprint) + "\n")
    write_text(
        output_dir / "SPEC-CONSISTENCY-REVIEW.md",
        build_consistency_review(target_root, fingerprint) + "\n",
    )

    print(f"OUTPUT_DIR={output_dir}")
    print(f"PRODUCT_FINGERPRINT={output_dir / 'PRODUCT-FINGERPRINT.json'}")
    print(f"SPEC_FILE={output_dir / 'SPEC.md'}")
    print(f"CONSISTENCY_REVIEW={output_dir / 'SPEC-CONSISTENCY-REVIEW.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
