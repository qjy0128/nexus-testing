"""Contract and role validators extracted from validate-framework.py."""

from __future__ import annotations

import re
from pathlib import Path

from sandbox_skill_invoke.core import read_text

ROOT = Path(__file__).resolve().parents[1]

ROLE_REF_PATTERN = re.compile(r"`roles/([^`]+\.md)`")
SEMVER_PATTERN = re.compile(r"v\d+\.\d+\.\d+")
MESSAGE_SEND_PATTERN = re.compile(r'message\(action:\s*"send"(?P<body>.*?)\)', re.DOTALL)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def validate_definition_consistency() -> list[str]:
    issues: list[str] = []
    definitions_text = read_text(ROOT / "DEFINITIONS.md")
    approval_text = read_text(ROOT / "reference-approval-mechanism.md")
    readme_text = read_text(ROOT / "README.md")
    skill_text = read_text(ROOT / "SKILL.md")

    if "approval-records.json" in approval_text and "approval-records.json" not in definitions_text:
        issues.append(
            "DEFINITIONS.md is missing approval-records.json referenced by reference-approval-mechanism.md"
        )
    if ".nexus-hmac-salt" in readme_text:
        issues.append("README.md still references deprecated .nexus-hmac-salt runtime state")
    if any(token in approval_text for token in ("HMAC", ".nexus-hmac-salt", '"signature"')):
        issues.append(
            "reference-approval-mechanism.md still contains deprecated HMAC/signature requirements"
        )
    if "HMAC" in skill_text:
        issues.append("SKILL.md still contains deprecated HMAC wording")
    if (ROOT / "roles" / "compatibility-tester-skill.md").exists():
        issues.append(
            "roles/compatibility-tester-skill.md should be archived outside the active roles directory"
        )
    if "PRODUCT-FINGERPRINT.json" not in definitions_text:
        issues.append("DEFINITIONS.md is missing PRODUCT-FINGERPRINT.json in the stage outputs")
    if "SPEC-CONSISTENCY-REVIEW.md" not in definitions_text:
        issues.append("DEFINITIONS.md is missing SPEC-CONSISTENCY-REVIEW.md in the stage outputs")
    if "STAGE-SUBAGENT-PLAN.json" not in definitions_text:
        issues.append("DEFINITIONS.md is missing STAGE-SUBAGENT-PLAN.json in the stage outputs")

    return issues


def validate_stage_subagent_plan_contract() -> list[str]:
    issues: list[str] = []
    definitions_text = read_text(ROOT / "DEFINITIONS.md")
    readme_text = read_text(ROOT / "README.md")
    skill_text = read_text(ROOT / "SKILL.md")
    recovery_text = read_text(ROOT / "reference-recovery.md")

    generator = ROOT / "scripts" / "generate_stage_subagent_plan.py"
    test_script = ROOT / "scripts" / "test_stage_subagent_plan.py"
    if not generator.exists():
        issues.append("scripts/generate_stage_subagent_plan.py is missing")
    if not test_script.exists():
        issues.append("scripts/test_stage_subagent_plan.py is missing")
    if "STAGE-SUBAGENT-PLAN.json" not in readme_text:
        issues.append("README.md is missing STAGE-SUBAGENT-PLAN.json guidance")
    if "generate_stage_subagent_plan.py" not in skill_text:
        issues.append("SKILL.md is missing generate_stage_subagent_plan.py guidance")
    if "STAGE-SUBAGENT-PLAN.json" not in recovery_text:
        issues.append("reference-recovery.md is missing STAGE-SUBAGENT-PLAN.json recovery guidance")
    if "generate STAGE-SUBAGENT-PLAN.json" not in definitions_text and "生成 STAGE-SUBAGENT-PLAN.json" not in definitions_text:
        issues.append("DEFINITIONS.md is missing the stage-zero stage-subagent-plan generation rule")

    return issues


