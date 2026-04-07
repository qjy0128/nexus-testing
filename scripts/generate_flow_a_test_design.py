#!/usr/bin/env python3
"""Generate Flow A stage-three artifacts from the stage-one fingerprint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SURFACE_RULES: dict[str, dict[str, object]] = {
    "skill": {
        "label": "Skill Entry",
        "minimum_mode": "shim-live",
        "focus": ["routing", "argument-hint", "subcommand", "delivery"],
        "security_focus": ["prompt-injection", "unsafe-tooling", "delivery-bypass"],
    },
    "bin": {
        "label": "CLI Entry",
        "minimum_mode": "shim-live",
        "focus": ["command-invocation", "stdout-stderr", "exit-status", "invalid-args"],
        "security_focus": ["command-injection", "path-traversal", "unsafe-exec"],
    },
    "openclaw-extension": {
        "label": "Plugin Extension",
        "minimum_mode": "shim-live",
        "focus": ["registration", "hook-behavior", "runtime-loading"],
        "security_focus": ["hook-abuse", "privilege-escalation", "unsafe-side-effects"],
    },
    "plugin-manifest": {
        "label": "Plugin Manifest",
        "minimum_mode": "trace",
        "focus": ["manifest-integrity", "path-resolution", "extension-declaration"],
        "security_focus": ["malicious-manifest", "unexpected-extension", "tampering"],
    },
    "package": {
        "label": "Package Surface",
        "minimum_mode": "trace",
        "focus": ["install-contract", "runtime-requirement", "script-entry"],
        "security_focus": ["supply-chain", "postinstall-risk", "dependency-drift"],
    },
    "mcp": {
        "label": "MCP Surface",
        "minimum_mode": "shim-live",
        "focus": ["server-registration", "tool-contract", "invocation-shape"],
        "security_focus": ["tool-abuse", "parameter-injection", "protocol-mismatch"],
    },
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_json(path: Path) -> dict[str, object]:
    return json.loads(read_text(path))


def ensure_passed_review(path: Path) -> None:
    text = read_text(path)
    if "`passed`" not in text:
        raise SystemExit(
            "ERROR: SPEC-CONSISTENCY-REVIEW.md is not passed; stage-three generation is blocked"
        )


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


def choose_mcp_binding(bin_surfaces: list[dict[str, object]]) -> dict[str, object] | None:
    if len(bin_surfaces) == 1:
        return bin_surfaces[0]

    keyword_candidates: list[dict[str, object]] = []
    for surface in bin_surfaces:
        probe_text = " ".join(
            str(surface.get(field, "")).lower() for field in ("name", "path", "command")
        )
        if any(keyword in probe_text for keyword in ("mcp", "modelcontextprotocol", "server")):
            keyword_candidates.append(surface)

    if len(keyword_candidates) == 1:
        return keyword_candidates[0]
    return None


def dedupe_surfaces(fingerprint: dict[str, object]) -> list[dict[str, object]]:
    surfaces: list[dict[str, object]] = []
    seen: set[str] = set()
    for surface in fingerprint.get("entrySurfaces", []):
        key = json.dumps(surface, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        surfaces.append(dict(surface))

    product_types = set(str(item) for item in fingerprint.get("productType", []))
    if "package" in product_types:
        synthetic = {
            "kind": "package",
            "name": fingerprint.get("packageName", "package"),
            "path": "package.json",
            "source": {"path": "package.json", "key": "name"},
        }
        key = json.dumps(synthetic, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            surfaces.append(synthetic)

    if "mcp" in product_types:
        selected_surface = choose_mcp_binding(
            [surface for surface in surfaces if str(surface.get("kind")) == "bin"]
        )
        synthetic: dict[str, object] = {
            "kind": "mcp",
            "name": "mcp-runtime",
            "path": "package.json",
            "command": None,
            "source": {"path": "package.json", "key": "dependencies"},
        }
        if selected_surface is not None:
            if isinstance(selected_surface.get("source"), dict):
                synthetic["source"] = dict(selected_surface["source"])
            synthetic["name"] = selected_surface.get("name") or synthetic["name"]
            synthetic["path"] = (
                selected_surface.get("path")
                or selected_surface.get("command")
                or synthetic["path"]
            )
            synthetic["command"] = selected_surface.get("command")
        key = json.dumps(synthetic, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            surfaces.append(synthetic)

    return surfaces


def related_capabilities(
    surface: dict[str, object], capabilities: list[dict[str, object]]
) -> list[dict[str, object]]:
    kind = str(surface.get("kind", "unknown"))
    path = str(surface.get("path") or "")
    matches: list[dict[str, object]] = []
    for capability in capabilities:
        source = capability.get("source", {})
        source_path = str(source.get("path") or "")
        cap_kind = str(capability.get("kind", "unknown"))
        if path and source_path == path:
            matches.append(capability)
            continue
        if kind == "package" and source_path == "package.json":
            matches.append(capability)
            continue
        if kind == "mcp" and cap_kind == "runtime-surface":
            matches.append(capability)
    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    for capability in matches:
        key = json.dumps(capability, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(capability)
    return deduped


def build_surface_inventory(fingerprint: dict[str, object]) -> list[dict[str, object]]:
    inventory: list[dict[str, object]] = []
    capabilities = list(fingerprint.get("capabilitySurfaces", []))
    for index, surface in enumerate(dedupe_surfaces(fingerprint), start=1):
        kind = str(surface.get("kind", "unknown"))
        rule = SURFACE_RULES.get(kind, SURFACE_RULES["package"])
        identifier = surface.get("path") or surface.get("name") or surface.get("command") or f"{kind}-{index}"
        inventory.append(
            {
                "surfaceId": f"SURFACE-{index:02d}",
                "kind": kind,
                "label": rule["label"],
                "identifier": str(identifier),
                "name": surface.get("name"),
                "path": surface.get("path"),
                "command": surface.get("command"),
                "minimumMode": rule["minimum_mode"],
                "primaryExecutor": "skill-tester",
                "secondaryExecutor": "security-tester",
                "focusAreas": list(rule["focus"]),
                "securityFocus": list(rule["security_focus"]),
                "source": surface.get("source"),
                "linkedCapabilities": related_capabilities(surface, capabilities),
            }
        )
    return inventory


def build_case(
    case_id: str,
    surface: dict[str, object],
    capability_id: str,
    category: str,
    title: str,
    objective: str,
    steps: list[str],
    expected: list[str],
) -> dict[str, object]:
    return {
        "caseId": case_id,
        "surfaceId": surface["surfaceId"],
        "surfaceKind": surface["kind"],
        "title": title,
        "category": category,
        "capabilityId": capability_id,
        "minimumMode": surface["minimumMode"],
        "primaryExecutor": surface["primaryExecutor"],
        "secondaryExecutor": surface["secondaryExecutor"],
        "objective": objective,
        "steps": steps,
        "expected": expected,
    }


def build_cases(surface: dict[str, object], case_start: int) -> list[dict[str, object]]:
    identifier = str(surface["identifier"])
    surface_id = str(surface["surfaceId"])
    cases: list[dict[str, object]] = []

    cases.append(
        build_case(
            f"TC-{case_start:03d}",
            surface,
            f"{surface_id}-BASE",
            "positive",
            f"{surface['label']} positive path",
            f"Verify the real {surface['kind']} surface `{identifier}` can be reached with real evidence.",
            [
                f"Resolve the real surface `{identifier}` from the repository or runtime.",
                f"Invoke or load the surface in `{surface['minimumMode']}` mode.",
                "Capture trigger, tool, output, or load evidence instead of relying on prose.",
            ],
            [
                "The surface is discoverable and matches the fingerprint.",
                "The invocation result contains structured evidence or an explicit blocker.",
            ],
        )
    )
    cases.append(
        build_case(
            f"TC-{case_start + 1:03d}",
            surface,
            f"{surface_id}-NEG",
            "negative",
            f"{surface['label']} negative path",
            "Verify invalid input or a non-matching request does not silently pass.",
            [
                "Construct a non-matching or invalid invocation for the same surface.",
                "Run the invocation with the same evidence requirements.",
                "Record whether the product rejects, blocks, or misroutes the request.",
            ],
            [
                "A non-matching request does not produce a false success.",
                "The system returns an explicit rejection, validation error, or blocker.",
            ],
        )
    )
    cases.append(
        build_case(
            f"TC-{case_start + 2:03d}",
            surface,
            f"{surface_id}-BOUNDARY",
            "boundary",
            f"{surface['label']} boundary and evidence path",
            "Verify the edge path still returns auditable evidence.",
            [
                f"Exercise one edge condition derived from {', '.join(surface['focusAreas'][:2])}.",
                "Repeat the run with explicit evidence capture enabled.",
                "Check that output, delivery, registration, or load evidence remains inspectable.",
            ],
            [
                "The edge case does not collapse into an unverified prose-only success.",
                "Structured evidence is still available, or the case is marked blocked.",
            ],
        )
    )

    next_case = case_start + 3
    for capability_index, capability in enumerate(surface["linkedCapabilities"], start=1):
        cap_name = str(capability.get("name", f"capability-{capability_index}"))
        cases.append(
            build_case(
                f"TC-{next_case:03d}",
                surface,
                f"{surface_id}-CAP-{capability_index:02d}",
                "capability",
                f"{surface['label']} capability `{cap_name}`",
                f"Verify capability `{cap_name}` is backed by a real executable surface instead of prose.",
                [
                    f"Target capability `{cap_name}` from surface `{identifier}`.",
                    "Run the smallest real invocation that should trigger this capability.",
                    "Capture structured evidence for trigger, tools, output, or runtime load behavior.",
                ],
                [
                    f"Capability `{cap_name}` is observable from the declared real surface.",
                    "The result can be traced back to the fingerprint source.",
                ],
            )
        )
        next_case += 1

    return cases


def build_execution_plan(
    fingerprint: dict[str, object], surface_inventory: list[dict[str, object]]
) -> dict[str, object]:
    surfaces: list[dict[str, object]] = []
    case_counter = 1
    for surface in surface_inventory:
        cases = build_cases(surface, case_counter)
        case_counter += len(cases)
        surfaces.append(
            {
                "surfaceId": surface["surfaceId"],
                "kind": surface["kind"],
                "identifier": surface["identifier"],
                "name": surface.get("name"),
                "path": surface.get("path"),
                "command": surface.get("command"),
                "minimumMode": surface["minimumMode"],
                "primaryExecutor": surface["primaryExecutor"],
                "secondaryExecutor": surface["secondaryExecutor"],
                "focusAreas": surface["focusAreas"],
                "securityFocus": surface["securityFocus"],
                "linkedCapabilityNames": [
                    str(item.get("name", "unknown")) for item in surface["linkedCapabilities"]
                ],
                "testCaseIds": [case["caseId"] for case in cases],
                "source": surface.get("source"),
            }
        )
        surface["generatedCases"] = cases

    return {
        "packageName": fingerprint.get("packageName", "unknown"),
        "productType": list(fingerprint.get("productType", [])),
        "parallelRoles": ["skill-tester", "security-tester"],
        "surfaces": surfaces,
    }


def render_surface_inventory(surface_inventory: list[dict[str, object]]) -> str:
    lines = [
        "| Surface ID | Kind | Identifier | Minimum Mode | Primary Executor |",
        "|------------|------|------------|--------------|------------------|",
    ]
    for surface in surface_inventory:
        lines.append(
            f"| {surface['surfaceId']} | {surface['kind']} | {surface['identifier']} | {surface['minimumMode']} | {surface['primaryExecutor']} |"
        )
    return "\n".join(lines)


def render_branch_matrix(surface_inventory: list[dict[str, object]]) -> str:
    lines = [
        "| Surface ID | Positive | Negative | Boundary | Capability |",
        "|------------|----------|----------|----------|------------|",
    ]
    for surface in surface_inventory:
        cases = list(surface.get("generatedCases", []))
        counts = {"positive": 0, "negative": 0, "boundary": 0, "capability": 0}
        for case in cases:
            counts[str(case["category"])] += 1
        lines.append(
            f"| {surface['surfaceId']} | {counts['positive']} | {counts['negative']} | {counts['boundary']} | {counts['capability']} |"
        )
    return "\n".join(lines)


def render_capability_matrix(surface_inventory: list[dict[str, object]]) -> str:
    lines = [
        "| Surface ID | Linked Capabilities | Case Count |",
        "|------------|---------------------|------------|",
    ]
    for surface in surface_inventory:
        capability_names = ", ".join(
            str(item.get("name", "unknown")) for item in surface["linkedCapabilities"]
        ) or "(none)"
        lines.append(
            f"| {surface['surfaceId']} | {capability_names} | {len(surface.get('generatedCases', []))} |"
        )
    return "\n".join(lines)


def render_case(case: dict[str, object]) -> str:
    lines = [
        f"#### {case['caseId']}: {case['title']}",
        f"- surface-id: `{case['surfaceId']}`",
        f"- capability-id: `{case['capabilityId']}`",
        f"- category: `{case['category']}`",
        f"- execution-environment: `{case['minimumMode']}`",
        f"- primary-executor: `{case['primaryExecutor']}`",
        f"- objective: {case['objective']}",
        "- steps:",
    ]
    lines.extend(f"  - {step}" for step in case["steps"])
    lines.append("- expected-results:")
    lines.extend(f"  - {item}" for item in case["expected"])
    return "\n".join(lines)


def build_test_design_markdown(
    fingerprint: dict[str, object], surface_inventory: list[dict[str, object]]
) -> str:
    title = str(fingerprint.get("packageName", "unknown"))
    lines = [
        f"# TEST-DESIGN - {title}",
        "",
        "## Test Strategy",
        "",
        "- Flow A must split execution by real product surfaces instead of flattening a mixed target into one skill.",
        "- Every surface must include positive, negative, and boundary coverage at minimum.",
        "- `SURFACE-EXECUTION-PLAN.json` is the stage-five execution input; no surface may be skipped silently.",
        "",
        "## Surface Inventory",
        "",
        render_surface_inventory(surface_inventory),
        "",
        "## Branch Coverage Matrix",
        "",
        render_branch_matrix(surface_inventory),
        "",
        "## Test Cases",
        "",
    ]

    for surface in surface_inventory:
        lines.append(f"### {surface['surfaceId']} - {surface['label']} (`{surface['identifier']}`)")
        lines.append("")
        lines.append(f"- source: {render_source(surface.get('source'))}")
        lines.append(f"- focus-areas: {', '.join(surface['focusAreas'])}")
        lines.append(f"- security-focus: {', '.join(surface['securityFocus'])}")
        lines.append("")
        for case in surface.get("generatedCases", []):
            lines.append(render_case(case))
            lines.append("")

    lines.extend(
        [
            "## Capability x Surface Coverage Matrix",
            "",
            render_capability_matrix(surface_inventory),
            "",
            "## Stage-Five Execution Requirements",
            "",
            "- `skill-tester` must execute every surface listed in `SURFACE-EXECUTION-PLAN.json`.",
            "- `security-tester` must review each surface against its `securityFocus`, not just repository prose.",
            "- Any surface that only reaches trace or probe-only evidence must not be reported as a functional pass.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fingerprint", required=True, help="Path to PRODUCT-FINGERPRINT.json")
    parser.add_argument("--spec", required=True, help="Path to SPEC.md")
    parser.add_argument("--consistency-review", required=True, help="Path to SPEC-CONSISTENCY-REVIEW.md")
    parser.add_argument("--output-dir", required=True, help="Directory for stage-three artifacts")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    fingerprint_path = Path(args.fingerprint).expanduser().resolve()
    spec_path = Path(args.spec).expanduser().resolve()
    review_path = Path(args.consistency_review).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    for path in (fingerprint_path, spec_path, review_path):
        if not path.exists():
            raise SystemExit(f"ERROR: required input does not exist: {path}")

    _ = read_text(spec_path)
    ensure_passed_review(review_path)
    fingerprint = load_json(fingerprint_path)

    surface_inventory = build_surface_inventory(fingerprint)
    execution_plan = build_execution_plan(fingerprint, surface_inventory)
    test_design = build_test_design_markdown(fingerprint, surface_inventory)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_text(output_dir / "TEST-DESIGN.md", test_design + "\n")
    write_text(
        output_dir / "SURFACE-EXECUTION-PLAN.json",
        json.dumps(execution_plan, ensure_ascii=False, indent=2) + "\n",
    )

    print(f"OUTPUT_DIR={output_dir}")
    print(f"TEST_DESIGN={output_dir / 'TEST-DESIGN.md'}")
    print(f"SURFACE_EXECUTION_PLAN={output_dir / 'SURFACE-EXECUTION-PLAN.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
