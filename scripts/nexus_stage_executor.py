#!/usr/bin/env python3
"""Stage orchestration state machine for Nexus Testing."""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from pathlib import Path

from generate_stage_subagent_plan import build_plan, normalize_flow, normalize_mode
from sandbox_skill_invoke.core import read_text, write_text

ROOT = Path(__file__).resolve().parents[1]
STATE_LOCK = threading.RLock()


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def resolve_path(path_value: str) -> Path:
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        return (ROOT / candidate).resolve()
    return candidate.resolve()


def load_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(read_text(path))


def save_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


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


def has_stage_complete_event(stage_log: list[object], stage_id: str) -> bool:
    for item in stage_log:
        if not isinstance(item, dict):
            continue
        if item.get("event") == "stage-complete" and item.get("from_stage") == stage_id:
            return True
    return False


FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def parse_frontmatter(text: str) -> dict[str, object]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    lines = match.group(1).splitlines()
    result: dict[str, object] = {}
    current_list_key: str | None = None
    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith("  - ") and current_list_key:
            result.setdefault(current_list_key, [])
            casted = result[current_list_key]
            if isinstance(casted, list):
                casted.append(line[4:].strip().strip('"'))
            continue
        current_list_key = None
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            result[key] = []
            current_list_key = key
        else:
            result[key] = value.strip('"')
    return result


def section_lines(text: str, heading: str) -> list[str]:
    markers = list(SECTION_RE.finditer(text))
    for index, marker in enumerate(markers):
        if marker.group(1).strip() != heading:
            continue
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        body = text[start:end]
        return [line.strip()[2:].strip() for line in body.splitlines() if line.strip().startswith("- ")]
    return []


def parse_role_doc(role_file: Path) -> dict[str, object]:
    text = read_text(role_file)
    frontmatter = parse_frontmatter(text)
    return {
        "name": frontmatter.get("name"),
        "type": frontmatter.get("type"),
        "description": frontmatter.get("description"),
        "bestFor": frontmatter.get("best_for", []),
        "inputSources": section_lines(text, "输入来源"),
        "inputs": section_lines(text, "输入"),
        "outputs": section_lines(text, "输出"),
        "consumers": section_lines(text, "下游消费者"),
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
        missing = collect_missing_deliverables(report_dir, list(stage.get("deliverables", [])))
        if not missing and any(str(item).startswith("(") for item in stage.get("deliverables", [])):
            if not has_stage_complete_event(stage_log, stage_id):
                missing.append("(stage-complete event)")
        if missing:
            return {
                "status": "run-stage",
                "stageId": stage_id,
                "label": stage.get("label"),
                "name": stage.get("name"),
                "dispatchMode": stage.get("dispatchMode"),
                "roles": stage.get("roles", []),
                "postStageRoles": stage.get("postStageRoles", []),
                "missingDeliverables": missing,
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
            if not approval_satisfied(record):
                return {
                    "status": "await-approval",
                    "stageId": stage_id,
                    "label": stage.get("label"),
                    "name": stage.get("name"),
                    "gate": stage.get("userGate"),
                    "approvalRecord": record,
                    "stageIndex": index,
                }
    return {"status": "complete", "stageCount": len(stages)}


def dispatch_payloads(report_dir: Path, plan: dict[str, object], action: dict[str, object]) -> dict[str, object]:
    status = str(action.get("status"))
    if status not in {"run-stage", "run-post-stage"}:
        return action

    payloads: list[dict[str, object]] = []
    roles = list(action.get("roles", []))
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
                "missingDeliverables": action.get("missingDeliverables", []),
                "inputSources": role_meta.get("inputSources", []),
                "inputs": role_meta.get("inputs", []),
                "outputs": role_meta.get("outputs", []),
                "consumers": role_meta.get("consumers", []),
                "description": role_meta.get("description"),
                "bestFor": role_meta.get("bestFor", []),
                "launchPrompt": (
                    f"执行 {action.get('label')} {action.get('name')}。"
                    f" 角色文件：{role_file}。"
                    f" 报告目录：{report_dir}。"
                    f" 当前需要补齐的交付物：{', '.join(str(item) for item in action.get('missingDeliverables', []))}。"
                    " 只负责本角色执行和写结果，不直接向用户请求批准。"
                ),
            }
        )

    result = dict(action)
    result["dispatchPayloads"] = payloads
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
        f"- Missing Deliverables: {', '.join(str(item) for item in payload.get('missingDeliverables', [])) or '(none)'}",
        "",
        "## Role Summary",
        "",
        f"- Description: {payload.get('description') or '(none)'}",
    ]
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

    dispatch_payloads_list = list(payload_result.get("dispatchPayloads", []))
    for payload in dispatch_payloads_list:
        role_id = str(payload["roleId"])
        order = int(payload["order"])
        stem = f"{order:02d}-{role_id}"
        payload_path = bundle_root / f"{stem}.payload.json"
        prompt_path = bundle_root / f"{stem}.prompt.md"
        save_json(payload_path, payload)
        write_text(prompt_path, render_dispatch_prompt(payload))
        manifest["roles"].append(
            {
                "roleId": role_id,
                "order": order,
                "payloadFile": payload_path.name,
                "promptFile": prompt_path.name,
            }
        )

    manifest_path = bundle_root / "manifest.json"
    save_json(manifest_path, manifest)
    result = dict(payload_result)
    result["bundleDir"] = str(bundle_root)
    result["manifestFile"] = str(manifest_path)
    return result


def init_executor(report_dir: Path, flow: str, mode: str) -> dict[str, object]:
    report_dir.mkdir(parents=True, exist_ok=True)
    flow_id = normalize_flow(flow)
    normalized_mode = normalize_mode(flow_id, mode)
    plan = build_plan(flow_id, normalized_mode)
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
    }


def read_executor_state(report_dir: Path) -> tuple[dict[str, object], dict[str, object], dict[str, object], list[object]]:
    plan = load_json(report_dir / "STAGE-SUBAGENT-PLAN.json", {})
    approvals = load_json(report_dir / "approval-records.json", {})
    rejections = load_json(report_dir / "rejection-count.json", {})
    stage_log = load_json(report_dir / "stage-transition-log.json", [])
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
    with STATE_LOCK:
        stage_log = load_json(stage_log_path, [])
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
    return {"status": "recorded", "event": "approval-requested", "stageId": stage_id}


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
    return {"status": "recorded", "event": f"approval-{response}", "stageId": stage_id}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Initialize report-dir state and generate STAGE-SUBAGENT-PLAN.json")
    init_parser.add_argument("--report-dir", required=True)
    init_parser.add_argument("--flow", required=True)
    init_parser.add_argument("--mode", default="standard")

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
        result = init_executor(report_dir, args.flow, args.mode)
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
