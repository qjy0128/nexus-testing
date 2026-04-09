#!/usr/bin/env python3
"""Generate a machine-readable stage/subagent dispatch plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sandbox_skill_invoke.core import write_text


FLOW_ALIASES = {
    "a": "A",
    "flow-a": "A",
    "skill": "A",
    "skill-testing": "A",
    "b": "B",
    "flow-b": "B",
    "web": "B",
    "web-api": "B",
    "web-api-testing": "B",
    "c": "C",
    "flow-c": "C",
    "android": "C",
    "android-testing": "C",
    "d": "D",
    "flow-d": "D",
    "mcp": "D",
    "mcp-testing": "D",
}

FLOW_NAMES = {
    "A": "Skill Testing",
    "B": "Web/API Testing",
    "C": "Android Testing",
    "D": "MCP Testing",
}

ROLE_META = {
    "environment-checker": {"file": "roles/environment-checker.md", "type": "executor"},
    "requirement-analyst": {"file": "roles/requirement-analyst.md", "type": "executor"},
    "spec-consistency-validator": {"file": "roles/spec-consistency-validator.md", "type": "validator"},
    "quality-assessor": {"file": "roles/quality-assessor.md", "type": "validator"},
    "test-designer": {"file": "roles/test-designer.md", "type": "executor"},
    "test-case-evaluator": {"file": "roles/test-case-evaluator.md", "type": "validator"},
    "skill-tester": {"file": "roles/skill-tester.md", "type": "executor"},
    "security-tester": {"file": "roles/security-tester.md", "type": "executor"},
    "functional-tester": {"file": "roles/functional-tester.md", "type": "executor"},
    "compatibility-tester": {"file": "roles/compatibility-tester.md", "type": "executor"},
    "performance-tester": {"file": "roles/performance-tester.md", "type": "executor"},
    "accessibility-auditor": {"file": "roles/accessibility-auditor.md", "type": "executor"},
    "reality-checker": {"file": "roles/reality-checker.md", "type": "executor"},
    "mcp-tester": {"file": "roles/mcp-tester.md", "type": "executor"},
    "evidence-collector": {"file": "roles/evidence-collector.md", "type": "validator"},
    "defect-analyst": {"file": "roles/defect-analyst.md", "type": "validator"},
    "report-integrator": {"file": "roles/report-integrator.md", "type": "executor"},
    "experience-tester-a": {"file": "roles/experience-tester-a.md", "type": "executor"},
    "experience-tester-b": {"file": "roles/experience-tester-b.md", "type": "executor"},
}


def role_entry(role_id: str, order: int) -> dict[str, object]:
    meta = ROLE_META[role_id]
    return {
        "id": role_id,
        "file": meta["file"],
        "type": meta["type"],
        "order": order,
    }


def serial_stage(
    stage_id: str,
    label: str,
    name: str,
    roles: list[str],
    deliverables: list[str],
    gate: str = "none",
) -> dict[str, object]:
    return {
        "stageId": stage_id,
        "label": label,
        "name": name,
        "dispatchMode": "serial",
        "roles": [role_entry(role_id, index + 1) for index, role_id in enumerate(roles)],
        "deliverables": deliverables,
        "userGate": gate,
    }


def parallel_stage(
    stage_id: str,
    label: str,
    name: str,
    roles: list[str],
    deliverables: list[str],
    gate: str = "none",
    post_roles: list[str] | None = None,
    post_deliverables: list[str] | None = None,
) -> dict[str, object]:
    stage: dict[str, object] = {
        "stageId": stage_id,
        "label": label,
        "name": name,
        "dispatchMode": "parallel",
        "roles": [role_entry(role_id, index + 1) for index, role_id in enumerate(roles)],
        "deliverables": deliverables,
        "userGate": gate,
    }
    if post_roles:
        stage["postStageRoles"] = [role_entry(role_id, index + 1) for index, role_id in enumerate(post_roles)]
    if post_deliverables:
        stage["postStageDeliverables"] = post_deliverables
    return stage


def build_standard_stages(flow_id: str) -> list[dict[str, object]]:
    stage_five_roles = {
        "A": ["skill-tester", "security-tester"],
        "B": ["functional-tester", "compatibility-tester", "security-tester", "performance-tester", "accessibility-auditor"],
        "C": ["functional-tester", "compatibility-tester", "security-tester", "performance-tester", "reality-checker"],
        "D": ["mcp-tester", "security-tester", "performance-tester", "reality-checker"],
    }[flow_id]
    return [
        serial_stage(
            "stage-0",
            "阶段零",
            "环境就绪检查",
            ["environment-checker"],
            ["STAGE-SUBAGENT-PLAN.json", "(in-memory) environment readiness report"],
            gate="confirm",
        ),
        serial_stage(
            "stage-1",
            "阶段一",
            "需求解析 + 规格一致性校验",
            ["requirement-analyst", "spec-consistency-validator"],
            ["PRODUCT-FINGERPRINT.json", "SPEC.md", "SPEC-CONSISTENCY-REVIEW.md"],
        ),
        serial_stage(
            "stage-2",
            "阶段二",
            "质量评估",
            ["quality-assessor"],
            ["PRODUCT-QUALITY-REVIEW.md"],
            gate="approve",
        ),
        serial_stage(
            "stage-3",
            "阶段三",
            "测试设计",
            ["test-designer"],
            ["TEST-DESIGN.md", "SURFACE-EXECUTION-PLAN.json"],
        ),
        serial_stage(
            "stage-4",
            "阶段四",
            "用例评估",
            ["test-case-evaluator"],
            ["TEST-CASE-REVIEW.md"],
            gate="approve",
        ),
        parallel_stage(
            "stage-5",
            "阶段五",
            "并行测试执行",
            stage_five_roles,
            ["TEST-EXECUTION/*.md", "TEST-EXECUTION/SKILL-SURFACE-WORKLIST.md", "TEST-EXECUTION/SURFACE-COVERAGE.json"],
            post_roles=["evidence-collector"],
            post_deliverables=["DEFECTS/evidence-collection.md"],
        ),
        serial_stage(
            "stage-6",
            "阶段六",
            "缺陷分析",
            ["defect-analyst"],
            ["DEFECTS/DEFECT-REPORT.md"],
        ),
        serial_stage(
            "stage-7",
            "阶段七",
            "报告整合",
            ["report-integrator"],
            ["FINAL-TEST-REPORT.md"],
        ),
    ]


def build_flow_b_mode_stages() -> list[dict[str, object]]:
    return [
        serial_stage(
            "b-stage-0",
            "B-阶段零",
            "环境就绪检查",
            ["environment-checker"],
            ["STAGE-SUBAGENT-PLAN.json", "(in-memory) environment readiness report"],
            gate="confirm",
        ),
        serial_stage(
            "b-stage-1",
            "B-阶段一",
            "需求解析",
            ["requirement-analyst"],
            ["SPEC.md"],
        ),
        serial_stage(
            "b-stage-2",
            "B-阶段二",
            "质量评估 + 模式判定",
            ["quality-assessor"],
            ["PRODUCT-QUALITY-REVIEW.md"],
            gate="approve",
        ),
        parallel_stage(
            "b-stage-3",
            "B-阶段三",
            "双边深度体验",
            ["experience-tester-a", "experience-tester-b"],
            ["EXPERIENCE/experience-report-a.md", "EXPERIENCE/experience-report-b.md"],
        ),
        parallel_stage(
            "b-stage-4",
            "B-阶段四",
            "交叉核对",
            ["experience-tester-a", "experience-tester-b"],
            ["EXPERIENCE/cross-check-a-by-b.md", "EXPERIENCE/cross-check-b-by-a.md"],
        ),
        parallel_stage(
            "b-stage-5",
            "B-阶段五",
            "争议复检 + 补充体验",
            ["experience-tester-a", "experience-tester-b"],
            ["EXPERIENCE/experience-report-a.md", "EXPERIENCE/experience-report-b.md"],
        ),
        serial_stage(
            "b-stage-6",
            "B-阶段六",
            "测试设计",
            ["test-designer"],
            ["TEST-DESIGN.md"],
        ),
        serial_stage(
            "b-stage-7",
            "B-阶段七",
            "用例评估",
            ["test-case-evaluator"],
            ["TEST-CASE-REVIEW.md"],
            gate="approve",
        ),
        parallel_stage(
            "b-stage-8",
            "B-阶段八",
            "并行测试执行",
            ["functional-tester", "compatibility-tester", "security-tester", "performance-tester", "accessibility-auditor"],
            ["TEST-EXECUTION/*.md"],
            post_roles=["evidence-collector"],
            post_deliverables=["DEFECTS/evidence-collection.md"],
        ),
        serial_stage(
            "b-stage-9",
            "B-阶段九",
            "缺陷分析",
            ["defect-analyst"],
            ["DEFECTS/DEFECT-REPORT.md"],
        ),
        serial_stage(
            "b-stage-10",
            "B-阶段十",
            "报告整合",
            ["report-integrator"],
            ["FINAL-TEST-REPORT.md"],
        ),
    ]


def normalize_flow(value: str) -> str:
    normalized = FLOW_ALIASES.get(value.strip().lower())
    if not normalized:
        raise ValueError(f"Unsupported flow: {value}")
    return normalized


def normalize_mode(flow_id: str, value: str) -> str:
    normalized = value.strip().lower()
    if flow_id != "B":
        return "standard"
    if normalized in {"a", "standard", "default"}:
        return "standard"
    if normalized in {"b", "experience", "explore"}:
        return "b-mode"
    raise ValueError(f"Unsupported mode for Flow B: {value}")


def build_plan(flow_id: str, mode: str) -> dict[str, object]:
    stages = build_flow_b_mode_stages() if flow_id == "B" and mode == "b-mode" else build_standard_stages(flow_id)
    return {
        "version": 1,
        "flowId": flow_id,
        "flowName": FLOW_NAMES[flow_id],
        "mode": mode,
        "generatedBy": "scripts/generate_stage_subagent_plan.py",
        "orchestrator": {
            "id": "main-agent",
            "type": "orchestrator",
            "responsibilities": [
                "route-flow",
                "spawn-stage-subagents",
                "send-deliverables",
                "request-approval",
                "handle-rejections",
                "advance-stages",
            ],
        },
        "stages": stages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate STAGE-SUBAGENT-PLAN.json for a flow.")
    parser.add_argument("--flow", required=True, help="Flow id or alias: A/B/C/D, skill, web-api, android, mcp")
    parser.add_argument("--mode", default="standard", help="Flow mode. Flow B supports: standard / b")
    parser.add_argument("--output-file", required=True, help="Path to STAGE-SUBAGENT-PLAN.json")
    args = parser.parse_args()

    try:
        flow_id = normalize_flow(args.flow)
        mode = normalize_mode(flow_id, args.mode)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_path = Path(args.output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plan = build_plan(flow_id, mode)
    write_text(output_path, json.dumps(plan, ensure_ascii=False, indent=2) + "\n")

    print(f"STAGE_SUBAGENT_PLAN={output_path}")
    print(f"FLOW_ID={flow_id}")
    print(f"MODE={mode}")
    print(f"STAGE_COUNT={len(plan['stages'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
