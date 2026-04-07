#!/usr/bin/env python3
"""Multi-turn runner backed by the strict skill invocation harness."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from sandbox_skill_invoke import PROJECT_DIR
from sandbox_skill_invoke.core import kv, read_text, write_text


def parse_kv_output(output: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute a multi-turn conversation against a skill.")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--skill-path", required=True)
    parser.add_argument("--conversation-file", required=True)
    parser.add_argument("--channel", default="telegram")
    parser.add_argument("--mode", default="auto", choices=("auto", "live", "shim-live", "trace"))
    parser.add_argument("--timeout-per-turn", type=int, default=60)
    parser.add_argument("--strict-real", action="store_true")
    parser.add_argument("--sandbox-root")
    parser.add_argument("--verification-manifest")
    args = parser.parse_args()

    sandbox_root = Path(args.sandbox_root).resolve() if args.sandbox_root else PROJECT_DIR / ".nexus-sandbox"
    session_dir = sandbox_root / args.session_id
    if not session_dir.exists():
        raise SystemExit(f"ERROR: Session does not exist: {session_dir}")

    workspace_dir = session_dir / "workspace"
    outputs_dir = workspace_dir / "outputs"
    logs_dir = session_dir / "logs"
    state_dir = workspace_dir / "state"
    for path in (outputs_dir, logs_dir, state_dir):
        path.mkdir(parents=True, exist_ok=True)

    conversation_file = Path(args.conversation_file)
    if not conversation_file.is_absolute():
        candidate = (workspace_dir / conversation_file).resolve()
        if candidate.exists():
            conversation_file = candidate
        else:
            conversation_file = conversation_file.resolve()
    if not conversation_file.exists():
        raise SystemExit(f"ERROR: Conversation file not found: {args.conversation_file}")

    payload = json.loads(read_text(conversation_file))
    turns = payload.get("turns", [])
    description = payload.get("description", "Multi-turn test")
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    history_file = state_dir / f"{timestamp}-multi-turn-history.json"
    log_file = logs_dir / f"{timestamp}-multi-turn.json"
    summary_file = outputs_dir / f"{timestamp}-multi-turn-summary.md"
    write_text(history_file, "[]\n")

    script_dir = Path(__file__).resolve().parent
    invoke_script = script_dir / "sandbox_skill_invoke.py"
    history: list[dict[str, str]] = []
    results: list[dict[str, object]] = []

    for index, turn in enumerate(turns, start=1):
        message = str(turn.get("message", ""))
        expect_trigger = turn.get("expect_trigger", True)
        expect_tools = [str(item) for item in turn.get("expect_tools", [])]
        expect_context_from_turn = turn.get("expect_context_from_turn")
        expect_delivery_status = turn.get("expect_delivery_status")
        require_delivery_evidence = bool(turn.get("require_delivery_evidence", False))
        write_text(history_file, json.dumps(history, ensure_ascii=False, indent=2) + "\n")

        cmd = [
            sys.executable,
            str(invoke_script),
            "--session-id",
            args.session_id,
            "--skill-path",
            args.skill_path,
            "--message",
            message,
            "--channel",
            args.channel,
            "--mode",
            args.mode,
            "--timeout",
            str(args.timeout_per_turn),
            "--history-file",
            str(history_file),
            "--sandbox-root",
            str(sandbox_root),
        ]
        if args.strict_real:
            cmd.append("--strict-real")
        if args.verification_manifest:
            cmd.extend(["--verification-manifest", args.verification_manifest])
        if expect_trigger is True:
            cmd.extend(["--expect-trigger", "true"])
        elif expect_trigger is False:
            cmd.extend(["--expect-trigger", "false"])
        if expect_tools:
            cmd.extend(["--require-tools", ",".join(expect_tools)])
        if expect_context_from_turn is not None:
            cmd.extend(["--expect-context-ref", str(expect_context_from_turn)])
        if expect_delivery_status:
            cmd.extend(["--require-delivery-status", str(expect_delivery_status)])
        if require_delivery_evidence:
            cmd.append("--require-delivery-evidence")

        turn_result: dict[str, object] = {
            "turnNumber": index,
            "message": message,
            "expectTrigger": expect_trigger,
            "expectTools": expect_tools,
            "expectContextFromTurn": expect_context_from_turn,
            "expectDeliveryStatus": expect_delivery_status,
            "requireDeliveryEvidence": require_delivery_evidence,
        }

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        parsed = parse_kv_output(proc.stdout)
        turn_result["exitCode"] = proc.returncode
        turn_result["invokeOutput"] = proc.stdout[:4000]
        turn_result["invokeError"] = proc.stderr[:2000]
        turn_result["selectedMode"] = parsed.get("SELECTED_MODE", "unknown")
        turn_result["executionLevel"] = parsed.get("EXECUTION_LEVEL", "unknown")
        turn_result["realExecuted"] = parsed.get("REAL_EXECUTED", "false")
        turn_result["telemetryTrust"] = parsed.get("TELEMETRY_TRUST", "unknown")
        turn_result["triggerMatched"] = parsed.get("TRIGGER_MATCHED", "unknown")
        turn_result["toolsCalled"] = parsed.get("TOOLS_CALLED", "unknown")
        turn_result["deliveryStatus"] = parsed.get("DELIVERY_STATUS", "unknown")
        turn_result["deliveryReceipts"] = parsed.get("DELIVERY_RECEIPTS", "unknown")
        turn_result["deliveryEvidence"] = parsed.get("DELIVERY_EVIDENCE", "unknown")
        turn_result["invalidDeliveryEvidence"] = parsed.get("INVALID_DELIVERY_EVIDENCE", "")
        turn_result["contextReferences"] = parsed.get("CONTEXT_REFERENCES", "unknown")
        turn_result["invokeStatus"] = parsed.get("INVOKE_STATUS", "unknown")
        turn_result["verificationStatus"] = parsed.get("VERIFICATION_STATUS", "not-configured")
        turn_result["verifierSource"] = parsed.get("VERIFIER_SOURCE", "none")
        turn_result["assertionsPassed"] = parsed.get("ASSERTIONS_PASSED", "unknown")
        turn_result["assertionFailures"] = parsed.get("ASSERTION_FAILURES", "")

        output_text = ""
        output_file = parsed.get("OUTPUT_FILE")
        if output_file:
            output_path = Path(output_file)
            if output_path.exists():
                output_text = read_text(output_path)
        turn_result["outputExcerpt"] = output_text[:2000]
        result_json_path_text = parsed.get("RESULT_JSON_FILE")
        if result_json_path_text:
            result_json_path = Path(result_json_path_text)
            if result_json_path.exists():
                try:
                    turn_result["resultPayload"] = json.loads(read_text(result_json_path))
                except json.JSONDecodeError:
                    turn_result["resultPayload"] = {}

        passed = proc.returncode == 0
        notes: list[str] = []

        if args.strict_real and parsed.get("REAL_EXECUTED") != "true":
            passed = False
            notes.append("Strict real execution required, but the turn did not execute at live/shim-live level.")
        if parsed.get("ASSERTIONS_PASSED") == "false":
            passed = False
            failures = parsed.get("ASSERTION_FAILURES", "").strip()
            if failures:
                notes.append(f"Invocation assertions failed: {failures}")
            else:
                notes.append("Invocation assertions failed.")
        elif proc.returncode != 0 and not notes:
            notes.append(f"Invocation failed with status {parsed.get('INVOKE_STATUS', 'unknown')}.")

        turn_result["passed"] = passed
        turn_result["notes"] = notes
        results.append(turn_result)

        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": output_text})

    passed_turns = sum(1 for item in results if item.get("passed"))
    failed_turns = len(results) - passed_turns
    if failed_turns == 0:
        status = "all-passed"
    elif passed_turns == 0:
        status = "all-failed"
    else:
        status = "partial-pass"

    context_checks = [item for item in results if item.get("expectContextFromTurn") is not None]
    if not context_checks:
        context_preservation = "not-tested"
    elif all(item.get("passed") for item in context_checks):
        context_preservation = "verified"
    elif any(item.get("passed") for item in context_checks):
        context_preservation = "partial"
    else:
        context_preservation = "failed"

    result_payload = {
        "description": description,
        "channel": args.channel,
        "modeRequested": args.mode,
        "strictReal": args.strict_real,
        "verificationManifest": args.verification_manifest or "",
        "totalTurns": len(results),
        "passedTurns": passed_turns,
        "failedTurns": failed_turns,
        "contextPreservation": context_preservation,
        "status": status,
        "historyFile": str(history_file),
        "turns": results,
    }
    write_text(log_file, json.dumps(result_payload, ensure_ascii=False, indent=2) + "\n")

    summary_lines = [
        "# Multi-Turn Conversation Test Summary",
        "",
        "## Overview",
        f"- Description: {description}",
        f"- Channel: {args.channel}",
        f"- Requested Mode: {args.mode}",
        f"- Strict Real: {'true' if args.strict_real else 'false'}",
        f"- Verification Manifest: {args.verification_manifest or 'none'}",
        f"- Total Turns: {len(results)}",
        f"- Passed: {passed_turns}",
        f"- Failed: {failed_turns}",
        f"- Context Preservation: {context_preservation}",
        f"- Status: {status}",
        "",
        "## Turn Details",
        "",
    ]

    for item in results:
        icon = "PASS" if item.get("passed") else "FAIL"
        summary_lines.append(f"### Turn {item['turnNumber']} {icon}")
        summary_lines.append(f"- Message: {str(item['message'])[:120]}")
        summary_lines.append(f"- Execution Level: {item.get('executionLevel', 'unknown')}")
        summary_lines.append(f"- Telemetry Trust: {item.get('telemetryTrust', 'unknown')}")
        summary_lines.append(f"- Trigger: {item.get('triggerMatched', 'unknown')}")
        summary_lines.append(f"- Tools: {item.get('toolsCalled', 'unknown')}")
        summary_lines.append(f"- Context Refs: {item.get('contextReferences', 'unknown')}")
        summary_lines.append(f"- Delivery: {item.get('deliveryStatus', 'unknown')}")
        if item.get("invalidDeliveryEvidence"):
            summary_lines.append(f"- Invalid Delivery Evidence: {item.get('invalidDeliveryEvidence')}")
        for note in item.get("notes", []):
            summary_lines.append(f"- Note: {note}")
        summary_lines.append("")

    write_text(summary_file, "\n".join(summary_lines))

    kv("MULTI_TURN_STATUS", status)
    kv("TOTAL_TURNS", len(results))
    kv("PASSED_TURNS", passed_turns)
    kv("FAILED_TURNS", failed_turns)
    kv("CONTEXT_PRESERVATION", context_preservation)
    kv("LOG_FILE", log_file)
    kv("SUMMARY_FILE", summary_file)
    kv("HISTORY_FILE", history_file)
    return 0 if failed_turns == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
