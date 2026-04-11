#!/usr/bin/env python3
"""Mock external runtime for nexus_runtime_bridge.py smoke tests."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from _bootstrap import bootstrap_paths

bootstrap_paths()

from nexus_testing.role_metadata import parse_role_doc

ROLE_OUTPUTS = {
    "environment-checker": ["RUNS/{stage_id}/environment-readiness.md"],
    "requirement-analyst": ["PRODUCT-FINGERPRINT.json", "SPEC.md"],
    "spec-consistency-validator": ["SPEC-CONSISTENCY-REVIEW.md"],
    "quality-assessor": ["PRODUCT-QUALITY-REVIEW.md"],
    "test-designer": ["TEST-DESIGN.md", "SURFACE-EXECUTION-PLAN.json"],
    "test-case-evaluator": ["TEST-CASE-REVIEW.md"],
    "skill-tester": [
        "TEST-EXECUTION/skill-results.md",
        "TEST-EXECUTION/SKILL-SURFACE-WORKLIST.md",
        "TEST-EXECUTION/SURFACE-COVERAGE.json",
    ],
    "security-tester": ["TEST-EXECUTION/security-results.md"],
    "functional-tester": ["TEST-EXECUTION/functional-results.md"],
    "compatibility-tester": ["TEST-EXECUTION/compatibility-results.md"],
    "performance-tester": ["TEST-EXECUTION/performance-results.md"],
    "accessibility-auditor": ["TEST-EXECUTION/accessibility-results.md"],
    "reality-checker": ["TEST-EXECUTION/reality-results.md"],
    "mcp-tester": ["TEST-EXECUTION/mcp-results.md"],
    "evidence-collector": ["DEFECTS/evidence-collection.md"],
    "defect-analyst": ["DEFECTS/DEFECT-REPORT.md"],
    "report-integrator": ["FINAL-TEST-REPORT.md"],
    "experience-tester-a": [
        "EXPERIENCE/experience-report-a.md",
        "EXPERIENCE/cross-check-b-by-a.md",
    ],
    "experience-tester-b": [
        "EXPERIENCE/experience-report-b.md",
        "EXPERIENCE/cross-check-a-by-b.md",
    ],
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def role_file(role_id: str) -> Path:
    return PROJECT_ROOT / "roles" / f"{role_id}.md"


def default_surface_plan(stage_id: str) -> dict[str, object]:
    return {
        "generatedBy": "mock-role-runtime",
        "stageId": stage_id,
        "surfaces": [
            {
                "surfaceId": "SURFACE-01",
                "title": "Mock skill surface",
                "kind": "skill",
                "minimumMode": "trace",
                "testCaseIds": ["TC-01"],
            }
        ],
    }


def write_role_output(path: Path, role_id: str, stage_id: str) -> None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = {"generatedBy": role_id, "stageId": stage_id, "status": "mock"}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    path.write_text(
        "\n".join(
            [
                "# Mock Output",
                "",
                f"role={role_id}",
                f"stage={stage_id}",
                "This output contains substantive mock content for smoke tests.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_structured_markdown(path: Path, title: str, sections: list[tuple[str, str]]) -> None:
    lines = [f"# {title}", ""]
    for heading, content in sections:
        lines.extend([f"## {heading}", content, ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_quality_assessor_output(report_dir: Path) -> list[str]:
    path = report_dir / "PRODUCT-QUALITY-REVIEW.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = parse_role_doc(role_file("quality-assessor"))
    headings = list(metadata.get("minimumOutput", []))
    sections = [
        (headings[0], "The current specification defines the main workflow, key inputs, and expected artifacts for this target."),
        (headings[1], "Most requirements can be translated into executable checks, but live delivery confirmation still needs explicit runtime evidence."),
        (headings[2], "The main risk is silent downgrade during execution when a missing tool is replaced with a weaker path."),
        (headings[3], "Keep Flow A on the standard runner path and escalate to takeover whenever the runtime cannot finish real execution."),
        (headings[4], "No rollback is required in this mock scenario because the required upstream artifacts are already present."),
    ]
    write_structured_markdown(path, "Mock Product Quality Review", sections)
    return [str(path)]


def write_test_designer_outputs(report_dir: Path, stage_id: str) -> list[str]:
    design_path = report_dir / "TEST-DESIGN.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = parse_role_doc(role_file("test-designer"))
    headings = list(metadata.get("minimumOutput", []))
    sections = [
        (headings[0], "Start with the primary skill surface, then expand to boundary and recovery scenarios after the baseline path is stable."),
        (headings[1], "TC-01 covers the primary acceptance path with executable evidence and a clear expected outcome."),
        (headings[2], "The branch matrix includes success, validation failure, and runtime degradation branches."),
        (headings[3], "Capability coverage is mapped across trigger, execution, evidence, and delivery dimensions."),
        (headings[4], "Use one nominal payload, one malformed payload, and one boundary payload with long text input."),
        (headings[5], "Reuse the standard surface worklist and validator artifacts instead of bespoke case scaffolding."),
        (headings[6], "If live runtime or verifier evidence is unavailable, stop the stage and escalate to takeover instead of weakening the verdict."),
    ]
    write_structured_markdown(design_path, "Mock Test Design", sections)

    plan_path = report_dir / "SURFACE-EXECUTION-PLAN.json"
    plan_path.write_text(json.dumps(default_surface_plan(stage_id), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return [str(design_path), str(plan_path)]


def write_skill_tester_outputs(report_dir: Path, stage_id: str) -> list[str]:
    plan_path = report_dir / "SURFACE-EXECUTION-PLAN.json"
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            plan = default_surface_plan(stage_id)
    else:
        plan = default_surface_plan(stage_id)
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    surfaces = plan.get("surfaces", []) if isinstance(plan, dict) else []
    if not isinstance(surfaces, list) or not surfaces:
        surfaces = default_surface_plan(stage_id)["surfaces"]

    execution_dir = report_dir / "TEST-EXECUTION"
    execution_dir.mkdir(parents=True, exist_ok=True)

    worklist_path = execution_dir / "SKILL-SURFACE-WORKLIST.md"
    worklist_lines = ["# Mock Surface Worklist", ""]
    result_lines = ["# TEST-EXECUTION/skill-results", ""]
    coverage_surfaces: list[dict[str, object]] = []

    for index, surface in enumerate(surfaces, start=1):
        if not isinstance(surface, dict):
            continue
        surface_id = str(surface.get("surfaceId") or f"SURFACE-{index:02d}")
        case_ids = [str(item) for item in surface.get("testCaseIds", []) if str(item).strip()] or [f"TC-{index:02d}"]
        worklist_lines.append(f"- {surface_id}")
        evidence_path = execution_dir / f"{surface_id}.json"
        result_lines.extend(
            [
                f"### Mock Surface {index}",
                f"- surface-id: `{surface_id}`",
                "- execution-level: `trace`",
                "- status: `passed`",
                f"- evidence: `{evidence_path}`",
                f"- notes: `case-coverage={len(case_ids)}/{len(case_ids)}; executed-case-count={len(case_ids)}`",
                f"- executed-case-ids: `{', '.join(case_ids)}`",
                "",
            ]
        )
        coverage_surfaces.append(
            {
                "surfaceId": surface_id,
                "status": "passed",
                "executionLevel": "trace",
                "requiredCaseIds": case_ids,
                "executedCaseCount": len(case_ids),
                "executedCaseIds": case_ids,
                "caseResults": [
                    {
                        "caseId": case_id,
                        "status": "passed",
                        "evidence": [str(evidence_path)],
                    }
                    for case_id in case_ids
                ],
            }
        )
        evidence_path.write_text(
            json.dumps({"surfaceId": surface_id, "stageId": stage_id, "status": "mock"}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    worklist_path.write_text("\n".join(worklist_lines) + "\n", encoding="utf-8")
    skill_results_path = execution_dir / "skill-results.md"
    skill_results_path.write_text("\n".join(result_lines), encoding="utf-8")
    coverage_path = execution_dir / "SURFACE-COVERAGE.json"
    coverage_path.write_text(
        json.dumps({"generatedBy": "mock-role-runtime", "stageId": stage_id, "surfaces": coverage_surfaces}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (execution_dir / "skill-results.meta.json").write_text(
        json.dumps(
            {
                "generatedBy": "scripts/run_flow_a_skill_execution.py",
                "runner": "flow-a-stage5",
                "executionProfile": "internal-fast",
                "strictReal": False,
                "validatedBy": "scripts/validate_flow_a_skill_results.py",
                "surfacePlan": str(plan_path.resolve()),
                "skillResults": str(skill_results_path.resolve()),
                "surfaceCoverage": str(coverage_path.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return [str(skill_results_path), str(worklist_path), str(coverage_path)]


def write_report_integrator_output(report_dir: Path) -> list[str]:
    path = report_dir / "FINAL-TEST-REPORT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = parse_role_doc(role_file("report-integrator"))
    headings = list(metadata.get("minimumOutput", []))
    sections = [
        (headings[0], "This report consolidates environment readiness, specification quality, design outputs, execution evidence, and residual risks."),
        (headings[1], "All mocked dimensions completed with standardized artifacts and an explicit delivery record."),
        (headings[2], "No blocking product defects were found in the mock path, but runtime shortcut detection remains under active review."),
        (headings[3], "Residual risk remains when live delivery confirmation depends on external channels or runtime availability."),
        (headings[4], "Release is acceptable for the mock scenario when takeover rules and delivery receipt checks remain enabled."),
    ]
    write_structured_markdown(path, "Mock Final Test Report", sections)
    return [str(path)]


def build_success_result(role_id: str, created: list[str]) -> dict[str, object]:
    result: dict[str, object] = {
        "resultFile": created[0] if created else None,
        "note": f"mock runtime completed for {role_id}",
        "producedArtifactPaths": created,
    }
    if role_id == "skill-tester":
        result["executionMethod"] = "scripts/run_flow_a_skill_execution.py"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-file", required=True)
    parser.add_argument("--prompt-file")
    parser.add_argument("--fail-role")
    parser.add_argument("--takeover-role")
    parser.add_argument("--blocked-role")
    parser.add_argument("--policy-fallback-role")
    parser.add_argument("--weak-role")
    parser.add_argument("--stall-role")
    parser.add_argument("--stall-seconds", type=int, default=5)
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    role_id = str(payload["roleId"])
    stage_id = str(payload["stageId"])
    report_dir = Path(str(payload["reportDir"]))

    if args.fail_role and args.fail_role == role_id:
        print(f"mock failure for {role_id}", file=sys.stderr)
        return 7

    if args.takeover_role and args.takeover_role == role_id:
        print(
            json.dumps(
                {
                    "resultFile": None,
                    "note": f"mock runtime requires main-agent takeover for {role_id}",
                    "status": "blocked",
                    "needsMainAgentTakeover": True,
                    "blockers": ["mock environment cannot finish this role"],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.blocked_role and args.blocked_role == role_id:
        print(
            json.dumps(
                {
                    "resultFile": None,
                    "note": f"mock runtime blocked for {role_id} because gateway is unavailable",
                    "status": "blocked",
                    "blockers": ["gateway unavailable"],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.stall_role and args.stall_role == role_id:
        time.sleep(max(1, int(args.stall_seconds)))
        print(json.dumps({"resultFile": None, "note": f"stall mock runtime eventually resumed for {role_id}"}, ensure_ascii=False))
        return 0

    if args.weak_role and args.weak_role == role_id:
        outputs = ROLE_OUTPUTS.get(role_id, [])
        created: list[str] = []
        for relative in outputs:
            resolved = report_dir / relative.format(stage_id=stage_id)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            write_role_output(resolved, role_id, stage_id)
            created.append(str(resolved))
        print(json.dumps({"resultFile": created[0] if created else None, "note": f"weak mock runtime completed for {role_id}"}, ensure_ascii=False))
        return 0

    if role_id == "quality-assessor":
        created = write_quality_assessor_output(report_dir)
    elif role_id == "test-designer":
        created = write_test_designer_outputs(report_dir, stage_id)
    elif role_id == "skill-tester":
        created = write_skill_tester_outputs(report_dir, stage_id)
    elif role_id == "report-integrator":
        created = write_report_integrator_output(report_dir)
    else:
        outputs = ROLE_OUTPUTS.get(role_id, [])
        created = []
        for relative in outputs:
            resolved = report_dir / relative.format(stage_id=stage_id)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            write_role_output(resolved, role_id, stage_id)
            created.append(str(resolved))

    result = build_success_result(role_id, created)
    if args.policy_fallback_role and args.policy_fallback_role == role_id:
        result["note"] = f"webReader unavailable; switched to web_fetch fallback for {role_id}"
        result["blockers"] = ["webReader unavailable", "web_fetch fallback"]
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