def validate_stage_executor_contract() -> list[str]:
    issues: list[str] = []
    readme_text = read_text(ROOT / "README.md")
    skill_text = read_text(ROOT / "SKILL.md")
    definitions_text = read_text(ROOT / "DEFINITIONS.md")
    recovery_text = read_text(ROOT / "reference-recovery.md")

    executor = ROOT / "scripts" / "nexus_stage_executor.py"
    test_script = ROOT / "scripts" / "test_nexus_stage_executor.py"
    if not executor.exists():
        issues.append("scripts/nexus_stage_executor.py is missing")
    if not test_script.exists():
        issues.append("scripts/test_nexus_stage_executor.py is missing")
    if "nexus_stage_executor.py" not in readme_text:
        issues.append("README.md is missing nexus_stage_executor.py guidance")
    if "nexus_stage_executor.py" not in skill_text:
        issues.append("SKILL.md is missing nexus_stage_executor.py guidance")
    if "dispatch" not in readme_text:
        issues.append("README.md is missing dispatch guidance for nexus_stage_executor.py")
    if "dispatch" not in skill_text:
        issues.append("SKILL.md is missing dispatch guidance for nexus_stage_executor.py")
    if "bundle-dispatch" not in readme_text:
        issues.append("README.md is missing bundle-dispatch guidance for nexus_stage_executor.py")
    if "bundle-dispatch" not in skill_text:
        issues.append("SKILL.md is missing bundle-dispatch guidance for nexus_stage_executor.py")
    if "stage-transition-log.json" not in definitions_text:
        issues.append("DEFINITIONS.md is missing stage-transition-log.json contract")
    if "approval-records.json" not in recovery_text:
        issues.append("reference-recovery.md is missing approval-records.json recovery contract")
    return issues


def validate_dispatch_runner_contract() -> list[str]:
    issues: list[str] = []
    readme_text = read_text(ROOT / "README.md")
    skill_text = read_text(ROOT / "SKILL.md")

    runner = ROOT / "scripts" / "nexus_dispatch_runner.py"
    test_script = ROOT / "scripts" / "test_nexus_dispatch_runner.py"
    if not runner.exists():
        issues.append("scripts/nexus_dispatch_runner.py is missing")
    if not test_script.exists():
        issues.append("scripts/test_nexus_dispatch_runner.py is missing")
    if "nexus_dispatch_runner.py" not in readme_text:
        issues.append("README.md is missing nexus_dispatch_runner.py guidance")
    if "nexus_dispatch_runner.py" not in skill_text:
        issues.append("SKILL.md is missing nexus_dispatch_runner.py guidance")
    if "bundle-dispatch" not in skill_text:
        issues.append("SKILL.md is missing bundle-dispatch bridge guidance")
    return issues


def validate_runtime_bridge_contract() -> list[str]:
    issues: list[str] = []
    readme_text = read_text(ROOT / "README.md")
    skill_text = read_text(ROOT / "SKILL.md")

    runner = ROOT / "scripts" / "nexus_runtime_bridge.py"
    test_script = ROOT / "scripts" / "test_nexus_runtime_bridge.py"
    if not runner.exists():
        issues.append("scripts/nexus_runtime_bridge.py is missing")
    if not test_script.exists():
        issues.append("scripts/test_nexus_runtime_bridge.py is missing")
    if "nexus_runtime_bridge.py" not in readme_text:
        issues.append("README.md is missing nexus_runtime_bridge.py guidance")
    if "nexus_runtime_bridge.py" not in skill_text:
        issues.append("SKILL.md is missing nexus_runtime_bridge.py guidance")
    if "runtime-config" not in readme_text:
        issues.append("README.md is missing runtime-config guidance for nexus_runtime_bridge.py")
    if "runtime-config" not in skill_text:
        issues.append("SKILL.md is missing runtime-config guidance for nexus_runtime_bridge.py")
    return issues


