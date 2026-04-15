#!/usr/bin/env python3
"""Convenience demo runner for OpenClaw-oriented stage orchestration."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from generate_stage_subagent_plan import normalize_flow, normalize_mode
from nexus_runtime_bridge import load_runtime_config, orchestration_settings, run_until_gate
from nexus_stage_executor import (
    approval_required,
    append_stage_log,
    init_executor,
    next_action,
    now_text,
    normalize_report_deliverable,
    process_approval_timeout,
    read_executor_state,
    record_approval_request,
    record_approval_response,
    resolve_path,
    stage_key,
)

ROOT = Path(__file__).resolve().parents[1]


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cleanup_empty_parents(path: Path, stop: Path) -> None:
    current = path
    stop = stop.resolve()
    while current.exists() and current.resolve() != stop:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _iter_stage_artifact_paths(report_dir: Path, stage: dict[str, object]) -> list[Path]:
    discovered: dict[str, Path] = {}
    for field in ("deliverables", "postStageDeliverables"):
        for item in stage.get(field, []):
            normalized = normalize_report_deliverable(item)
            if not normalized:
                continue
            if any(token in normalized for token in "*?["):
                for candidate in sorted(report_dir.glob(normalized)):
                    if not candidate.exists():
                        continue
                    relative = str(candidate.relative_to(report_dir)).replace("\\", "/")
                    discovered[relative] = candidate
                continue
            candidate = report_dir / normalized
            if not candidate.exists():
                continue
            relative = str(candidate.relative_to(report_dir)).replace("\\", "/")
            discovered[relative] = candidate
    return [discovered[key] for key in sorted(discovered)]


def _recovery_archive_dir(report_dir: Path, from_stage: str) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    base = report_dir / "archive" / f"recovery-{from_stage}-{timestamp}"
    candidate = base
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = report_dir / "archive" / f"recovery-{from_stage}-{timestamp}-{suffix}"
    return candidate


def archive_stages_for_recovery(
    report_dir: Path,
    stages: list[dict[str, object]],
    *,
    from_stage: str,
) -> tuple[Path | None, list[str]]:
    artifact_map: dict[str, Path] = {}
    for stage in stages:
        for artifact_path in _iter_stage_artifact_paths(report_dir, stage):
            relative = str(artifact_path.relative_to(report_dir)).replace("\\", "/")
            artifact_map[relative] = artifact_path

    if not artifact_map:
        return None, []

    archive_dir = _recovery_archive_dir(report_dir, from_stage)
    archived: list[str] = []
    for relative, source in sorted(artifact_map.items()):
        destination = archive_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        archived.append(relative)
        _cleanup_empty_parents(source.parent, report_dir)
    return archive_dir, archived


def clear_gate_state_from_stage(
    report_dir: Path,
    stages: list[dict[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    plan, approvals, rejections, _ = read_executor_state(report_dir)
    if not isinstance(approvals, dict):
        approvals = {}
    if not isinstance(rejections, dict):
        rejections = {}

    for stage in stages:
        if not approval_required(stage):
            continue
        approvals.pop(stage_key(str(stage.get("stageId"))), None)
        rejections.pop(stage_key(str(stage.get("stageId"))), None)

    save_json(report_dir / "approval-records.json", approvals)
    save_json(report_dir / "rejection-count.json", rejections)
    return approvals, rejections


def ensure_initialized(report_dir: Path, flow: str, mode: str) -> dict[str, object]:
    plan_file = report_dir / "STAGE-SUBAGENT-PLAN.json"
    if plan_file.exists():
        plan, _, _, _ = read_executor_state(report_dir)
        requested_flow = normalize_flow(flow)
        requested_mode = normalize_mode(requested_flow, mode)
        actual_flow = str(plan.get("flowId"))
        actual_mode = str(plan.get("mode"))
        if actual_flow != requested_flow or actual_mode != requested_mode:
            raise SystemExit(
                "ERROR: existing report-dir plan does not match requested flow/mode: "
                f"requested {requested_flow}/{requested_mode}, found {actual_flow}/{actual_mode}"
            )
        return {
            "status": "reused",
            "reportDir": str(report_dir),
            "planFile": str(plan_file),
        }
    return init_executor(report_dir, flow, mode)


def build_summary(report_dir: Path, runtime_result: dict[str, object]) -> dict[str, object]:
    plan, approvals, rejections, stage_log = read_executor_state(report_dir)
    return {
        "status": str(runtime_result.get("status")),
        "reportDir": str(report_dir),
        "flowId": plan.get("flowId"),
        "mode": plan.get("mode"),
        "stageLogEntries": len(stage_log),
        "approvalRecords": approvals,
        "rejections": rejections,
        "runtimeResult": runtime_result,
    }


def approval_record_for_stage(report_dir: Path, stage_id: str) -> dict[str, object] | None:
    _, approvals, _, _ = read_executor_state(report_dir)
    record = approvals.get(stage_key(stage_id))
    return record if isinstance(record, dict) else None


def ensure_gate_request_recorded(report_dir: Path, runtime_result: dict[str, object]) -> dict[str, object] | None:
    if str(runtime_result.get("status")) != "await-approval":
        return None
    gate_action = runtime_result.get("gateAction", {})
    if not isinstance(gate_action, dict):
        gate_action = runtime_result
    stage_id = str(gate_action.get("stageId") or "").strip()
    if not stage_id:
        return None
    record = approval_record_for_stage(report_dir, stage_id)
    if record and str(record.get("sent_at") or "").strip():
        return {"status": "already-recorded", "stageId": stage_id}
    return record_approval_request(report_dir, stage_id, "text", None)


def reconcile_approval_timeouts(report_dir: Path) -> dict[str, object] | None:
    if not (report_dir / "STAGE-SUBAGENT-PLAN.json").exists():
        return None
    result = process_approval_timeout(report_dir)
    if str(result.get("status")) == "idle":
        return None
    return result


def detect_existing(report_dir: Path) -> dict[str, object]:
    """Scan report-dir state and return a recovery recommendation."""
    plan_file = report_dir / "STAGE-SUBAGENT-PLAN.json"
    if not plan_file.exists():
        return {"status": "no-session", "reportDir": str(report_dir), "recommendation": "start a new session with the 'start' command"}

    timeout_action = reconcile_approval_timeouts(report_dir)
    plan, approvals, rejections, stage_log = read_executor_state(report_dir)
    action = next_action(report_dir, plan, approvals, rejections, stage_log)
    action_status = str(action.get("status"))
    stages = [str(stage.get("stageId")) for stage in plan.get("stages", []) if isinstance(stage, dict)]
    stage_positions = {stage_id: index for index, stage_id in enumerate(stages)}

    completed_stages = [
        str(entry.get("to_stage"))
        for entry in stage_log
        if isinstance(entry, dict) and entry.get("event") == "stage-complete"
    ]
    last_completed = completed_stages[-1] if completed_stages else None
    pending_stage = str(action.get("stageId")) if action.get("stageId") else None

    if action_status == "complete":
        result = {
            "status": "session-complete",
            "reportDir": str(report_dir),
            "flowId": plan.get("flowId"),
            "mode": plan.get("mode"),
            "lastCompletedStage": stages[-1] if stages else last_completed,
            "recommendation": "all stages finished — no recovery needed",
        }
        if timeout_action:
            result["timeoutAction"] = timeout_action
        return result

    if action_status == "await-approval":
        result = {
            "status": "awaiting-approval",
            "reportDir": str(report_dir),
            "flowId": plan.get("flowId"),
            "mode": plan.get("mode"),
            "lastCompletedStage": pending_stage or last_completed,
            "pendingStageId": pending_stage,
            "recommendation": f"run: approve --stage-id {pending_stage} --continue-run",
        }
        if timeout_action:
            result["timeoutAction"] = timeout_action
        return result

    if pending_stage in stage_positions and stage_positions[pending_stage] > 0:
        last_completed = stages[stage_positions[pending_stage] - 1]
    result = {
        "status": "recoverable",
        "reportDir": str(report_dir),
        "flowId": plan.get("flowId"),
        "mode": plan.get("mode"),
        "lastCompletedStage": last_completed,
        "pendingStageId": pending_stage,
        "missingDeliverables": action.get("missingDeliverables", []),
        "recommendation": f"run: recover --report-dir {report_dir} to resume from stage {pending_stage}",
        "stageLogEntries": len(stage_log),
    }
    if timeout_action:
        result["timeoutAction"] = timeout_action
    return result


def recover_session(
    report_dir: Path,
    runtime_config: dict[str, object],
    from_stage: str | None,
    max_cycles: int,
) -> dict[str, object]:
    """Resume a session from the last incomplete stage (or from_stage if specified)."""
    if not (report_dir / "STAGE-SUBAGENT-PLAN.json").exists():
        raise SystemExit(f"ERROR: no session found at {report_dir} — use 'start' to create one")

    plan, approvals, rejections, stage_log = read_executor_state(report_dir)

    if from_stage:
        stages = list(plan.get("stages", []))
        stage_ids = [str(s["stageId"]) for s in stages]
        if from_stage not in stage_ids:
            raise SystemExit(f"ERROR: stage '{from_stage}' not found in plan; valid stages: {stage_ids}")
        from_index = stage_ids.index(from_stage)
        recovery_stages = stages[from_index:]
        archive_dir, archived = archive_stages_for_recovery(
            report_dir,
            recovery_stages,
            from_stage=from_stage,
        )
        clear_gate_state_from_stage(report_dir, recovery_stages)
        append_stage_log(
            report_dir,
            {
                "from_stage": "recovery",
                "to_stage": from_stage,
                "timestamp": now_text(),
                "deliverable_file": None,
                "approval_required": False,
                "gate_check_passed": False,
                "event": "manual-recovery",
                "recovery_reason": f"user requested recovery from stage {from_stage}",
                "archive_dir": str(archive_dir) if archive_dir else None,
                "archived_artifacts": archived,
            },
        )

    plan, approvals, rejections, stage_log = read_executor_state(report_dir)
    action = next_action(report_dir, plan, approvals, rejections, stage_log)
    runtime_result = run_until_gate(report_dir, runtime_config, max_cycles, orchestration_settings(report_dir))
    gate_request = ensure_gate_request_recorded(report_dir, runtime_result)
    return {
        "command": "recover",
        "reportDir": str(report_dir),
        "resumedAt": action.get("stageId"),
        "recovery": {
            "fromStage": from_stage,
        },
        "approvalRequest": gate_request,
        "summary": build_summary(report_dir, runtime_result),
    }


def approve_stage(report_dir: Path, stage_id: str, reason: str | None) -> dict[str, object]:
    record = approval_record_for_stage(report_dir, stage_id)
    if record and str(record.get("sent_at") or "").strip():
        requested = {"status": "already-recorded", "stageId": stage_id}
    else:
        requested = record_approval_request(report_dir, stage_id, "text", None)
    approved = record_approval_response(report_dir, stage_id, "approved", reason)
    return {
        "status": "approved",
        "stageId": stage_id,
        "requestEvent": requested,
        "responseEvent": approved,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    start_parser = sub.add_parser("start", help="Initialize report-dir if needed and run until the first approval gate")
    start_parser.add_argument("--report-dir", required=True)
    start_parser.add_argument("--flow", default="skill")
    start_parser.add_argument("--mode", default="standard")
    start_parser.add_argument("--runtime-config", default="runtime-config.openclaw.json")
    start_parser.add_argument("--max-cycles", type=int, default=20)

    continue_parser = sub.add_parser("continue", help="Resume an existing report-dir and run until the next gate")
    continue_parser.add_argument("--report-dir", required=True)
    continue_parser.add_argument("--runtime-config", default="runtime-config.openclaw.json")
    continue_parser.add_argument("--max-cycles", type=int, default=20)

    approve_parser = sub.add_parser("approve", help="Record approval for a stage and optionally continue execution")
    approve_parser.add_argument("--report-dir", required=True)
    approve_parser.add_argument("--stage-id", required=True)
    approve_parser.add_argument("--reason")
    approve_parser.add_argument("--runtime-config", default="runtime-config.openclaw.json")
    approve_parser.add_argument("--continue-run", action="store_true")
    approve_parser.add_argument("--max-cycles", type=int, default=20)

    detect_parser = sub.add_parser("detect-existing", help="Inspect an existing report-dir and recommend recovery action")
    detect_parser.add_argument("--report-dir", required=True)

    recover_parser = sub.add_parser("recover", help="Resume an interrupted session from the last incomplete stage")
    recover_parser.add_argument("--report-dir", required=True)
    recover_parser.add_argument("--from-stage", help="Force recovery from a specific stage ID (optional)")
    recover_parser.add_argument("--runtime-config", default="runtime-config.openclaw.json")
    recover_parser.add_argument("--max-cycles", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    report_dir = resolve_path(args.report_dir)

    if args.command == "start":
        runtime_config = load_runtime_config(args.runtime_config)
        init_result = ensure_initialized(report_dir, args.flow, args.mode)
        timeout_action = reconcile_approval_timeouts(report_dir)
        runtime_result = run_until_gate(report_dir, runtime_config, args.max_cycles, orchestration_settings(report_dir))
        gate_request = ensure_gate_request_recorded(report_dir, runtime_result)
        result = {
            "command": "start",
            "initResult": init_result,
            "timeoutAction": timeout_action,
            "approvalRequest": gate_request,
            "summary": build_summary(report_dir, runtime_result),
        }
    elif args.command == "continue":
        runtime_config = load_runtime_config(args.runtime_config)
        timeout_action = reconcile_approval_timeouts(report_dir)
        runtime_result = run_until_gate(report_dir, runtime_config, args.max_cycles, orchestration_settings(report_dir))
        gate_request = ensure_gate_request_recorded(report_dir, runtime_result)
        result = {
            "command": "continue",
            "timeoutAction": timeout_action,
            "approvalRequest": gate_request,
            "summary": build_summary(report_dir, runtime_result),
        }
    elif args.command == "approve":
        approval_result = approve_stage(report_dir, args.stage_id, args.reason)
        result = {
            "command": "approve",
            "approval": approval_result,
        }
        if args.continue_run:
            runtime_config = load_runtime_config(args.runtime_config)
            timeout_action = reconcile_approval_timeouts(report_dir)
            runtime_result = run_until_gate(report_dir, runtime_config, args.max_cycles, orchestration_settings(report_dir))
            gate_request = ensure_gate_request_recorded(report_dir, runtime_result)
            result["timeoutAction"] = timeout_action
            result["approvalRequest"] = gate_request
            result["summary"] = build_summary(report_dir, runtime_result)
    elif args.command == "detect-existing":
        result = detect_existing(report_dir)
    elif args.command == "recover":
        runtime_config = load_runtime_config(args.runtime_config)
        result = recover_session(report_dir, runtime_config, getattr(args, "from_stage", None), args.max_cycles)
    else:
        raise SystemExit(f"ERROR: unsupported command {args.command}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
