#!/usr/bin/env python3
"""Shared prompt builder for stage-role runtimes."""

from __future__ import annotations

LOCALIZATION = {
    "en": {
        "intro": "You are the stage-role subagent `{role_id}` for {stage_label} {stage_name}.",
        "role_file": "Role file: {role_file}",
        "report_dir": "Report directory: {report_dir}",
        "run_mode": "Run mode: {run_mode}",
        "missing": "Missing deliverables: {missing}",
        "available_artifacts": "Available report artifacts: {artifacts}",
        "rules_title": "Execution rules:",
        "rules": [
            "Work only for this role and this stage.",
            "Create or update only the deliverables needed for this role in the report directory.",
            "Do not ask the user for approval; that is handled by the orchestrator.",
            "Do not leave TODOs, placeholders, or vague summaries in the final artifacts.",
            "If you cannot finish real execution, record explicit blockers and mark the situation clearly instead of claiming success.",
            "Put the primary artifact path in the report directory when possible.",
        ],
        "sections": {
            "Responsibilities": "Responsibilities",
            "Hard boundaries": "Hard boundaries",
            "Execution rules from role doc": "Execution rules from role doc",
            "Evidence requirements": "Evidence requirements",
            "Anti-patterns to avoid": "Anti-patterns to avoid",
            "Minimum output structure": "Minimum output structure",
        },
        "self_check_title": "Self-check before returning:",
        "self_check": [
            "Every deliverable you claim to have produced exists on disk.",
            "The deliverable content follows the role's required structure, not just a stub.",
            "Blockers and residual gaps are explicit when anything remains unverified.",
        ],
        "launch_prompt": "Role launch prompt:",
        "json_title": "JSON response requirements:",
        "json_rules": [
            "resultFile: primary artifact path you produced, or null if there is no single primary file.",
            "note: one short sentence summarizing what you completed.",
            "status: optional. Use `completed` when done, or `blocked` if you need takeover.",
            "needsMainAgentTakeover: optional boolean. Set true when the host/main agent must continue the work because your environment is insufficient.",
            "blockers: optional array of short blocker reasons.",
        ],
    },
    "zh": {
        "intro": "你现在是阶段角色 subagent：`{role_id}`。",
        "role_file": "角色文件：{role_file}",
        "report_dir": "报告目录：{report_dir}",
        "run_mode": "运行模式：{run_mode}",
        "missing": "当前缺失交付物：{missing}",
        "available_artifacts": "当前报告目录已有工件：{artifacts}",
        "rules_title": "执行要求：",
        "rules": [
            "只执行当前角色负责的工作，不处理审批。",
            "只在报告目录中补齐当前角色交付物。",
            "完成后优先把主交付物写入报告目录。",
            "不要输出长解释，不要向用户提问。",
            "不要只写占位内容、TODO 或模糊结论。",
            "若环境不足以完成真实执行，必须明确写 blocker，而不是把未验证内容写成通过。",
        ],
        "sections": {
            "Responsibilities": "职责",
            "Hard boundaries": "强边界",
            "Execution rules from role doc": "执行规则",
            "Evidence requirements": "证据要求",
            "Anti-patterns to avoid": "反模式",
            "Minimum output structure": "最低输出结构",
        },
        "self_check_title": "返回前自检：",
        "self_check": [
            "你声称产出的交付物必须已写入磁盘。",
            "交付物必须是可消费结果，不是空壳或摘要占位。",
            "若需主 agent 接管，请明确说明 blocker 和接管原因。",
        ],
        "launch_prompt": "角色启动提示词：",
        "json_title": "",
        "json_rules": [],
    },
}


def extend_prompt_section(lines: list[str], title: str, items: list[object], *, language: str) -> None:
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        return
    localized_title = LOCALIZATION[language]["sections"][title]
    lines.extend(["", f"{localized_title}:", *[f"- {item}" for item in values]])


def build_runtime_prompt(
    payload: dict[str, object],
    prompt_text: str,
    *,
    language: str,
    include_json_response_rules: bool,
) -> str:
    messages = LOCALIZATION[language]
    missing = ", ".join(str(item) for item in payload.get("missingDeliverables", [])) or "(none)"
    run_mode = str(payload.get("runMode", "test"))
    available_artifacts = ", ".join(str(item) for item in payload.get("availableArtifacts", [])) or "(none)"
    lines = [
        messages["intro"].format(
            role_id=str(payload["roleId"]),
            stage_label=str(payload["stageLabel"]),
            stage_name=str(payload["stageName"]),
        ),
        messages["role_file"].format(role_file=str(payload["roleFile"])),
        messages["report_dir"].format(report_dir=str(payload["reportDir"])),
        messages["run_mode"].format(run_mode=run_mode),
        messages["missing"].format(missing=missing),
        messages["available_artifacts"].format(artifacts=available_artifacts),
        "",
        messages["rules_title"],
        *[f"- {item}" for item in messages["rules"]],
    ]
    if run_mode == "test":
        lines.append(
            "- Do not modify the target repository under test; record defects in the report directory and stop."
            if language == "en"
            else "- 测试模式下禁止修改被测仓库；只能在报告目录记录缺陷，不得边测边改产品。"
        )
    extend_prompt_section(lines, "Responsibilities", list(payload.get("responsibilities", [])), language=language)
    extend_prompt_section(lines, "Hard boundaries", list(payload.get("hardBoundaries", [])), language=language)
    extend_prompt_section(lines, "Execution rules from role doc", list(payload.get("executionRules", [])), language=language)
    extend_prompt_section(lines, "Evidence requirements", list(payload.get("evidenceRequirements", [])), language=language)
    extend_prompt_section(lines, "Anti-patterns to avoid", list(payload.get("antiPatterns", [])), language=language)
    extend_prompt_section(lines, "Minimum output structure", list(payload.get("minimumOutput", [])), language=language)
    lines.extend(
        [
            "",
            messages["self_check_title"],
            *[f"- {item}" for item in messages["self_check"]],
            "",
            messages["launch_prompt"],
            prompt_text.strip(),
        ]
    )
    if include_json_response_rules and messages["json_title"]:
        lines.extend(["", messages["json_title"], *[f"- {item}" for item in messages["json_rules"]]])
    return "\n".join(lines)