def validate_claude_runtime_contract() -> list[str]:
    issues: list[str] = []
    readme_text = read_text(ROOT / "README.md")
    skill_text = read_text(ROOT / "SKILL.md")

    adapter = ROOT / "scripts" / "nexus_claude_role_runtime.py"
    generator = ROOT / "scripts" / "generate_runtime_bridge_config.py"
    adapter_test = ROOT / "scripts" / "test_nexus_claude_role_runtime.py"
    generator_test = ROOT / "scripts" / "test_generate_runtime_bridge_config.py"
    if not adapter.exists():
        issues.append("scripts/nexus_claude_role_runtime.py is missing")
    if not generator.exists():
        issues.append("scripts/generate_runtime_bridge_config.py is missing")
    if not adapter_test.exists():
        issues.append("scripts/test_nexus_claude_role_runtime.py is missing")
    if not generator_test.exists():
        issues.append("scripts/test_generate_runtime_bridge_config.py is missing")
    if "nexus_claude_role_runtime.py" not in readme_text:
        issues.append("README.md is missing nexus_claude_role_runtime.py guidance")
    if "generate_runtime_bridge_config.py" not in readme_text:
        issues.append("README.md is missing generate_runtime_bridge_config.py guidance")
    if "nexus_claude_role_runtime.py" not in skill_text:
        issues.append("SKILL.md is missing nexus_claude_role_runtime.py guidance")
    if "generate_runtime_bridge_config.py" not in skill_text:
        issues.append("SKILL.md is missing generate_runtime_bridge_config.py guidance")
    return issues


def validate_openclaw_runtime_contract() -> list[str]:
    issues: list[str] = []
    readme_text = read_text(ROOT / "README.md")
    skill_text = read_text(ROOT / "SKILL.md")

    adapter = ROOT / "scripts" / "nexus_openclaw_role_runtime.py"
    test_script = ROOT / "scripts" / "test_nexus_openclaw_role_runtime.py"
    fixture = ROOT / "scripts" / "fixtures" / "mock_openclaw_cli.py"
    if not adapter.exists():
        issues.append("scripts/nexus_openclaw_role_runtime.py is missing")
    if not test_script.exists():
        issues.append("scripts/test_nexus_openclaw_role_runtime.py is missing")
    if not fixture.exists():
        issues.append("scripts/fixtures/mock_openclaw_cli.py is missing")
    if "nexus_openclaw_role_runtime.py" not in readme_text:
        issues.append("README.md is missing nexus_openclaw_role_runtime.py guidance")
    if "nexus_openclaw_role_runtime.py" not in skill_text:
        issues.append("SKILL.md is missing nexus_openclaw_role_runtime.py guidance")
    if "OpenClaw" not in skill_text and "openclaw" not in skill_text:
        issues.append("SKILL.md is missing explicit OpenClaw targeting guidance")
    return issues


def validate_openclaw_demo_contract() -> list[str]:
    issues: list[str] = []
    readme_text = read_text(ROOT / "README.md")
    skill_text = read_text(ROOT / "SKILL.md")

    demo = ROOT / "scripts" / "run_openclaw_stage_demo.py"
    test_script = ROOT / "scripts" / "test_run_openclaw_stage_demo.py"
    if not demo.exists():
        issues.append("scripts/run_openclaw_stage_demo.py is missing")
    if not test_script.exists():
        issues.append("scripts/test_run_openclaw_stage_demo.py is missing")
    if "run_openclaw_stage_demo.py" not in readme_text:
        issues.append("README.md is missing run_openclaw_stage_demo.py guidance")
    if "run_openclaw_stage_demo.py" not in skill_text:
        issues.append("SKILL.md is missing run_openclaw_stage_demo.py guidance")
    return issues


def validate_flow_a_fact_contract() -> list[str]:
    issues: list[str] = []

    flow_text = read_text(ROOT / "flows" / "skill-testing.md")
    requirement_text = read_text(ROOT / "roles" / "requirement-analyst.md")
    designer_text = read_text(ROOT / "roles" / "test-designer.md")
    evaluator_text = read_text(ROOT / "roles" / "test-case-evaluator.md")
    reference_text = read_text(ROOT / "reference-flow-skill.md")
    skill_text = read_text(ROOT / "SKILL.md")

    if "PRODUCT-FINGERPRINT.json" not in flow_text or "SPEC-CONSISTENCY-REVIEW.md" not in flow_text:
        issues.append("flows/skill-testing.md is missing the stage-one fact contract")
    if "PRODUCT-FINGERPRINT.json" not in requirement_text:
        issues.append("roles/requirement-analyst.md is missing PRODUCT-FINGERPRINT.json output requirements")
    if "真实入口" not in designer_text:
        issues.append("roles/test-designer.md is missing the real-entry test design rule")
    if "事实一致性" not in evaluator_text:
        issues.append("roles/test-case-evaluator.md is missing the fact-consistency review rule")
    if "阶段一事实指纹模板" not in reference_text:
        issues.append("reference-flow-skill.md is missing the stage-one fingerprint template")
    if "静态分析只能作为补充审查" not in skill_text:
        issues.append("SKILL.md is missing the static-analysis outcome restriction")
    if not (ROOT / "roles" / "spec-consistency-validator.md").exists():
        issues.append("roles/spec-consistency-validator.md is missing")

    return issues


