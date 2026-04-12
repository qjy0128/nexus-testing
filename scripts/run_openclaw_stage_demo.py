#!/usr/bin/env python3
"""Convenience demo runner for OpenClaw-oriented stage orchestration."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import argparse
import json
import sys
from pathlib import Path

from generate_stage_subagent_plan import normalize_flow, normalize_mode
from nexus_runtime_bridge import load_runtime_config, orchestration_settings, run_until_gate
from nexus_stage_executor import (
    append_stage_log,
    init_executor,
    next_action,
    now_text,
    read_executor_state,
    record_approval_request,
    record_approval_response,
    resolve_path,
)

ROOT = Path(__file__).resolve().parents[1]


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


def detect_existing(report_dir: Path) -> dict[str, object]:
    """Scan report-dir state and return a recovery recommendation."""
    plan_file = report_dir / "STAGE-SUBAGENT-PLAN.json"
    if not plan_file.exists():
        return {"status": "no-session", "reportDir": str(report_dir), "recommendation": "start a new session with the 'start' command"}

    plan, approvals, rejections, stage_log = read_executor_state(report_dir)
    action = next_action(report_dir, plan, approvals, rejections, stage_log)
    action_status = str(action.get("status"))

    completed_stages = [
        str(entry.get("to_stage"))
        for entry in stage_log
        if isinstance(entry, dict) and entry.get("event") == "stage-complete"
    ]
    last_completed = completed_stages[-1] if completed_stages else None

    if action_status == "done":
        return {
            "status": "session-complete",
            "reportDir": str(report_dir),
            "flowId": plan.get("flowId"),
            "mode": plan.get("mode"),
            "lastCompletedStage": last_completed,
            "recommendation": "all stages finished — no recovery needed",
        }

    if action_status == "await-approval":
        return {
            "status": "awaiting-approval",
            "reportDir": str(report_dir),
            "flowId": plan.get("flowId"),
            "mode": plan.get("mode"),
            "lastCompletedStage": last_completed,
            "pendingStageId": action.get("stageId"),
            "recommendation": f"run: approve --stage-id {action.get('stageId')} --continue-run",
        }

    pending_stage = action.get("stageId")
    return {
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
            },
        )

    action = next_action(report_dir, plan, approvals, rejections, stage_log)
    runtime_result = run_until_gate(report_dir, runtime_config, max_cycles, orchestration_settings(report_dir))
    return {
        "command": "recover",
        "reportDir": str(report_dir),
        "resumedAt": action.get("stageId"),
        "summary": build_summary(report_dir, runtime_result),
    }


def approve_stage(report_dir: Path, stage_id: str, reason: str | None) -> dict[str, object]:
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
    runtime_config = load_runtime_config(getattr(args, "runtime_config", "runtime-config.openclaw.json"))

    if args.command == "start":
        init_result = ensure_initialized(report_dir, args.flow, args.mode)
        runtime_result = run_until_gate(report_dir, runtime_config, args.max_cycles, orchestration_settings(report_dir))
        result = {
            "command": "start",
            "initResult": init_result,
            "summary": build_summary(report_dir, runtime_result),
        }
    elif args.command == "continue":
        runtime_result = run_until_gate(report_dir, runtime_config, args.max_cycles, orchestration_settings(report_dir))
        result = {
            "command": "continue",
            "summary": build_summary(report_dir, runtime_result),
        }
    elif args.command == "approve":
        approval_result = approve_stage(report_dir, args.stage_id, args.reason)
        result = {
            "command": "approve",
            "approval": approval_result,
        }
        if args.continue_run:
            runtime_result = run_until_gate(report_dir, runtime_config, args.max_cycles, orchestration_settings(report_dir))
            result["summary"] = build_summary(report_dir, runtime_result)
    elif args.command == "detect-existing":
        result = detect_existing(report_dir)
    elif args.command == "recover":
        result = recover_session(report_dir, runtime_config, getattr(args, "from_stage", None), args.max_cycles)
    else:
        raise SystemExit(f"ERROR: unsupported command {args.command}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
