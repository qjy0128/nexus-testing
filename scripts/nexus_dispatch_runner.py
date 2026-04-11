#!/usr/bin/env python3
"""Runtime bridge for DISPATCH bundles produced by nexus_stage_executor.py."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import argparse
import json
import sys
import threading
from pathlib import Path

from nexus_stage_executor import (
    append_stage_log,
    bundle_dispatch,
    dispatch_payloads,
    mark_stage_complete,
    next_action,
    now_text,
    read_executor_state,
    resolve_path,
)

from nexus_testing.dispatch_payload_schema import validate_dispatch_payload_list
from nexus_testing.json_utils import load_json
from nexus_testing.sandbox_skill_invoke.core import write_text

STATE_LOCK = threading.RLock()


def save_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def current_bundle(report_dir: Path) -> dict[str, object]:
    plan, approvals, rejections, stage_log = read_executor_state(report_dir)
    actionable = dispatch_payloads(
        report_dir,
        plan,
        next_action(report_dir, plan, approvals, rejections, stage_log),
    )
    return bundle_dispatch(report_dir, actionable)


def runner_root(report_dir: Path, stage_id: str) -> Path:
    return report_dir / "RUNS" / stage_id


def role_state_path(report_dir: Path, stage_id: str, role_id: str) -> Path:
    return runner_root(report_dir, stage_id) / f"{role_id}.state.json"


def prepare_bundle(report_dir: Path) -> dict[str, object]:
    bundle = current_bundle(report_dir)
    status = str(bundle.get("status"))
    if status not in {"run-stage", "run-post-stage"}:
        return bundle
    bundle["dispatchPayloads"] = validate_dispatch_payload_list(bundle.get("dispatchPayloads", []))
    payloads = bundle["dispatchPayloads"]

    stage_id = str(bundle["stageId"])
    run_dir = runner_root(report_dir, stage_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "stageId": stage_id,
        "stageLabel": bundle.get("label"),
        "stageName": bundle.get("name"),
        "dispatchMode": bundle.get("dispatchMode"),
        "status": status,
        "bundleDir": bundle.get("bundleDir"),
        "bundleManifest": bundle.get("manifestFile"),
        "missingDeliverables": bundle.get("missingDeliverables", []),
        "preparedAt": now_text(),
        "executionProfile": payloads[0].get("executionProfile") if payloads else "internal-fast",
        "strictReal": payloads[0].get("strictReal") if payloads else False,
        "executionPolicy": payloads[0].get("executionPolicy", {}) if payloads else {},
        "delivery": payloads[0].get("delivery", {}) if payloads else {},
        "roles": [],
    }

    for payload in payloads:
        role_id = str(payload["roleId"])
        state_path = role_state_path(report_dir, stage_id, role_id)
        if not state_path.exists():
            save_json(
                state_path,
                {
                    "roleId": role_id,
                    "stageId": stage_id,
                    "status": "pending",
                    "attempts": 0,
                    "startedAt": None,
                    "completedAt": None,
                    "failedAt": None,
                    "takeoverAt": None,
                    "takeoverFile": None,
                    "resultFile": None,
                    "note": None,
                    "runtime": None,
                    "runtimeStatus": None,
                },
            )
        role_state = load_json(state_path, {}, label=f"role state {state_path.name}")
        if not isinstance(role_state, dict):
            role_state = {"status": "unknown"}
        manifest["roles"].append(
            {
                "roleId": role_id,
                "stateFile": state_path.name,
                "status": role_state.get("status"),
            }
        )

    manifest_path = run_dir / "run-manifest.json"
    save_json(manifest_path, manifest)
    bundle["runManifest"] = str(manifest_path)
    return bundle


def update_role_state(report_dir: Path, stage_id: str, role_id: str, updater) -> dict[str, object]:
    state_path = role_state_path(report_dir, stage_id, role_id)
    if not state_path.exists():
        raise SystemExit(f"ERROR: role state does not exist: {state_path}")
    with STATE_LOCK:
        state = load_json(state_path, {}, label=f"role state {state_path.name}")
        if not isinstance(state, dict):
            state = {}
        updater(state)
        save_json(state_path, state)
        return state


def start_role(report_dir: Path, stage_id: str, role_id: str, runtime: str) -> dict[str, object]:
    state = update_role_state(
        report_dir,
        stage_id,
        role_id,
        lambda data: data.update(
            {
                "status": "running",
                "attempts": int(data.get("attempts", 0)) + 1,
                "startedAt": now_text(),
                "completedAt": None,
                "failedAt": None,
                "takeoverAt": None,
                "takeoverFile": None,
                "resultFile": None,
                "note": None,
                "runtime": runtime,
                "runtimeStatus": "running",
            }
        ),
    )
    append_stage_log(
        report_dir,
        {
            "from_stage": stage_id,
            "to_stage": stage_id,
            "timestamp": now_text(),
            "deliverable_file": None,
            "approval_required": False,
            "gate_check_passed": False,
            "event": "role-started",
            "role_id": role_id,
        },
    )
    return state


def complete_role(
    report_dir: Path,
    stage_id: str,
    role_id: str,
    result_file: str | None,
    note: str | None,
    *,
    runtime_status: str | None = None,
) -> dict[str, object]:
    resolved_result: str | None = None
    if result_file:
        path = resolve_path(result_file)
        if not path.exists():
            raise SystemExit(f"ERROR: result file does not exist: {path}")
        try:
            resolved_result = str(path.relative_to(report_dir))
        except ValueError:
            resolved_result = str(path)

    state = update_role_state(
        report_dir,
        stage_id,
        role_id,
        lambda data: data.update(
            {
                "status": "completed",
                "completedAt": now_text(),
                "failedAt": None,
                "takeoverAt": None,
                "takeoverFile": None,
                "resultFile": resolved_result,
                "note": note,
                "runtimeStatus": runtime_status or "completed",
            }
        ),
    )
    append_stage_log(
        report_dir,
        {
            "from_stage": stage_id,
            "to_stage": stage_id,
            "timestamp": now_text(),
            "deliverable_file": resolved_result,
            "approval_required": False,
            "gate_check_passed": False,
            "event": "role-completed",
            "role_id": role_id,
            "runtime_status": runtime_status or "completed",
        },
    )
    return state


def fail_role(
    report_dir: Path,
    stage_id: str,
    role_id: str,
    note: str | None,
    *,
    runtime_status: str | None = None,
) -> dict[str, object]:
    state = update_role_state(
        report_dir,
        stage_id,
        role_id,
        lambda data: data.update(
            {
                "status": "failed",
                "completedAt": None,
                "failedAt": now_text(),
                "takeoverAt": None,
                "takeoverFile": None,
                "note": note,
                "runtimeStatus": runtime_status or "failed",
            }
        ),
    )
    append_stage_log(
        report_dir,
        {
            "from_stage": stage_id,
            "to_stage": stage_id,
            "timestamp": now_text(),
            "deliverable_file": None,
            "approval_required": False,
            "gate_check_passed": False,
            "event": "role-failed",
            "role_id": role_id,
            "reason": note,
            "runtime_status": runtime_status or "failed",
        },
    )
    return state


def takeover_role(
    report_dir: Path,
    stage_id: str,
    role_id: str,
    note: str | None,
    takeover_file: str | None,
    *,
    runtime_status: str | None = None,
) -> dict[str, object]:
    resolved_takeover: str | None = None
    if takeover_file:
        path = resolve_path(takeover_file)
        if not path.exists():
            raise SystemExit(f"ERROR: takeover file does not exist: {path}")
        try:
            resolved_takeover = str(path.relative_to(report_dir))
        except ValueError:
            resolved_takeover = str(path)

    state = update_role_state(
        report_dir,
        stage_id,
        role_id,
        lambda data: data.update(
            {
                "status": "takeover-required",
                "completedAt": None,
                "failedAt": None,
                "takeoverAt": now_text(),
                "takeoverFile": resolved_takeover,
                "note": note,
                "runtimeStatus": runtime_status or "takeover-required",
            }
        ),
    )
    append_stage_log(
        report_dir,
        {
            "from_stage": stage_id,
            "to_stage": stage_id,
            "timestamp": now_text(),
            "deliverable_file": resolved_takeover,
            "approval_required": False,
            "gate_check_passed": False,
            "event": "role-takeover-required",
            "role_id": role_id,
            "reason": note,
            "runtime_status": runtime_status or "takeover-required",
        },
    )
    return state


def stage_run_status(report_dir: Path, stage_id: str) -> dict[str, object]:
    run_dir = runner_root(report_dir, stage_id)
    role_states = []
    for path in sorted(run_dir.glob("*.state.json")):
        payload = load_json(path, {}, label=f"role state {path.name}")
        if isinstance(payload, dict):
            role_states.append(payload)
    completed = [item for item in role_states if item.get("status") == "completed"]
    failed = [item for item in role_states if item.get("status") == "failed"]
    takeover_required = [item for item in role_states if item.get("status") == "takeover-required"]
    running = [item for item in role_states if item.get("status") == "running"]
    pending = [item for item in role_states if item.get("status") == "pending"]
    runtime_status_counts: dict[str, int] = {}
    for item in role_states:
        runtime_status = str(item.get("runtimeStatus") or "").strip()
        if not runtime_status:
            continue
        runtime_status_counts[runtime_status] = runtime_status_counts.get(runtime_status, 0) + 1
    return {
        "stageId": stage_id,
        "roleStates": role_states,
        "completedCount": len(completed),
        "failedCount": len(failed),
        "takeoverRequiredCount": len(takeover_required),
        "runningCount": len(running),
        "pendingCount": len(pending),
        "totalCount": len(role_states),
        "allCompleted": len(role_states) > 0 and len(completed) == len(role_states),
        "runtimeStatusCounts": runtime_status_counts,
    }


def stage_completion_artifacts(run_status: dict[str, object]) -> str | None:
    artifacts: list[str] = []
    for item in run_status.get("roleStates", []):
        if not isinstance(item, dict):
            continue
        result_file = item.get("resultFile")
        if result_file:
            artifacts.append(str(result_file))
    if not artifacts:
        return None
    return ", ".join(artifacts)


def advance(report_dir: Path) -> dict[str, object]:
    bundle = prepare_bundle(report_dir)
    status = str(bundle.get("status"))
    if status not in {"run-stage", "run-post-stage"}:
        return bundle

    stage_id = str(bundle["stageId"])
    run_status = stage_run_status(report_dir, stage_id)
    if not run_status["allCompleted"]:
        return {
            "status": "waiting-role-completion",
            "stageId": stage_id,
            "runStatus": run_status,
        }

    plan, approvals, rejections, stage_log = read_executor_state(report_dir)
    current = next_action(report_dir, plan, approvals, rejections, stage_log)
    if current.get("status") not in {"run-stage", "run-post-stage"}:
        return {"status": "desynced", "currentAction": current, "runStatus": run_status}

    append_stage_log(
        report_dir,
        {
            "from_stage": stage_id,
            "to_stage": stage_id,
            "timestamp": now_text(),
            "deliverable_file": ", ".join(str(item) for item in current.get("missingDeliverables", [])),
            "approval_required": False,
            "gate_check_passed": True,
            "event": "dispatch-run-complete",
        },
    )
    stage_complete = mark_stage_complete(
        report_dir,
        stage_id,
        stage_completion_artifacts(run_status),
    )

    next_bundle = current_bundle(report_dir)
    return {
        "status": "advanced",
        "completedStageId": stage_id,
        "stageCompleteEvent": stage_complete,
        "nextAction": next_bundle,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare", help="Prepare current stage RUNS manifest from DISPATCH bundle")
    prepare_parser.add_argument("--report-dir", required=True)

    status_parser = sub.add_parser("status", help="Show RUNS status for current actionable stage")
    status_parser.add_argument("--report-dir", required=True)

    start_parser = sub.add_parser("start-role", help="Mark a role as running")
    start_parser.add_argument("--report-dir", required=True)
    start_parser.add_argument("--stage-id", required=True)
    start_parser.add_argument("--role-id", required=True)
    start_parser.add_argument("--runtime", default="external-runtime")

    complete_parser = sub.add_parser("complete-role", help="Mark a role as completed")
    complete_parser.add_argument("--report-dir", required=True)
    complete_parser.add_argument("--stage-id", required=True)
    complete_parser.add_argument("--role-id", required=True)
    complete_parser.add_argument("--result-file")
    complete_parser.add_argument("--note")

    fail_parser = sub.add_parser("fail-role", help="Mark a role as failed")
    fail_parser.add_argument("--report-dir", required=True)
    fail_parser.add_argument("--stage-id", required=True)
    fail_parser.add_argument("--role-id", required=True)
    fail_parser.add_argument("--note")

    takeover_parser = sub.add_parser("takeover-role", help="Mark a role as requiring main-agent takeover")
    takeover_parser.add_argument("--report-dir", required=True)
    takeover_parser.add_argument("--stage-id", required=True)
    takeover_parser.add_argument("--role-id", required=True)
    takeover_parser.add_argument("--note")
    takeover_parser.add_argument("--takeover-file")

    advance_parser = sub.add_parser("advance", help="Advance if all roles in current RUNS bundle are completed")
    advance_parser.add_argument("--report-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    report_dir = resolve_path(args.report_dir)

    if args.command == "prepare":
        result = prepare_bundle(report_dir)
    elif args.command == "status":
        bundle = prepare_bundle(report_dir)
        if str(bundle.get("status")) not in {"run-stage", "run-post-stage"}:
            result = bundle
        else:
            result = stage_run_status(report_dir, str(bundle["stageId"]))
    elif args.command == "start-role":
        result = start_role(report_dir, args.stage_id, args.role_id, args.runtime)
    elif args.command == "complete-role":
        result = complete_role(report_dir, args.stage_id, args.role_id, args.result_file, args.note)
    elif args.command == "fail-role":
        result = fail_role(report_dir, args.stage_id, args.role_id, args.note)
    elif args.command == "takeover-role":
        result = takeover_role(report_dir, args.stage_id, args.role_id, args.note, args.takeover_file)
    elif args.command == "advance":
        result = advance(report_dir)
    else:
        raise SystemExit(f"ERROR: unsupported command {args.command}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