def validate_flow_a_surface_plan_contract() -> list[str]:
    issues: list[str] = []

    definitions_text = read_text(ROOT / "DEFINITIONS.md")
    flow_text = read_text(ROOT / "flows" / "skill-testing.md")
    skill_text = read_text(ROOT / "SKILL.md")
    readme_text = read_text(ROOT / "README.md")
    designer_text = read_text(ROOT / "roles" / "test-designer.md")
    evaluator_text = read_text(ROOT / "roles" / "test-case-evaluator.md")
    tester_text = read_text(ROOT / "roles" / "skill-tester.md")
    reference_text = read_text(ROOT / "reference-flow-skill.md")

    if "SURFACE-EXECUTION-PLAN.json" not in definitions_text:
        issues.append("DEFINITIONS.md is missing SURFACE-EXECUTION-PLAN.json in the stage outputs")
    if "SURFACE-EXECUTION-PLAN.json" not in flow_text:
        issues.append("flows/skill-testing.md is missing the stage-three surface execution plan output")
    if "SURFACE-EXECUTION-PLAN.json" not in skill_text:
        issues.append("SKILL.md is missing the stage-three surface execution plan contract")
    if "SURFACE-EXECUTION-PLAN.json" not in readme_text:
        issues.append("README.md is missing SURFACE-EXECUTION-PLAN.json in the documented outputs")
    if "SURFACE-EXECUTION-PLAN.json" not in designer_text:
        issues.append("roles/test-designer.md is missing SURFACE-EXECUTION-PLAN.json output requirements")
    if "SURFACE-EXECUTION-PLAN.json" not in evaluator_text:
        issues.append("roles/test-case-evaluator.md is missing SURFACE-EXECUTION-PLAN.json review requirements")
    if "SURFACE-EXECUTION-PLAN.json" not in tester_text:
        issues.append("roles/skill-tester.md is missing SURFACE-EXECUTION-PLAN.json execution requirements")
    if "真实入口表面" not in reference_text and "真实入口表面" not in flow_text:
        issues.append("Flow A docs are missing the real-surface wording for stage-three planning")

    return issues


def validate_flow_a_surface_execution_contract() -> list[str]:
    issues: list[str] = []

    definitions_text = read_text(ROOT / "DEFINITIONS.md")
    flow_text = read_text(ROOT / "flows" / "skill-testing.md")
    skill_text = read_text(ROOT / "SKILL.md")
    readme_text = read_text(ROOT / "README.md")
    tester_text = read_text(ROOT / "roles" / "skill-tester.md")
    evidence_text = read_text(ROOT / "roles" / "evidence-collector.md")
    report_text = read_text(ROOT / "roles" / "report-integrator.md")
    reference_text = read_text(ROOT / "reference-flow-skill.md")

    for token in ("SKILL-SURFACE-WORKLIST.md", "SURFACE-COVERAGE.json"):
        if token not in definitions_text:
            issues.append(f"DEFINITIONS.md is missing {token} in the stage-five outputs")
        if token not in flow_text:
            issues.append(f"flows/skill-testing.md is missing {token} in the stage-five contract")
        if token not in readme_text:
            issues.append(f"README.md is missing {token} in the documented outputs")

    if "validate_flow_a_skill_results.py" not in skill_text:
        issues.append("SKILL.md is missing validate_flow_a_skill_results.py guidance")
    if "run_flow_a_skill_execution.py" not in skill_text:
        issues.append("SKILL.md is missing run_flow_a_skill_execution.py guidance")
    if "SKILL-SURFACE-WORKLIST.md" not in tester_text or "SURFACE-COVERAGE.json" not in tester_text:
        issues.append("roles/skill-tester.md is missing stage-five worklist and coverage inputs")
    if "SURFACE-COVERAGE.json" not in evidence_text:
        issues.append("roles/evidence-collector.md is missing SURFACE-COVERAGE.json audit input")
    if "SURFACE-COVERAGE.json" not in report_text:
        issues.append("roles/report-integrator.md is missing SURFACE-COVERAGE.json residual-risk input")
    if "validate_flow_a_skill_results.py" not in reference_text:
        issues.append("reference-flow-skill.md is missing the stage-five surface result validator")

    return issues


