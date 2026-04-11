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
    init_executor,
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
    else:
        raise SystemExit(f"ERROR: unsupported command {args.command}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
