#!/usr/bin/env python3
"""Stage orchestration state machine for Nexus Testing."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import argparse
import json
import sys
import time
from pathlib import Path

from generate_stage_subagent_plan import build_plan, normalize_flow, normalize_mode

from nexus_testing.definitions_loader import load_sections_for_role
from nexus_testing.dispatch_payload_schema import (
    validate_bundle_files,
    validate_bundle_manifest,
    validate_dispatch_payload_list,
)
from nexus_testing.json_utils import load_json
from nexus_testing.path_utils import resolve_path
from nexus_testing.role_metadata import parse_role_doc as load_role_doc_metadata
from nexus_testing.role_runtime_prompt import build_runtime_prompt
from nexus_testing.runtime.policy import EXECUTION_PROFILES, resolve_execution_policy
from nexus_testing.sandbox_skill_invoke.core import write_text
from nexus_testing.stage_contracts import verify_stage_preconditions
from nexus_testing.stage_validation import validate_stage_artifacts
from nexus_testing.state_lock import StateLock


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
def save_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def build_delivery_config(
    *,
    backend: str | None,
    channel: str,
    caption: str,
    command: list[str] | None,
    timeout_seconds: int,
    auto_send_on_complete: bool,
    default_backend: str,
) -> dict[str, object]:
    normalized_backend = str(backend or default_backend).strip().lower()
    if normalized_backend not in {"relay-only", "command"}:
        normalized_backend = default_backend
    normalized_command = [str(item).strip() for item in (command or []) if str(item).strip()]
    if normalized_backend == "command" and not normalized_command:
        normalized_backend = "relay-only"
    return {
        "enabled": True,
        "autoSendOnComplete": auto_send_on_complete,
        "channel": str(channel or "telegram").strip() or "telegram",
        "caption": str(caption or ""),
        "backend": normalized_backend,
        "command": normalized_command,
        "timeoutSeconds": max(1, int(timeout_seconds)),
    }


def stage_key(stage_id: str) -> str:
    return stage_id.replace("-", "_")


def approval_required(stage: dict[str, object]) -> bool:
    return str(stage.get("userGate", "none")) in {"confirm", "approve"}


def approval_satisfied(record: dict[str, object] | None) -> bool:
    if not record:
        return False
    return str(record.get("user_response")) in {"approved", "auto-continue"}


def rejection_state(rejections: dict[str, object], stage_id: str) -> dict[str, object] | None:
    value = rejections.get(stage_key(stage_id))
    return value if isinstance(value, dict) else None


def collect_missing_deliverables(report_dir: Path, deliverables: list[object]) -> list[str]:
    missing: list[str] = []
    for item in deliverables:
        text = str(item)
        if text.startswith("("):
            continue
        if "*" in text:
            if not list(report_dir.glob(text)):
                missing.append(text)
            continue
        if not (report_dir / text).exists():
            missing.append(text)
    return missing


def normalize_report_deliverable(item: object) -> str:
    text = str(item).strip().strip("`")
    if not text:
        return ""
    normalized = text.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if "nexus-reports" in parts:
        index = parts.index("nexus-reports")
        if len(parts) > index + 2:
            normalized = "/".join(parts[index + 2 :])
        elif parts:
            normalized = parts[-1]
    return normalized


def available_report_artifacts(report_dir: Path) -> list[str]:
    artifacts: list[str] = []
    if not report_dir.exists():
        return artifacts
    ignored_roots = {"DISPATCH", "RUNS"}
    for path in sorted(report_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(report_dir)
        if relative.parts and relative.parts[0] in ignored_roots:
            continue
        artifacts.append(str(relative).replace("\\", "/"))
    return artifacts[:200]


def actionable_roles_for_stage(report_dir: Path, action: dict[str, object]) -> list[dict[str, object]]:
    roles = [role for role in action.get("roles", []) if isinstance(role, dict)]
    if str(action.get("dispatchMode")) != "serial" or len(roles) <= 1:
        return roles
    for role in roles:
        role_file = resolve_path(str(role.get("file")))
        role_meta = parse_role_doc(role_file)
        outputs: list[str] = []
        for item in role_meta.get("outputs", []):
            normalized = normalize_report_deliverable(item)
            if normalized:
                outputs.append(normalized)
        if not outputs:
            return [role]
        if collect_missing_deliverables(report_dir, outputs):
            return [role]
    return roles[:1]


def has_stage_complete_event(stage_log: list[object], stage_id: str) -> bool:
    for item in stage_log:
        if not isinstance(item, dict):
            continue
        if item.get("event") == "stage-complete" and item.get("from_stage") == stage_id:
            return True
    return False


def parse_role_doc(role_file: Path) -> dict[str, object]:
    return load_role_doc_metadata(role_file)


def precondition_failure_action(stage: dict[str, object], stage_index: int, preconditions: dict[str, object]) -> dict[str, object]:
    return {
        "status": "precondition-failed",
        "stageId": stage.get("stageId"),
        "label": stage.get("label"),
        "name": stage.get("name"),
        "dispatchMode": stage.get("dispatchMode"),
        "roles": stage.get("roles", []),
        "postStageRoles": stage.get("postStageRoles", []),
        "requiredInputs": preconditions.get("requiredInputs", []),
        "missingInputs": preconditions.get("missingInputs", []),
        "artifactBaseDir": preconditions.get("artifactBaseDir"),
        "requiredArtifactPaths": preconditions.get("requiredArtifactPaths", []),
        "upstreamOutputsVerified": False,
        "userGate": stage.get("userGate", "none"),
        "stageIndex": stage_index,
    }


def next_action(
    report_dir: Path,
    plan: dict[str, object],
    approvals: dict[str, object],
    rejections: dict[str, object],
    stage_log: list[object],
) -> dict[str, object]:
    stages = list(plan.get("stages", []))
    for index, stage in enumerate(stages):
        stage_id = str(stage["stageId"])
        preconditions = verify_stage_preconditions(report_dir, stage)
        missing = collect_missing_deliverables(report_dir, list(stage.get("deliverables", [])))
        if not missing and any(str(item).startswith("(") for item in stage.get("deliverables", [])):
            if not has_stage_complete_event(stage_log, stage_id):
                missing.append("(stage-complete event)")
        if missing:
            if list(preconditions.get("missingInputs", [])):
                return precondition_failure_action(stage, index, preconditions)
            return {
                "status": "run-stage",
                "stageId": stage_id,
                "label": stage.get("label"),
                "name": stage.get("name"),
                "dispatchMode": stage.get("dispatchMode"),
                "roles": stage.get("roles", []),
                "postStageRoles": stage.get("postStageRoles", []),
                "missingDeliverables": missing,
                "requiredInputs": preconditions.get("requiredInputs", []),
                "artifactBaseDir": preconditions.get("artifactBaseDir"),
                "requiredArtifactPaths": preconditions.get("requiredArtifactPaths", []),
                "upstreamOutputsVerified": bool(preconditions.get("upstreamOutputsVerified", True)),
                "userGate": stage.get("userGate", "none"),
                "stageIndex": index,
            }
        post_roles = list(stage.get("postStageRoles", []))
        post_deliverables = list(stage.get("postStageDeliverables", []))
        if post_roles and post_deliverables:
            missing_post = collect_missing_deliverables(report_dir, post_deliverables)
            if missing_post:
                return {
                    "status": "run-post-stage",
                    "stageId": stage_id,
                    "label": stage.get("label"),
                    "name": stage.get("name"),
                    "dispatchMode": "serial" if len(post_roles) == 1 else "parallel",
                    "roles": post_roles,
                    "missingDeliverables": missing_post,
                    "requiredInputs": preconditions.get("requiredInputs", []),
                    "artifactBaseDir": preconditions.get("artifactBaseDir"),
                    "requiredArtifactPaths": preconditions.get("requiredArtifactPaths", []),
                    "upstreamOutputsVerified": bool(preconditions.get("upstreamOutputsVerified", True)),
                    "userGate": "none",
                    "stageIndex": index,
                    "postStage": True,
                }
        if approval_required(stage):
            record = approvals.get(stage_key(stage_id))
            rejection = rejection_state(rejections, stage_id)
            if rejection and int(rejection.get("count", 0)) >= 3:
                return {
                    "status": "no-go",
                    "stageId": stage_id,
                    "label": stage.get("label"),
                    "reason": rejection.get("last_reason", "Rejected 3 times"),
                }
            artifact_validation = validate_stage_artifacts(report_dir, stage)
            if not bool(artifact_validation.get("ok", False)):
                return {
                    "status": "artifact-validation-failed",
                    "stageId": stage_id,
                    "label": stage.get("label"),
                    "name": stage.get("name"),
                    "artifactValidation": artifact_validation,
                    "stageIndex": index,
                }
            if not approval_satisfied(record):
                return {
                    "status": "await-approval",
                    "stageId": stage_id,
                    "label": stage.get("label"),
                    "name": stage.get("name"),
                    "gate": stage.get("userGate"),
                    "approvalRecord": record,
                    "artifactValidation": artifact_validation,
                    "stageIndex": index,
                }
    return {"status": "complete", "stageCount": len(stages)}


def dispatch_payloads(report_dir: Path, plan: dict[str, object], action: dict[str, object]) -> dict[str, object]:
    status = str(action.get("status"))
    if status not in {"run-stage", "run-post-stage"}:
        return action

    payloads: list[dict[str, object]] = []
    roles = actionable_roles_for_stage(report_dir, action)
    run_mode = str(plan.get("runMode", "test"))
    execution_profile = str(plan.get("executionProfile", "internal-fast"))
    strict_real = bool(plan.get("strictReal", False))
    execution_policy = plan.get("executionPolicy", resolve_execution_policy(execution_profile, strict_real).to_dict())
    delivery = plan.get(
        "delivery",
        build_delivery_config(
            backend=None,
            channel="telegram",
            caption="",
            command=None,
            timeout_seconds=60,
            auto_send_on_complete=True,
            default_backend=resolve_execution_policy(execution_profile, strict_real).default_sender_backend,
        ),
    )
    artifacts = available_report_artifacts(report_dir)
    artifact_base_dir = str(action.get("artifactBaseDir") or report_dir.resolve())
    required_artifact_paths = [str(item) for item in action.get("requiredArtifactPaths", []) if str(item).strip()]
    upstream_outputs_verified = bool(action.get("upstreamOutputsVerified", True))
    for index, role in enumerate(roles):
        role_id = str(role.get("id"))
        role_file = resolve_path(str(role.get("file")))
        role_meta = parse_role_doc(role_file)
        payloads.append(
            {
                "roleId": role_id,
                "roleFile": str(role_file),
                "roleType": role.get("type"),
                "order": index + 1,
                "stageId": action.get("stageId"),
                "stageLabel": action.get("label"),
                "stageName": action.get("name"),
                "dispatchMode": action.get("dispatchMode"),
                "reportDir": str(report_dir),
                "artifactBaseDir": artifact_base_dir,
                "requiredArtifactPaths": required_artifact_paths,
                "upstreamOutputsVerified": upstream_outputs_verified,
                "runMode": run_mode,
                "executionProfile": execution_profile,
                "strictReal": strict_real,
                "executionPolicy": execution_policy,
                "delivery": delivery,
                "missingDeliverables": action.get("missingDeliverables", []),
                "availableArtifacts": artifacts,
                "inputSources": role_meta.get("inputSources", []),
                "inputs": role_meta.get("inputs", []),
                "outputs": role_meta.get("outputs", []),
                "consumers": role_meta.get("consumers", []),
                "responsibilities": role_meta.get("responsibilities", []),
                "executionRules": role_meta.get("executionRules", []),
                "evidenceRequirements": role_meta.get("evidenceRequirements", []),
                "antiPatterns": role_meta.get("antiPatterns", []),
                "hardBoundaries": role_meta.get("hardBoundaries", []),
                "minimumOutput": role_meta.get("minimumOutput", []),
                "validateMarkdownStructure": role_meta.get("validateMarkdownStructure", False),
                "minimumOutputAliases": role_meta.get("minimumOutputAliases", {}),
                "mainAgentTakeoverPolicy": role_meta.get("mainAgentTakeoverPolicy", {}),
                "description": role_meta.get("description"),
                "bestFor": role_meta.get("bestFor", []),
                "definitionExcerpt": load_sections_for_role(role_id) or None,
                "launchPrompt": (
                    f"执行 {action.get('label')} {action.get('name')}。"
                    f" 角色文件：{role_file}。"
                    f" 报告目录：{report_dir}。"
                    f" 当前需要补齐的交付物：{', '.join(str(item) for item in action.get('missingDeliverables', []))}。"
                    " 只负责本角色执行和写结果，不直接向用户请求批准。"
                ),
            }
        )
        payloads[-1]["launchPrompt"] = "\n".join(
            [
                f"执行 {action.get('label')} {action.get('name')}。",
                f"角色文件: {role_file}",
                f"报告目录: {report_dir}",
                f"当前需要补齐的交付物: {', '.join(str(item) for item in action.get('missingDeliverables', [])) or '(none)'}",
                f"必须优先读取这些完整路径: {', '.join(required_artifact_paths) or '(none)'}",
                "不要自行推断其它路径，也不要在工作区根目录搜索同名替代文件。只负责本角色执行和写结果，不直接向用户请求批准。",
            ]
        )

    result = dict(action)
    result["dispatchPayloads"] = validate_dispatch_payload_list(payloads)
    return result


def slugify_stage(stage_id: str) -> str:
    return stage_id.replace("/", "-").replace("\\", "-")


def render_dispatch_prompt(payload: dict[str, object]) -> str:
    lines = [
        f"# Dispatch Prompt - {payload['roleId']}",
        "",
        f"- Stage: {payload['stageLabel']} {payload['stageName']}",
        f"- Role File: `{payload['roleFile']}`",
        f"- Report Dir: `{payload['reportDir']}`",
        f"- Artifact Base Dir: `{payload.get('artifactBaseDir', payload['reportDir'])}`",
        f"- Run Mode: `{payload.get('runMode', 'test')}`",
        f"- Execution Profile: `{payload.get('executionProfile', 'internal-fast')}`",
        f"- Strict Real: `{str(bool(payload.get('strictReal', False))).lower()}`",
        f"- Upstream Outputs Verified: `{str(bool(payload.get('upstreamOutputsVerified', True))).lower()}`",
        f"- Missing Deliverables: {', '.join(str(item) for item in payload.get('missingDeliverables', [])) or '(none)'}",
        f"- Available Report Artifacts: {', '.join(str(item) for item in payload.get('availableArtifacts', [])) or '(none)'}",
        "",
        "## Role Summary",
        "",
        f"- Description: {payload.get('description') or '(none)'}",
    ]
    required_artifact_paths = list(payload.get("requiredArtifactPaths", []))
    if required_artifact_paths:
        lines.extend(["", "## Required Artifact Paths", ""] + [f"- `{item}`" for item in required_artifact_paths])
        lines.extend(
            [
                "",
                "## Artifact Path Contract",
                "",
                "- Read the exact paths listed above before judging missing inputs.",
                "- Do not infer alternate paths or substitute files with the same name from elsewhere in the workspace.",
            ]
        )
    best_for = list(payload.get("bestFor", []))
    if best_for:
        lines.extend(["- Best For:"] + [f"  - {item}" for item in best_for])
    input_sources = list(payload.get("inputSources", []))
    if input_sources:
        lines.extend(["", "## Input Sources", ""] + [f"- {item}" for item in input_sources])
    inputs = list(payload.get("inputs", []))
    if inputs:
        lines.extend(["", "## Inputs", ""] + [f"- {item}" for item in inputs])
    outputs = list(payload.get("outputs", []))
    if outputs:
        lines.extend(["", "## Outputs", ""] + [f"- {item}" for item in outputs])
    consumers = list(payload.get("consumers", []))
    if consumers:
        lines.extend(["", "## Downstream Consumers", ""] + [f"- {item}" for item in consumers])
    responsibilities = list(payload.get("responsibilities", []))
    if responsibilities:
        lines.extend(["", "## Responsibilities", ""] + [f"- {item}" for item in responsibilities])
    hard_boundaries = list(payload.get("hardBoundaries", []))
    if hard_boundaries:
        lines.extend(["", "## Hard Boundaries", ""] + [f"- {item}" for item in hard_boundaries])
    execution_rules = list(payload.get("executionRules", []))
    if execution_rules:
        lines.extend(["", "## Execution Rules", ""] + [f"- {item}" for item in execution_rules])
    evidence_requirements = list(payload.get("evidenceRequirements", []))
    if evidence_requirements:
        lines.extend(["", "## Evidence Requirements", ""] + [f"- {item}" for item in evidence_requirements])
    anti_patterns = list(payload.get("antiPatterns", []))
    if anti_patterns:
        lines.extend(["", "## Anti-Patterns", ""] + [f"- {item}" for item in anti_patterns])
    minimum_output = list(payload.get("minimumOutput", []))
    if minimum_output:
        lines.extend(["", "## Minimum Output Structure", ""] + [f"- {item}" for item in minimum_output])
    if payload.get("validateMarkdownStructure"):
        lines.extend(["", "## Output Validation", "", "- markdown-headings"])
    minimum_output_aliases = payload.get("minimumOutputAliases", {})
    if isinstance(minimum_output_aliases, dict) and minimum_output_aliases:
        lines.extend(
            ["", "## Minimum Output Aliases", ""]
            + [f"- {key} => {value}" for key, value in minimum_output_aliases.items()]
        )
    takeover_policy = payload.get("mainAgentTakeoverPolicy", {})
    if isinstance(takeover_policy, dict) and takeover_policy:
        lines.extend(["", "## Main Agent Takeover Policy", ""])
        for key in ("enabled", "statuses", "patterns", "onProcessFailure"):
            if key not in takeover_policy:
                continue
            value = takeover_policy[key]
            if isinstance(value, list):
                rendered = ", ".join(str(item) for item in value)
            else:
                rendered = str(value)
            lines.append(f"- {key}: {rendered}")
    execution_policy = payload.get("executionPolicy", {})
    if isinstance(execution_policy, dict) and execution_policy:
        lines.extend(["", "## Execution Policy", ""])
        for key in ("name", "strict_real", "prefer_host_execution", "run_security_scan", "default_sender_backend"):
            if key not in execution_policy:
                continue
            lines.append(f"- {key}: {execution_policy[key]}")
    delivery = payload.get("delivery", {})
    if isinstance(delivery, dict) and delivery:
        lines.extend(["", "## Delivery Defaults", ""])
        for key in ("enabled", "autoSendOnComplete", "channel", "backend", "timeoutSeconds"):
            if key not in delivery:
                continue
            lines.append(f"- {key}: {delivery[key]}")
    lines.extend(["", "## Launch Prompt", "", str(payload["launchPrompt"]), ""])
    return "\n".join(lines)


def bundle_dispatch(report_dir: Path, payload_result: dict[str, object]) -> dict[str, object]:
    status = str(payload_result.get("status"))
    if status not in {"run-stage", "run-post-stage"}:
        return payload_result

    stage_id = str(payload_result["stageId"])
    bundle_root = report_dir / "DISPATCH" / slugify_stage(stage_id)
    bundle_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "stageId": stage_id,
        "stageLabel": payload_result.get("label"),
        "stageName": payload_result.get("name"),
        "dispatchMode": payload_result.get("dispatchMode"),
        "status": status,
        "generatedAt": now_text(),
        "roles": [],
    }

    dispatch_payloads_list = validate_dispatch_payload_list(payload_result.get("dispatchPayloads", []))
    for payload in dispatch_payloads_list:
        role_id = str(payload["roleId"])
        order = int(payload["order"])
        stem = f"{order:02d}-{role_id}"
        payload_path = bundle_root / f"{stem}.payload.json"
        prompt_path = bundle_root / f"{stem}.prompt.md"
        raw_prompt = render_dispatch_prompt(payload)
        write_text(prompt_path, raw_prompt)
        final_prompt_path = bundle_root / f"{stem}.final_prompt.md"
        final_prompt = build_runtime_prompt(
            payload,
            raw_prompt,
            language="zh",
            include_json_response_rules=False,
        )
        write_text(final_prompt_path, final_prompt)
        baked_payload = dict(payload)
        baked_payload["prebaked"] = True
        baked_payload["finalPromptFile"] = str(final_prompt_path)
        save_json(payload_path, baked_payload)
        manifest["roles"].append(
            {
                "roleId": role_id,
                "order": order,
                "payloadFile": payload_path.name,
                "promptFile": prompt_path.name,
                "finalPromptFile": final_prompt_path.name,
            }
        )

    manifest_path = bundle_root / "manifest.json"
    validated_manifest = validate_bundle_manifest(manifest)
    validate_bundle_files(bundle_root, validated_manifest, dispatch_payloads_list)
    save_json(manifest_path, validated_manifest)
    result = dict(payload_result)
    result["bundleDir"] = str(bundle_root)
    result["manifestFile"] = str(manifest_path)
    return result


def init_executor(
    report_dir: Path,
    flow: str,
    mode: str,
    run_mode: str = "test",
    *,
    execution_profile: str = "internal-fast",
    strict_real: bool = False,
    delivery_backend: str | None = None,
    delivery_channel: str = "telegram",
    delivery_caption: str = "",
    delivery_command: list[str] | None = None,
    delivery_timeout_seconds: int = 60,
    auto_delivery: bool = True,
) -> dict[str, object]:
    report_dir.mkdir(parents=True, exist_ok=True)
    flow_id = normalize_flow(flow)
    normalized_mode = normalize_mode(flow_id, mode)
    normalized_run_mode = "repair" if str(run_mode).strip().lower() == "repair" else "test"
    execution_policy = resolve_execution_policy(execution_profile, strict_real)
    delivery = build_delivery_config(
        backend=delivery_backend,
        channel=delivery_channel,
        caption=delivery_caption,
        command=delivery_command,
        timeout_seconds=delivery_timeout_seconds,
        auto_send_on_complete=auto_delivery,
        default_backend=execution_policy.default_sender_backend,
    )
    plan = build_plan(flow_id, normalized_mode)
    plan["runMode"] = normalized_run_mode
    plan["executionProfile"] = execution_policy.name
    plan["strictReal"] = execution_policy.strict_real
    plan["executionPolicy"] = execution_policy.to_dict()
    plan["delivery"] = delivery
    plan_path = report_dir / "STAGE-SUBAGENT-PLAN.json"
    approval_path = report_dir / "approval-records.json"
    rejection_path = report_dir / "rejection-count.json"
    stage_log_path = report_dir / "stage-transition-log.json"

    save_json(plan_path, plan)
    if not approval_path.exists():
        save_json(approval_path, {})
    if not rejection_path.exists():
        save_json(rejection_path, {})
    if not stage_log_path.exists():
        save_json(stage_log_path, [])

    return {
        "status": "initialized",
        "reportDir": str(report_dir),
        "planFile": str(plan_path),
        "flowId": flow_id,
        "mode": normalized_mode,
        "runMode": normalized_run_mode,
        "executionProfile": execution_policy.name,
        "strictReal": execution_policy.strict_real,
        "executionPolicy": execution_policy.to_dict(),
        "delivery": delivery,
    }


def read_executor_state(report_dir: Path) -> tuple[dict[str, object], dict[str, object], dict[str, object], list[object]]:
    plan = load_json(report_dir / "STAGE-SUBAGENT-PLAN.json", {}, label="stage subagent plan")
    approvals = load_json(report_dir / "approval-records.json", {}, label="approval records")
    rejections = load_json(report_dir / "rejection-count.json", {}, label="rejection counts")
    stage_log = load_json(report_dir / "stage-transition-log.json", [], label="stage transition log")
    if not isinstance(plan, dict):
        raise SystemExit("ERROR: invalid STAGE-SUBAGENT-PLAN.json")
    if not isinstance(approvals, dict):
        raise SystemExit("ERROR: invalid approval-records.json")
    if not isinstance(rejections, dict):
        raise SystemExit("ERROR: invalid rejection-count.json")
    if not isinstance(stage_log, list):
        raise SystemExit("ERROR: invalid stage-transition-log.json")
    return plan, approvals, rejections, stage_log


def current_approval_gate(
    report_dir: Path,
    plan: dict[str, object],
    approvals: dict[str, object],
    rejections: dict[str, object],
    stage_log: list[object],
) -> dict[str, object]:
    action = next_action(report_dir, plan, approvals, rejections, stage_log)
    if str(action.get("status")) != "await-approval":
        raise SystemExit("ERROR: there is no stage currently waiting for approval")
    return action


def append_stage_log(report_dir: Path, entry: dict[str, object]) -> None:
    stage_log_path = report_dir / "stage-transition-log.json"
    with StateLock(stage_log_path):
        stage_log = load_json(stage_log_path, [], label="stage transition log")
        if not isinstance(stage_log, list):
            stage_log = []
        stage_log.append(entry)
        save_json(stage_log_path, stage_log)


def mark_stage_complete(report_dir: Path, stage_id: str, deliverable_file: str | None) -> dict[str, object]:
    append_stage_log(
        report_dir,
        {
            "from_stage": stage_id,
            "to_stage": stage_id,
            "timestamp": now_text(),
            "deliverable_file": deliverable_file,
            "approval_required": stage_id in {"stage-0", "stage-2", "stage-4", "b-stage-0", "b-stage-2", "b-stage-7"},
            "gate_check_passed": True,
            "event": "stage-complete",
        },
    )
    return {"status": "recorded", "event": "stage-complete", "stageId": stage_id}


def record_approval_request(report_dir: Path, stage_id: str, transport: str, interaction_id: str | None) -> dict[str, object]:
    plan, approvals, rejections, stage_log = read_executor_state(report_dir)
    gate = current_approval_gate(report_dir, plan, approvals, rejections, stage_log)
    expected_stage = str(gate.get("stageId"))
    if expected_stage != stage_id:
        raise SystemExit(
            f"ERROR: stage {stage_id} is not awaiting approval; current gate is {expected_stage}"
        )
    if not isinstance(approvals, dict):
        approvals = {}
    approvals[stage_key(stage_id)] = {
        "transport": transport,
        "interaction_id": interaction_id,
        "sent_at": now_text(),
        "user_response": None,
        "response_at": None,
        "stageLabel": gate.get("label"),
        "stageName": gate.get("name"),
        "artifactValidation": gate.get("artifactValidation", {}),
    }
    save_json(report_dir / "approval-records.json", approvals)
    append_stage_log(
        report_dir,
        {
            "from_stage": stage_id,
            "to_stage": stage_id,
            "timestamp": now_text(),
            "deliverable_file": None,
            "approval_required": True,
            "gate_check_passed": False,
            "event": "approval-requested",
        },
    )
    return {
        "status": "recorded",
        "event": "approval-requested",
        "stageId": stage_id,
        "stageLabel": gate.get("label"),
        "stageName": gate.get("name"),
        "artifactValidation": gate.get("artifactValidation", {}),
    }


def record_approval_response(report_dir: Path, stage_id: str, response: str, reason: str | None) -> dict[str, object]:
    if response not in {"approved", "rejected", "wait", "auto-continue"}:
        raise SystemExit(f"ERROR: unsupported response: {response}")

    plan, approvals, rejections, stage_log = read_executor_state(report_dir)
    gate = current_approval_gate(report_dir, plan, approvals, rejections, stage_log)
    expected_stage = str(gate.get("stageId"))
    if expected_stage != stage_id:
        raise SystemExit(
            f"ERROR: stage {stage_id} is not awaiting approval; current gate is {expected_stage}"
        )
    if not isinstance(approvals, dict):
        approvals = {}
    if not isinstance(rejections, dict):
        rejections = {}

    record = approvals.get(stage_key(stage_id), {})
    if not isinstance(record, dict):
        record = {}
    if not record.get("sent_at"):
        raise SystemExit(
            f"ERROR: approval request for {stage_id} has not been recorded yet"
        )
    record["user_response"] = response
    record["response_at"] = now_text()
    approvals[stage_key(stage_id)] = record
    save_json(report_dir / "approval-records.json", approvals)

    if response == "rejected":
        rejection = rejections.get(stage_key(stage_id), {})
        if not isinstance(rejection, dict):
            rejection = {}
        count = int(rejection.get("count", 0)) + 1
        rejection.update(
            {
                "stage": stage_id,
                "count": count,
                "last_rejection": now_text(),
                "last_reason": reason or "",
            }
        )
        rejections[stage_key(stage_id)] = rejection
    elif response in {"approved", "auto-continue"}:
        rejections[stage_key(stage_id)] = {"stage": stage_id, "count": 0, "last_rejection": None, "last_reason": None}
    save_json(report_dir / "rejection-count.json", rejections)

    append_stage_log(
        report_dir,
        {
            "from_stage": stage_id,
            "to_stage": stage_id,
            "timestamp": now_text(),
            "deliverable_file": None,
            "approval_required": True,
            "gate_check_passed": response in {"approved", "auto-continue"},
            "event": f"approval-{response}",
            "reason": reason,
        },
    )
    return {
        "status": "recorded",
        "event": f"approval-{response}",
        "stageId": stage_id,
        "artifactValidation": gate.get("artifactValidation", {}),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Initialize report-dir state and generate STAGE-SUBAGENT-PLAN.json")
    init_parser.add_argument("--report-dir", required=True)
    init_parser.add_argument("--flow", required=True)
    init_parser.add_argument("--mode", default="standard")
    init_parser.add_argument("--run-mode", default="test")
    init_parser.add_argument("--execution-profile", choices=EXECUTION_PROFILES, default="internal-fast")
    init_parser.add_argument("--strict-real", action="store_true")
    init_parser.add_argument("--delivery-backend", choices=("relay-only", "command"))
    init_parser.add_argument("--delivery-channel", default="telegram")
    init_parser.add_argument("--delivery-caption", default="")
    init_parser.add_argument("--delivery-command", nargs="+")
    init_parser.add_argument("--delivery-timeout-seconds", type=int, default=60)
    init_parser.add_argument("--no-auto-delivery", action="store_true")

    status_parser = sub.add_parser("status", help="Inspect current orchestration state")
    status_parser.add_argument("--report-dir", required=True)

    next_parser = sub.add_parser("next", help="Return the next actionable orchestration step")
    next_parser.add_argument("--report-dir", required=True)

    dispatch_parser = sub.add_parser("dispatch", help="Return dispatch payloads for the current actionable step")
    dispatch_parser.add_argument("--report-dir", required=True)

    bundle_parser = sub.add_parser("bundle-dispatch", help="Write dispatch payloads and prompt files into a bundle directory")
    bundle_parser.add_argument("--report-dir", required=True)

    complete_parser = sub.add_parser("mark-stage-complete", help="Append a stage-complete event")
    complete_parser.add_argument("--report-dir", required=True)
    complete_parser.add_argument("--stage-id", required=True)
    complete_parser.add_argument("--deliverable-file")

    req_parser = sub.add_parser("record-approval-request", help="Record that the main agent requested approval")
    req_parser.add_argument("--report-dir", required=True)
    req_parser.add_argument("--stage-id", required=True)
    req_parser.add_argument("--transport", default="text")
    req_parser.add_argument("--interaction-id")

    resp_parser = sub.add_parser("record-approval-response", help="Record an approval response")
    resp_parser.add_argument("--report-dir", required=True)
    resp_parser.add_argument("--stage-id", required=True)
    resp_parser.add_argument("--response", required=True)
    resp_parser.add_argument("--reason")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    report_dir = resolve_path(args.report_dir)

    if args.command == "init":
        result = init_executor(
            report_dir,
            args.flow,
            args.mode,
            args.run_mode,
            execution_profile=args.execution_profile,
            strict_real=args.strict_real,
            delivery_backend=args.delivery_backend,
            delivery_channel=args.delivery_channel,
            delivery_caption=args.delivery_caption,
            delivery_command=args.delivery_command,
            delivery_timeout_seconds=args.delivery_timeout_seconds,
            auto_delivery=not args.no_auto_delivery,
        )
    elif args.command == "status":
        plan, approvals, rejections, stage_log = read_executor_state(report_dir)
        result = {
            "status": "ok",
            "plan": plan,
            "approvals": approvals,
            "rejections": rejections,
            "stageLogEntries": len(stage_log),
            "nextAction": next_action(report_dir, plan, approvals, rejections, stage_log),
        }
    elif args.command == "next":
        plan, approvals, rejections, stage_log = read_executor_state(report_dir)
        result = next_action(report_dir, plan, approvals, rejections, stage_log)
    elif args.command == "dispatch":
        plan, approvals, rejections, stage_log = read_executor_state(report_dir)
        result = dispatch_payloads(
            report_dir,
            plan,
            next_action(report_dir, plan, approvals, rejections, stage_log),
        )
    elif args.command == "bundle-dispatch":
        plan, approvals, rejections, stage_log = read_executor_state(report_dir)
        result = bundle_dispatch(
            report_dir,
            dispatch_payloads(
                report_dir,
                plan,
                next_action(report_dir, plan, approvals, rejections, stage_log),
            ),
        )
    elif args.command == "mark-stage-complete":
        result = mark_stage_complete(report_dir, args.stage_id, args.deliverable_file)
    elif args.command == "record-approval-request":
        result = record_approval_request(report_dir, args.stage_id, args.transport, args.interaction_id)
    elif args.command == "record-approval-response":
        result = record_approval_response(report_dir, args.stage_id, args.response, args.reason)
    else:
        raise SystemExit(f"ERROR: unsupported command {args.command}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