def validate_message_send_contract() -> list[str]:
    issues: list[str] = []
    example_files = (
        "SKILL.md",
        "reference-report-format.md",
    )

    skill_text = read_text(ROOT / "SKILL.md")
    if "交付物生成后立即主动发送" not in skill_text:
        issues.append(
            "SKILL.md is missing the proactive deliverable-send rule"
        )

    definitions_text = read_text(ROOT / "DEFINITIONS.md")
    if "阶段文件已写入但尚未发送给用户，不算阶段完成" not in definitions_text:
        issues.append(
            "DEFINITIONS.md is missing the sent-before-complete rule"
        )
    if "files/" not in definitions_text or "prepare_report_delivery.py" not in definitions_text:
        issues.append(
            "DEFINITIONS.md is missing the files/ relay rule for artifact delivery"
        )

    flow_skill_text = read_text(ROOT / "flows" / "skill-testing.md")
    if "主 agent 动作" not in flow_skill_text:
        issues.append(
            "flows/skill-testing.md is missing explicit main-agent send actions"
        )
    if "files/" not in flow_skill_text:
        issues.append(
            "flows/skill-testing.md is missing the files/ relay delivery rule"
        )

    approval_text = read_text(ROOT / "reference-approval-mechanism.md")
    if "交付物发送与批准请求必须同轮触发" not in approval_text:
        issues.append(
            "reference-approval-mechanism.md is missing the same-turn send-and-approve rule"
        )
    if "prepare_report_delivery.py" not in approval_text:
        issues.append(
            "reference-approval-mechanism.md is missing the relay-send fallback guidance"
        )

    for relative_path in example_files:
        text = read_text(ROOT / relative_path)
        matches = [
            match
            for match in MESSAGE_SEND_PATTERN.finditer(text)
            if "filePath:" in match.group("body")
        ]
        if not matches:
            issues.append(
                f"{relative_path} is missing a concrete message(action: \"send\", ...) example"
            )
            continue

        has_empty_buttons = False
        for match in matches:
            body = match.group("body")
            if "caption:" not in body:
                issues.append(
                    f"{relative_path} contains a file-send example without caption"
                )
            if "buttons:" not in body:
                issues.append(
                    f"{relative_path} contains a file-send example without buttons"
                )
            if "buttons: []" in body:
                has_empty_buttons = True
            if 'filePath: "memory/' in body:
                issues.append(
                    f"{relative_path} contains a file-send example that incorrectly uses memory/ instead of files/"
                )
            if 'filePath: "files/' not in body:
                issues.append(
                    f"{relative_path} is missing a file-send example that uses a files/ relay path"
                )

        if not has_empty_buttons:
            issues.append(
                f"{relative_path} is missing a file-send example with buttons: []"
            )

    return issues


def validate_output_language_contract() -> list[str]:
    issues: list[str] = []
    required_paths = (
        "SKILL.md",
        "DEFINITIONS.md",
        "reference-report-format.md",
        "roles/requirement-analyst.md",
        "roles/test-designer.md",
        "roles/test-case-evaluator.md",
        "roles/report-integrator.md",
    )
    required_markers = (
        "发起测试请求的语言",
        "--language",
    )
    for relative_path in required_paths:
        text = read_text(ROOT / relative_path)
        if not any(marker in text for marker in required_markers):
            issues.append(
                f"{relative_path} is missing the request-language output contract"
            )
    return issues


