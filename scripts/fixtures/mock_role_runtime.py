#!/usr/bin/env python3
"""Mock external runtime for nexus_runtime_bridge.py smoke tests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
    path.write_text(f"# Mock Output\n\nrole={role_id}\nstage={stage_id}\n", encoding="utf-8")


def write_quality_assessor_output(report_dir: Path, stage_id: str) -> list[str]:
    path = report_dir / "PRODUCT-QUALITY-REVIEW.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# Mock Product Quality Review",
                "",
                "## 规格完整性",
                "- mock",
                "",
                "## 可测试性",
                "- mock",
                "",
                "## 主要风险",
                "- mock",
                "",
                "## 测试设计建议",
                "- mock",
                "",
                "## 结论与是否需要重新进入前一阶段",
                "- mock",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return [str(path)]


def write_test_designer_outputs(report_dir: Path, stage_id: str) -> list[str]:
    design_path = report_dir / "TEST-DESIGN.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text(
        "\n".join(
            [
                "# Mock Test Design",
                "",
                "## 测试策略",
                "- mock",
                "",
                "## 测试用例集",
                "- TC-01",
                "",
                "## 逻辑分支覆盖矩阵",
                "- mock",
                "",
                "## 能力 × 维度覆盖矩阵（Flow A）",
                "- mock",
                "",
                "## 测试数据方案（正常/异常/边界）",
                "- mock",
                "",
                "## 测试夹具方案（如适用）",
                "- mock",
                "",
                "## 风险与备注",
                "- mock",
                "",
            ]
        ),
        encoding="utf-8",
    )

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
        case_ids = [str(item) for item in surface.get("testCaseIds", []) if str(item).strip()]
        if not case_ids:
            case_ids = [f"TC-{index:02d}"]
        worklist_lines.append(f"- {surface_id}")
        result_lines.extend(
            [
                f"### Mock Surface {index}",
                f"- surface-id: `{surface_id}`",
                "- execution-level: `trace`",
                "- status: `passed`",
                f"- evidence: `{execution_dir / f'{surface_id}.json'}`",
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
                        "evidence": [str(execution_dir / f"{surface_id}.json")],
                    }
                    for case_id in case_ids
                ],
            }
        )
        (execution_dir / f"{surface_id}.json").write_text(
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
    return [str(skill_results_path), str(worklist_path), str(coverage_path)]


def write_report_integrator_output(report_dir: Path, stage_id: str) -> list[str]:
    path = report_dir / "FINAL-TEST-REPORT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# Mock Final Test Report",
                "",
                "## 测试概览",
                "- mock",
                "",
                "## 各维度结果",
                "- mock",
                "",
                "## 缺陷摘要",
                "- mock",
                "",
                "## 未覆盖范围与残余风险",
                "- mock",
                "",
                "## 发布建议",
                "- mock",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return [str(path)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-file", required=True)
    parser.add_argument("--prompt-file")
    parser.add_argument("--fail-role")
    parser.add_argument("--takeover-role")
    parser.add_argument("--blocked-role")
    parser.add_argument("--weak-role")
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

    if args.weak_role and args.weak_role == role_id:
        outputs = ROLE_OUTPUTS.get(role_id, [])
        created = []
        for relative in outputs:
            resolved = report_dir / relative.format(stage_id=stage_id)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            write_role_output(resolved, role_id, stage_id)
            created.append(str(resolved))
        print(json.dumps({"resultFile": created[0] if created else None, "note": f"weak mock runtime completed for {role_id}"}, ensure_ascii=False))
        return 0

    if role_id == "quality-assessor":
        created = write_quality_assessor_output(report_dir, stage_id)
    elif role_id == "test-designer":
        created = write_test_designer_outputs(report_dir, stage_id)
    elif role_id == "skill-tester":
        created = write_skill_tester_outputs(report_dir, stage_id)
    elif role_id == "report-integrator":
        created = write_report_integrator_output(report_dir, stage_id)
    else:
        outputs = ROLE_OUTPUTS.get(role_id, [])
        created = []
        for relative in outputs:
            resolved = report_dir / relative.format(stage_id=stage_id)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            write_role_output(resolved, role_id, stage_id)
            created.append(str(resolved))

    result = {
        "resultFile": created[0] if created else None,
        "note": f"mock runtime completed for {role_id}",
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