def validate_flow_a_case_depth_contract() -> list[str]:
    issues: list[str] = []
    checks = {
        "flows/skill-testing.md": ("数据驱动", "规则", "决策路径", "检查项"),
        "roles/test-designer.md": ("数据驱动", "规则", "决策路径", "检查项"),
        "roles/test-case-evaluator.md": ("数据驱动", "规则", "决策路径", "检查项"),
        "reference-flow-skill.md": ("规则", "决策路径", "检查项"),
    }
    for relative_path, markers in checks.items():
        text = read_text(ROOT / relative_path)
        if not all(marker in text for marker in markers):
            issues.append(
                f"{relative_path} is missing the Flow A data-driven case-depth contract"
            )
    return issues


def validate_flow_a_runtime_harness_contract() -> list[str]:
    issues: list[str] = []
    checks = {
        "SKILL.md": ("openclawExtensionRuntimeHarness",),
        "README.md": ("openclawExtensionRuntimeHarness",),
        "flows/skill-testing.md": ("openclawExtensionRuntimeHarness", "伴随规则文件"),
        "reference-flow-skill.md": ("openclawExtensionRuntimeHarness", "伴随规则文件"),
        "roles/requirement-analyst.md": ("伴随规则文件", "源码"),
        "roles/skill-tester.md": ("openclawExtensionRuntimeHarness", "runtime-probed=true"),
    }
    for relative_path, markers in checks.items():
        text = read_text(ROOT / relative_path)
        if not all(marker in text for marker in markers):
            issues.append(
                f"{relative_path} is missing the Flow A runtime-harness / companion-inventory contract"
            )
    return issues


def validate_role_references(required_flow_files: tuple[str, ...]) -> list[str]:
    """Check that roles referenced in flow files actually exist."""
    issues: list[str] = []
    for relative_path in required_flow_files:
        path = ROOT / relative_path
        if not path.exists():
            continue
        content = read_text(path)
        for role_name in ROLE_REF_PATTERN.findall(content):
            role_path = ROOT / "roles" / role_name
            if not role_path.exists():
                issues.append(
                    f"{relative_path} references non-existent role: roles/{role_name}"
                )
    return issues


def validate_role_definitions_ref() -> list[str]:
    """Check that active role files reference DEFINITIONS.md."""
    issues: list[str] = []
    for path in sorted((ROOT / "roles").glob("*.md")):
        content = read_text(path)
        if "DEFINITIONS.md" not in content:
            issues.append(
                f"{rel(path)} does not reference DEFINITIONS.md"
            )
    return issues


def validate_role_version_tags() -> list[str]:
    issues: list[str] = []
    for path in sorted((ROOT / "roles").glob("*.md")):
        if SEMVER_PATTERN.search(read_text(path)):
            issues.append(
                f"{rel(path)} contains an inline version tag; move version history to CHANGELOG.md"
            )
    return issues


def validate_flow_role_consistency(required_flow_files: tuple[str, ...]) -> list[str]:
    """Check that Flow files reference the expected number of parallel roles."""
    issues: list[str] = []

    for relative_path in required_flow_files:
        path = ROOT / relative_path
        if not path.exists():
            continue
        content = read_text(path)
        role_refs = ROLE_REF_PATTERN.findall(content)
        unique_roles = set(role_refs)

        for role_name in unique_roles:
            if not (ROOT / "roles" / role_name).exists():
                issues.append(
                    f"{relative_path} references non-existent role: roles/{role_name}"
                )

    return issues


def validate_required_references() -> list[str]:
    """Check that key reference files exist and CLAUDE.md exists."""
    issues: list[str] = []
    required_refs = (
        "reference-recovery.md",
        "reference-production-readiness.md",
    )
    for ref in required_refs:
        if not (ROOT / ref).exists():
            issues.append(f"Missing required reference file: {ref}")
    if not (ROOT / "CLAUDE.md").exists():
        issues.append("Missing CLAUDE.md (project AI collaboration guide)")
    return issues
