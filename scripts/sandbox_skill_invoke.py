#!/usr/bin/env python3
"""Skill invocation harness with strict real-execution gating."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from nexus_testing.sandbox_skill_invoke.adapter import detect_adapter
from nexus_testing.sandbox_skill_invoke.assertions import (
    collect_delivery_metadata,
    evaluate_assertions,
    normalize_context_references,
)
from nexus_testing.sandbox_skill_invoke.audit import append_audit_entry
from nexus_testing.sandbox_skill_invoke.core import (
    PROJECT_DIR,
    bool_text,
    detect_command,
    extract_skill_name,
    install_skill_source,
    kv,
    parse_int_list,
    read_declared_tools,
    read_text,
    resolve_cwd_within_skill,
    resolve_skill_path,
    run_command,
    run_command_sequence,
    sanitize_name,
    session_relative,
    snapshot_skill_source,
    write_text,
)
from nexus_testing.sandbox_skill_invoke.telemetry import (
    LIVE_TELEMETRY_PROTOCOL_VERSION,
    LIVE_TELEMETRY_SOURCE,
    inspect_live_runtime_telemetry,
    load_result_payload,
    merge_telemetry_payload,
    write_preferred_output,
)
from nexus_testing.sandbox_skill_invoke.trace import build_trace
from nexus_testing.sandbox_skill_invoke.verifier import load_verifier_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Invoke a skill inside a sandbox session.")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--skill-path", required=True)
    parser.add_argument("--message")
    parser.add_argument("--channel", default="telegram")
    parser.add_argument("--mode", default="auto", choices=("auto", "live", "shim-live", "trace", "dry-run"))
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--strict-real", action="store_true")
    parser.add_argument("--history-file")
    parser.add_argument("--sandbox-root")
    parser.add_argument("--expect-trigger", choices=("true", "false", "unknown"))
    parser.add_argument("--require-tools")
    parser.add_argument("--expect-context-ref", action="append")
    parser.add_argument("--require-delivery-status")
    parser.add_argument("--require-delivery-evidence", action="store_true")
    parser.add_argument("--verification-manifest")
    args = parser.parse_args()

    if args.mode != "dry-run" and not args.message:
        parser.error("--message is required unless --mode dry-run is used")
    if args.strict_real and args.mode in {"trace", "dry-run"}:
        parser.error("--strict-real cannot be combined with trace or dry-run mode")
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.session_id):
        raise SystemExit("ERROR: Invalid session-id format")

    sandbox_root = Path(args.sandbox_root).resolve() if args.sandbox_root else PROJECT_DIR / ".nexus-sandbox"
    session_dir = sandbox_root / args.session_id
    if not session_dir.exists():
        raise SystemExit(f"ERROR: Session does not exist: {session_dir}")

    workspace_dir = session_dir / "workspace"
    logs_dir = session_dir / "logs"
    state_dir = workspace_dir / "state"
    outputs_dir = workspace_dir / "outputs"
    artifacts_root = workspace_dir / "artifacts"
    skills_dir = workspace_dir / "skills"
    for path in (state_dir, outputs_dir, artifacts_root, skills_dir):
        path.mkdir(parents=True, exist_ok=True)

    skill_dir, skill_md = resolve_skill_path(args.skill_path)
    skill_name = extract_skill_name(skill_md)
    skill_name_safe = sanitize_name(skill_name)
    try:
        source_snapshot = snapshot_skill_source(skill_dir)
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}")
    source_fingerprint = source_snapshot.fingerprint
    verifier_manifest = load_verifier_manifest(args.verification_manifest, skill_dir)
    if args.verification_manifest and not verifier_manifest.get("available"):
        raise SystemExit(f"ERROR: {verifier_manifest.get('error', 'invalid verification manifest')}")
    skill_target = skills_dir / f"{skill_name_safe}-{source_fingerprint[:12]}"
    if not (skill_target / "SKILL.md").exists():
        if skill_target.exists():
            shutil.rmtree(skill_target)
        install_skill_source(source_snapshot, skill_target)
        install_status = "installed"
    else:
        install_status = "reused"

    if not (skill_target / "SKILL.md").exists():
        raise SystemExit("ERROR: Skill installation verification failed")

    tools = read_declared_tools(skill_target / "SKILL.md")
    tools_csv = ",".join(tools) if tools else "unknown"
    adapter = detect_adapter(skill_target)
    openclaw = detect_command("openclaw", "claw")

    requested_mode = args.mode
    selected_mode = requested_mode
    if requested_mode == "auto":
        if args.strict_real and adapter.get("available") and verifier_manifest.get("available"):
            selected_mode = "shim-live"
        elif openclaw:
            selected_mode = "live"
        elif adapter.get("available"):
            selected_mode = "shim-live"
        else:
            selected_mode = "trace"

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    trace_file = logs_dir / f"{timestamp}-invoke-trace.json"
    output_file = outputs_dir / f"{timestamp}-response.md"
    channel_render_file = outputs_dir / f"{timestamp}-channel-{args.channel}.md"
    result_json_file = state_dir / f"{timestamp}-invoke-result.json"
    artifacts_dir = artifacts_root / f"{timestamp}-{skill_name_safe}"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    require_tools = [item.strip() for item in (args.require_tools or "").split(",") if item.strip()]
    expect_context_refs = parse_int_list(args.expect_context_ref)
    strict_verifier_required = args.strict_real and selected_mode == "shim-live"

    history_file: Path | None = None
    if args.history_file:
        history_file = Path(args.history_file)
        if not history_file.is_absolute():
            history_file = (workspace_dir / history_file).resolve()
        history_file.parent.mkdir(parents=True, exist_ok=True)
        if not history_file.exists():
            history_file.write_text("[]\n", encoding="utf-8")

    command_repr = " ".join([
        "sandbox-skill-invoke",
        f"--mode {selected_mode}",
        f"--skill-path {args.skill_path}",
        f"--channel {args.channel}",
        f"--message {json.dumps(args.message or '', ensure_ascii=False)}",
        *([f"--verification-manifest {args.verification_manifest}"] if args.verification_manifest else []),
    ])

    def write_channel_render(execution_level: str, real_executed: bool, delivery_status: str = "unknown", delivery_evidence: list[str] | None = None) -> None:
        output_text = read_text(output_file) if output_file.exists() else "(no output captured)"
        evidence_text = ", ".join(delivery_evidence or []) if delivery_evidence else "unknown"
        write_text(channel_render_file, "\n".join([
            f"# Channel Render: {args.channel}", "",
            f"- Requested Mode: {requested_mode}", f"- Selected Mode: {selected_mode}",
            f"- Execution Level: {execution_level}", f"- Real Executed: {bool_text(real_executed)}",
            f"- Delivery Status: {delivery_status}", f"- Delivery Evidence: {evidence_text}",
            "", "## Message", args.message or "", "", "## Output", output_text, "",
        ]))

    def blocked(status: str, reason: str) -> int:
        write_text(output_file, "\n".join(["# Skill Invocation Blocked", "", f"- Requested mode: {requested_mode}", f"- Strict real: {bool_text(args.strict_real)}", f"- Blocker: {reason}", ""]))
        trace_payload = {"requestedMode": requested_mode, "selectedMode": "blocked", "executionLevel": "none", "realExecuted": False, "strictReal": args.strict_real, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()), "skillName": skill_name, "skillPath": str(skill_target), "message": args.message, "channel": args.channel, "status": status, "blockerReason": reason}
        write_text(trace_file, json.dumps(trace_payload, ensure_ascii=False, indent=2) + "\n")
        write_channel_render("none", False)
        seq = append_audit_entry(session_dir, command_text=command_repr, exit_code=2, duration_ms=0, status=status, execution_level="none", real_executed=False, output_file=output_file, extra={"traceFile": session_relative(trace_file, session_dir), "blockerReason": reason})
        kv("REQUESTED_MODE", requested_mode); kv("SELECTED_MODE", "blocked"); kv("EXECUTION_LEVEL", "none")
        kv("REAL_EXECUTED", "false"); kv("STRICT_REAL", bool_text(args.strict_real)); kv("INVOKE_STATUS", status)
        kv("BLOCKER_REASON", reason); kv("TOOL_TRACE_FILE", trace_file); kv("OUTPUT_FILE", output_file)
        kv("CHANNEL_RENDER_FILE", channel_render_file); kv("SEQ", seq)
        return 2

    def adapter_install_steps() -> list[object]:
        commands = adapter.get("install_commands")
        if isinstance(commands, list):
            return [command for command in commands if command]
        legacy_command = adapter.get("install_command")
        if legacy_command:
            return [legacy_command]
        return []

    if args.strict_real and selected_mode == "trace":
        return blocked("blocked-no-real-exec", "Neither OpenClaw live runtime nor shim adapter is available")

    kv("SESSION_ID", args.session_id); kv("SKILL_NAME", skill_name_safe); kv("INSTALL_STATUS", install_status)

    if selected_mode == "dry-run":
        install_steps = adapter_install_steps()
        if adapter.get("available") and install_steps:
            install_stdout_file = logs_dir / f"{timestamp}-install.stdout.log"
            install_stderr_file = logs_dir / f"{timestamp}-install.stderr.log"
            try:
                install_cwd = resolve_cwd_within_skill(skill_target, str(adapter.get("install_cwd", ".")))
                env = os.environ.copy()
                env.update({"NEXUS_SESSION_ID": args.session_id, "NEXUS_MESSAGE": args.message or "", "NEXUS_CHANNEL": args.channel, "NEXUS_SKILL_PATH": str(skill_target), "NEXUS_WORKSPACE_DIR": str(workspace_dir), "NEXUS_OUTPUT_FILE": str(output_file), "NEXUS_RESULT_JSON_FILE": str(result_json_file), "NEXUS_HISTORY_FILE": str(history_file or ""), "NEXUS_ARTIFACTS_DIR": str(artifacts_dir), "NEXUS_STRICT_REAL": bool_text(args.strict_real)})
                install_proc = run_command_sequence(install_steps, install_cwd, max(args.timeout, 120), env)
                write_text(install_stdout_file, install_proc.stdout); write_text(install_stderr_file, install_proc.stderr)
                if install_proc.returncode != 0:
                    return blocked("blocked-install-failed", "dependency installation failed during dry-run")
                install_status = "success"
            except subprocess.TimeoutExpired:
                return blocked("blocked-install-timeout", "dependency installation timed out during dry-run")
            except (RuntimeError, ValueError) as exc:
                return blocked("blocked-install-failed", str(exc))
        assertion_failures = evaluate_assertions(expect_trigger=args.expect_trigger, require_tools=require_tools, expect_context_refs=expect_context_refs, require_delivery_status=args.require_delivery_status, require_delivery_evidence=args.require_delivery_evidence, actual_trigger="unknown", actual_tools=[], actual_context_refs=[], delivery_status="unknown", delivery_receipts=[], delivery_evidence=[], invalid_delivery_evidence=[])
        invoke_status = "dry-run-complete" if not assertion_failures else "assertion-failed"
        payload = {"requestedMode": requested_mode, "selectedMode": "dry-run", "executionLevel": "dry-run", "realExecuted": False, "strictReal": args.strict_real, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()), "skillName": skill_name, "skillPath": str(skill_target), "sourceSkillPath": str(skill_dir), "sourceFingerprint": source_fingerprint, "adapterAvailable": bool(adapter.get("available")), "adapterSource": adapter.get("source", "none"), "triggerMatched": None, "toolsCalled": [], "contextReferences": [], "deliveryStatus": "unknown", "deliveryReceipts": [], "deliveryEvidence": [], "invalidDeliveryEvidence": [], "assertionsPassed": not assertion_failures, "assertionFailures": assertion_failures, "installStatus": install_status, "status": invoke_status}
        write_text(trace_file, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        write_text(output_file, "\n".join(["# Skill Dry Run", "", f"- Requested Mode: {requested_mode}", "- Selected Mode: dry-run", f"- Adapter Available: {bool_text(bool(adapter.get('available')))}", f"- Adapter Source: {adapter.get('source', 'none')}", f"- Install Status: {install_status}", f"- Assertions Passed: {bool_text(not assertion_failures)}", "", "No invocation was performed.", ""]))
        write_channel_render("dry-run", False, delivery_status="unknown")
        seq = append_audit_entry(session_dir, command_text=command_repr, exit_code=0 if not assertion_failures else 3, duration_ms=0, status=invoke_status, execution_level="dry-run", real_executed=False, output_file=output_file, extra={"traceFile": session_relative(trace_file, session_dir), "adapterSource": adapter.get("source", "none")})
        kv("REQUESTED_MODE", requested_mode); kv("SELECTED_MODE", "dry-run"); kv("EXECUTION_LEVEL", "dry-run"); kv("REAL_EXECUTED", "false"); kv("STRICT_REAL", bool_text(args.strict_real)); kv("INVOKE_STATUS", invoke_status); kv("ADAPTER_AVAILABLE", bool_text(bool(adapter.get("available")))); kv("ADAPTER_SOURCE", adapter.get("source", "none")); kv("DELIVERY_STATUS", "unknown"); kv("DELIVERY_EVIDENCE", "unknown"); kv("CONTEXT_REFERENCES", "unknown"); kv("ASSERTIONS_PASSED", bool_text(not assertion_failures)); kv("ASSERTION_FAILURES", " | ".join(assertion_failures) if assertion_failures else ""); kv("TOOL_TRACE_FILE", trace_file); kv("OUTPUT_FILE", output_file); kv("CHANNEL_RENDER_FILE", channel_render_file); kv("SEQ", seq)
        kv("RESULT_JSON_FILE", result_json_file)
        return 0 if not assertion_failures else 3

    if selected_mode == "trace":
        trace_payload = build_trace(skill_target / "SKILL.md", args.message or "", args.channel, tools, args.strict_real, requested_mode, skill_name, skill_target)
        actual_trigger = "true" if trace_payload["triggerMatched"] is True else "unknown"
        actual_tools = list(trace_payload.get("toolsCalled", []))
        assertion_failures = evaluate_assertions(expect_trigger=args.expect_trigger, require_tools=require_tools, expect_context_refs=expect_context_refs, require_delivery_status=args.require_delivery_status, require_delivery_evidence=args.require_delivery_evidence, actual_trigger=actual_trigger, actual_tools=actual_tools, actual_context_refs=[], delivery_status="unknown", delivery_receipts=[], delivery_evidence=[], invalid_delivery_evidence=[])
        invoke_status = "trace-complete" if not assertion_failures else "assertion-failed"
        trace_payload.update({"sourceSkillPath": str(skill_dir), "sourceFingerprint": source_fingerprint, "contextReferences": [], "deliveryStatus": "unknown", "deliveryReceipts": [], "deliveryEvidence": [], "invalidDeliveryEvidence": [], "assertionsPassed": not assertion_failures, "assertionFailures": assertion_failures, "status": invoke_status})
        write_text(trace_file, json.dumps(trace_payload, ensure_ascii=False, indent=2) + "\n")
        write_text(output_file, "\n".join(["# Skill Trace Output", "", f"- Requested Mode: {requested_mode}", "- Selected Mode: trace", "- Execution Level: trace", "- Real Executed: false", f"- Trigger Matched: {trace_payload['triggerMatched']}", f"- Tools Declared: {tools_csv}", f"- Assertions Passed: {bool_text(not assertion_failures)}", "", "This output came from static trace analysis. It is not valid evidence for a real functional pass.", ""]))
        write_channel_render("trace", False, delivery_status="unknown")
        seq = append_audit_entry(session_dir, command_text=command_repr, exit_code=0 if not assertion_failures else 3, duration_ms=0, status=invoke_status, execution_level="trace", real_executed=False, output_file=output_file, extra={"traceFile": session_relative(trace_file, session_dir), "toolsCalled": actual_tools})
        kv("REQUESTED_MODE", requested_mode); kv("SELECTED_MODE", "trace"); kv("EXECUTION_LEVEL", "trace"); kv("REAL_EXECUTED", "false"); kv("STRICT_REAL", bool_text(args.strict_real)); kv("INVOKE_STATUS", invoke_status); kv("TRIGGER_MATCHED", actual_trigger); kv("TOOLS_CALLED", tools_csv); kv("DELIVERY_STATUS", "unknown"); kv("DELIVERY_EVIDENCE", "unknown"); kv("CONTEXT_REFERENCES", "unknown"); kv("ASSERTIONS_PASSED", bool_text(not assertion_failures)); kv("ASSERTION_FAILURES", " | ".join(assertion_failures) if assertion_failures else ""); kv("TOOL_TRACE_FILE", trace_file); kv("OUTPUT_FILE", output_file); kv("CHANNEL_RENDER_FILE", channel_render_file); kv("SEQ", seq)
        kv("RESULT_JSON_FILE", result_json_file)
        return 0 if not assertion_failures else 3

    # ── shim-live mode ──────────────────────────────────────────────────
    if selected_mode == "shim-live":
        if not adapter.get("available"):
            return blocked("blocked-no-adapter", f"shim-live requires a local adapter, but: {adapter.get('error', 'none found')}")

        # strict-real without independent verifier → assertion failure
        if strict_verifier_required and not verifier_manifest.get("available"):
            assertion_failures = ["shim-live --strict-real requires an independent verification manifest"]
            payload = {
                "requestedMode": requested_mode, "selectedMode": "shim-live",
                "executionLevel": "shim-live", "realExecuted": False,
                "strictReal": args.strict_real,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                "skillName": skill_name, "skillPath": str(skill_target),
                "sourceSkillPath": str(skill_dir), "sourceFingerprint": source_fingerprint,
                "adapterAvailable": True, "adapterSource": adapter.get("source", "none"),
                "triggerMatched": None, "toolsCalled": [], "contextReferences": [],
                "deliveryStatus": "unknown", "deliveryReceipts": [], "deliveryEvidence": [],
                "invalidDeliveryEvidence": [],
                "telemetryTrust": "self-reported", "verificationStatus": "not-configured",
                "assertionsPassed": False, "assertionFailures": assertion_failures,
                "status": "assertion-failed",
            }
            write_text(trace_file, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            write_text(output_file, "\n".join([
                "# Skill Invocation — Assertion Failed", "",
                f"- Requested Mode: {requested_mode}", "- Selected Mode: shim-live",
                f"- Strict Real: {bool_text(args.strict_real)}",
                "- Telemetry Trust: self-reported",
                "- Verification Status: not-configured", "",
                "## Assertion Failures", "",
                *[f"- {f}" for f in assertion_failures], "",
            ]))
            write_channel_render("shim-live", False, delivery_status="unknown")
            seq = append_audit_entry(
                session_dir, command_text=command_repr, exit_code=3,
                duration_ms=0, status="assertion-failed",
                execution_level="shim-live", real_executed=False,
                output_file=output_file,
                extra={"traceFile": session_relative(trace_file, session_dir), "adapterSource": adapter.get("source", "none")},
            )
            kv("REQUESTED_MODE", requested_mode); kv("SELECTED_MODE", "shim-live")
            kv("EXECUTION_LEVEL", "shim-live"); kv("REAL_EXECUTED", "false")
            kv("STRICT_REAL", bool_text(args.strict_real))
            kv("INVOKE_STATUS", "assertion-failed")
            kv("TELEMETRY_TRUST", "self-reported")
            kv("VERIFICATION_STATUS", "not-configured")
            kv("ASSERTIONS_PASSED", "false")
            kv("ASSERTION_FAILURES", " | ".join(assertion_failures))
            kv("TOOL_TRACE_FILE", trace_file); kv("OUTPUT_FILE", output_file)
            kv("CHANNEL_RENDER_FILE", channel_render_file); kv("SEQ", seq)
            kv("RESULT_JSON_FILE", result_json_file)
            return 3

        # ── run adapter install ──
        env = os.environ.copy()
        env.update({
            "NEXUS_SESSION_ID": args.session_id,
            "NEXUS_MESSAGE": args.message or "",
            "NEXUS_CHANNEL": args.channel,
            "NEXUS_SKILL_PATH": str(skill_target),
            "NEXUS_WORKSPACE_DIR": str(workspace_dir),
            "NEXUS_OUTPUT_FILE": str(output_file),
            "NEXUS_RESULT_JSON_FILE": str(result_json_file),
            "NEXUS_HISTORY_FILE": str(history_file or ""),
            "NEXUS_ARTIFACTS_DIR": str(artifacts_dir),
            "NEXUS_STRICT_REAL": bool_text(args.strict_real),
        })
        install_steps = adapter_install_steps()
        if install_steps:
            install_stdout_file = logs_dir / f"{timestamp}-install.stdout.log"
            install_stderr_file = logs_dir / f"{timestamp}-install.stderr.log"
            try:
                install_cwd = resolve_cwd_within_skill(skill_target, str(adapter.get("install_cwd", ".")))
                install_proc = run_command_sequence(install_steps, install_cwd, max(args.timeout, 120), env)
                write_text(install_stdout_file, install_proc.stdout)
                write_text(install_stderr_file, install_proc.stderr)
                if install_proc.returncode != 0:
                    return blocked("blocked-install-failed", "dependency installation failed")
            except subprocess.TimeoutExpired:
                return blocked("blocked-install-timeout", "dependency installation timed out")
            except (RuntimeError, ValueError) as exc:
                return blocked("blocked-install-failed", str(exc))

        # ── run adapter invoke ──
        invoke_stdout_file = logs_dir / f"{timestamp}-invoke.stdout.log"
        invoke_stderr_file = logs_dir / f"{timestamp}-invoke.stderr.log"
        adapter_result_file = result_json_file
        adapter_start = time.time()
        try:
            invoke_cwd = resolve_cwd_within_skill(skill_target, str(adapter.get("invoke_cwd", ".")))
            invoke_proc = run_command(adapter["invoke_command"], invoke_cwd, args.timeout, env)
            adapter_duration_ms = int((time.time() - adapter_start) * 1000)
            write_text(invoke_stdout_file, invoke_proc.stdout)
            write_text(invoke_stderr_file, invoke_proc.stderr)
            if invoke_proc.returncode != 0:
                return blocked("blocked-invoke-failed", f"adapter exited with code {invoke_proc.returncode}")
        except subprocess.TimeoutExpired:
            return blocked("blocked-invoke-timeout", "adapter invoke timed out")
        except (RuntimeError, ValueError) as exc:
            return blocked("blocked-invoke-failed", str(exc))

        adapter_payload = load_result_payload(adapter_result_file, invoke_proc.stdout, invoke_proc.stderr)
        adapter_telemetry = inspect_live_runtime_telemetry(adapter_payload)

        # ── run independent verifier (if strict-real) ──
        verifier_payload: dict[str, object] = {}
        verifier_status = "not-configured"
        telemetry_trust = "self-reported"
        if strict_verifier_required and verifier_manifest.get("available"):
            verifier_result_file = state_dir / f"{timestamp}-verifier-result.json"
            verifier_stdout_file = logs_dir / f"{timestamp}-verifier.stdout.log"
            verifier_stderr_file = logs_dir / f"{timestamp}-verifier.stderr.log"
            verifier_env = env.copy()
            verifier_env["NEXUS_ADAPTER_RESULT_JSON_FILE"] = str(adapter_result_file)
            verifier_env["NEXUS_VERIFIER_RESULT_FILE"] = str(verifier_result_file)
            try:
                verifier_start = time.time()
                verifier_cwd = verifier_manifest["cwd"]
                verifier_timeout = verifier_manifest.get("timeout_seconds") or args.timeout
                verifier_proc = run_command(
                    verifier_manifest["command"],
                    verifier_cwd,
                    verifier_timeout,
                    verifier_env,
                )
                verifier_duration_ms = int((time.time() - verifier_start) * 1000)
                write_text(verifier_stdout_file, verifier_proc.stdout)
                write_text(verifier_stderr_file, verifier_proc.stderr)
                if verifier_proc.returncode != 0:
                    verifier_status = "failed"
                else:
                    verifier_payload = load_result_payload(verifier_result_file, verifier_proc.stdout, verifier_proc.stderr)
                    verifier_status = "passed"
                    telemetry_trust = "independent"
            except subprocess.TimeoutExpired:
                verifier_status = "timeout"
            except (RuntimeError, ValueError):
                verifier_status = "error"

        # ── merge payloads & evaluate ──
        merged_payload = merge_telemetry_payload(adapter_payload, verifier_payload)
        actual_trigger = str(merged_payload.get("triggerMatched", ""))
        if isinstance(merged_payload.get("triggerMatched"), bool):
            actual_trigger = "true" if merged_payload["triggerMatched"] else "false"
        actual_tools = [str(t) for t in (merged_payload.get("toolsCalled") or []) if str(t).strip()]
        actual_context_refs = normalize_context_references(merged_payload.get("contextReferences"))
        delivery_status, delivery_receipts, delivery_evidence, invalid_evidence = collect_delivery_metadata(merged_payload, session_dir)
        assertion_failures = evaluate_assertions(
            expect_trigger=args.expect_trigger, require_tools=require_tools,
            expect_context_refs=expect_context_refs,
            require_delivery_status=args.require_delivery_status,
            require_delivery_evidence=args.require_delivery_evidence,
            actual_trigger=actual_trigger, actual_tools=actual_tools,
            actual_context_refs=actual_context_refs,
            delivery_status=delivery_status,
            delivery_receipts=delivery_receipts,
            delivery_evidence=delivery_evidence,
            invalid_delivery_evidence=invalid_evidence,
        )
        invoke_status = "success" if not assertion_failures else "assertion-failed"
        payload = {
            "requestedMode": requested_mode, "selectedMode": "shim-live",
            "executionLevel": "shim-live", "realExecuted": True,
            "strictReal": args.strict_real,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "skillName": skill_name, "skillPath": str(skill_target),
            "sourceSkillPath": str(skill_dir), "sourceFingerprint": source_fingerprint,
            "adapterAvailable": True, "adapterSource": adapter.get("source", "none"),
            "triggerMatched": merged_payload.get("triggerMatched"),
            "toolsCalled": actual_tools, "contextReferences": actual_context_refs,
            "deliveryStatus": delivery_status,
            "deliveryReceipts": delivery_receipts,
            "deliveryEvidence": delivery_evidence,
            "invalidDeliveryEvidence": invalid_evidence,
            "telemetryTrust": telemetry_trust,
            "verificationStatus": verifier_status,
            "adapterTelemetry": adapter_telemetry,
            "assertionsPassed": not assertion_failures,
            "assertionFailures": assertion_failures,
            "status": invoke_status,
        }
        write_text(trace_file, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        write_preferred_output(merged_payload, output_file, invoke_proc.stdout)
        write_channel_render("shim-live", True, delivery_status=delivery_status, delivery_evidence=delivery_evidence)
        total_duration = adapter_duration_ms + (verifier_duration_ms if strict_verifier_required else 0)
        seq = append_audit_entry(
            session_dir, command_text=command_repr,
            exit_code=0 if not assertion_failures else 3,
            duration_ms=total_duration, status=invoke_status,
            execution_level="shim-live", real_executed=True,
            stdout_file=invoke_stdout_file, stderr_file=invoke_stderr_file,
            output_file=output_file,
            extra={"traceFile": session_relative(trace_file, session_dir), "adapterSource": adapter.get("source", "none"), "telemetryTrust": telemetry_trust, "verificationStatus": verifier_status},
        )
        kv("REQUESTED_MODE", requested_mode); kv("SELECTED_MODE", "shim-live")
        kv("EXECUTION_LEVEL", "shim-live"); kv("REAL_EXECUTED", "true")
        kv("STRICT_REAL", bool_text(args.strict_real)); kv("INVOKE_STATUS", invoke_status)
        kv("TRIGGER_MATCHED", actual_trigger); kv("TOOLS_CALLED", ",".join(actual_tools))
        kv("DELIVERY_STATUS", delivery_status)
        kv("DELIVERY_EVIDENCE", ",".join(delivery_evidence) if delivery_evidence else "none")
        kv("INVALID_DELIVERY_EVIDENCE", ",".join(invalid_evidence) if invalid_evidence else "none")
        kv("CONTEXT_REFERENCES", ",".join(str(r) for r in actual_context_refs) if actual_context_refs else "none")
        kv("TELEMETRY_TRUST", telemetry_trust)
        kv("VERIFICATION_STATUS", verifier_status)
        kv("ASSERTIONS_PASSED", bool_text(not assertion_failures))
        kv("ASSERTION_FAILURES", " | ".join(assertion_failures) if assertion_failures else "")
        kv("TOOL_TRACE_FILE", trace_file); kv("OUTPUT_FILE", output_file)
        kv("CHANNEL_RENDER_FILE", channel_render_file); kv("SEQ", seq)
        kv("RESULT_JSON_FILE", adapter_result_file)
        return 0 if not assertion_failures else 3

    # ── live mode ───────────────────────────────────────────────────────
    if selected_mode == "live":
        if not openclaw:
            return blocked("blocked-no-openclaw", "live mode requires OpenClaw CLI (openclaw or claw)")
        live_result_file = state_dir / f"{timestamp}-live-result.json"
        live_stdout_file = logs_dir / f"{timestamp}-live.stdout.log"
        live_stderr_file = logs_dir / f"{timestamp}-live.stderr.log"
        live_env = os.environ.copy()
        live_env.update({
            "NEXUS_SESSION_ID": args.session_id,
            "NEXUS_MESSAGE": args.message or "",
            "NEXUS_CHANNEL": args.channel,
            "NEXUS_SKILL_PATH": str(skill_target),
            "NEXUS_OUTPUT_FILE": str(output_file),
            "NEXUS_RESULT_JSON_FILE": str(live_result_file),
            "NEXUS_ARTIFACTS_DIR": str(artifacts_dir),
            "NEXUS_STRICT_REAL": bool_text(args.strict_real),
            "NEXUS_TELEMETRY_PROTOCOL_VERSION": LIVE_TELEMETRY_PROTOCOL_VERSION,
            "NEXUS_TELEMETRY_SOURCE": LIVE_TELEMETRY_SOURCE,
        })
        live_start = time.time()
        try:
            live_cmd = [
                openclaw,
                "invoke",
                "--skill",
                str(skill_target),
                "--message",
                args.message or "",
                "--channel",
                args.channel,
                "--output",
                str(output_file),
                "--result",
                str(live_result_file),
            ]
            live_proc = run_command(live_cmd, skill_target, args.timeout, live_env)
            live_duration_ms = int((time.time() - live_start) * 1000)
            write_text(live_stdout_file, live_proc.stdout)
            write_text(live_stderr_file, live_proc.stderr)
            if live_proc.returncode != 0:
                return blocked("blocked-live-failed", f"openclaw invoke exited with code {live_proc.returncode}")
        except subprocess.TimeoutExpired:
            return blocked("blocked-live-timeout", "openclaw invoke timed out")
        except (RuntimeError, ValueError) as exc:
            return blocked("blocked-live-failed", str(exc))

        live_payload = load_result_payload(live_result_file, live_proc.stdout, live_proc.stderr)
        live_telemetry = inspect_live_runtime_telemetry(live_payload)
        if args.strict_real and live_telemetry.get("status") != "passed":
            telemetry_issues = live_telemetry.get("issues", [])
            telemetry_block_status = "blocked-live-telemetry-missing" if live_telemetry.get("status") == "missing" else "blocked-live-telemetry-invalid"
            return blocked(telemetry_block_status, f"strict-real requires valid telemetry: {'; '.join(telemetry_issues)}")

        actual_trigger = str(live_payload.get("triggerMatched", ""))
        if isinstance(live_payload.get("triggerMatched"), bool):
            actual_trigger = "true" if live_payload["triggerMatched"] else "false"
        actual_tools = [str(t) for t in (live_payload.get("toolsCalled") or []) if str(t).strip()]
        actual_context_refs = normalize_context_references(live_payload.get("contextReferences"))
        delivery_status, delivery_receipts, delivery_evidence, invalid_evidence = collect_delivery_metadata(live_payload, session_dir)
        assertion_failures = evaluate_assertions(
            expect_trigger=args.expect_trigger, require_tools=require_tools,
            expect_context_refs=expect_context_refs,
            require_delivery_status=args.require_delivery_status,
            require_delivery_evidence=args.require_delivery_evidence,
            actual_trigger=actual_trigger, actual_tools=actual_tools,
            actual_context_refs=actual_context_refs,
            delivery_status=delivery_status,
            delivery_receipts=delivery_receipts,
            delivery_evidence=delivery_evidence,
            invalid_delivery_evidence=invalid_evidence,
        )
        invoke_status = "success" if not assertion_failures else "assertion-failed"
        payload = {
            "requestedMode": requested_mode, "selectedMode": "live",
            "executionLevel": "live", "realExecuted": True,
            "strictReal": args.strict_real,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "skillName": skill_name, "skillPath": str(skill_target),
            "sourceSkillPath": str(skill_dir), "sourceFingerprint": source_fingerprint,
            "triggerMatched": live_payload.get("triggerMatched"),
            "toolsCalled": actual_tools, "contextReferences": actual_context_refs,
            "deliveryStatus": delivery_status,
            "deliveryReceipts": delivery_receipts,
            "deliveryEvidence": delivery_evidence,
            "invalidDeliveryEvidence": invalid_evidence,
            "liveTelemetry": live_telemetry,
            "assertionsPassed": not assertion_failures,
            "assertionFailures": assertion_failures,
            "status": invoke_status,
        }
        write_text(trace_file, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        write_preferred_output(live_payload, output_file, live_proc.stdout)
        write_channel_render("live", True, delivery_status=delivery_status, delivery_evidence=delivery_evidence)
        seq = append_audit_entry(
            session_dir, command_text=command_repr,
            exit_code=0 if not assertion_failures else 3,
            duration_ms=live_duration_ms, status=invoke_status,
            execution_level="live", real_executed=True,
            stdout_file=live_stdout_file, stderr_file=live_stderr_file,
            output_file=output_file,
            extra={"traceFile": session_relative(trace_file, session_dir), "liveTelemetryStatus": live_telemetry.get("status", "unknown")},
        )
        kv("REQUESTED_MODE", requested_mode); kv("SELECTED_MODE", "live")
        kv("EXECUTION_LEVEL", "live"); kv("REAL_EXECUTED", "true")
        kv("STRICT_REAL", bool_text(args.strict_real)); kv("INVOKE_STATUS", invoke_status)
        kv("TRIGGER_MATCHED", actual_trigger); kv("TOOLS_CALLED", ",".join(actual_tools))
        kv("DELIVERY_STATUS", delivery_status)
        kv("DELIVERY_EVIDENCE", ",".join(delivery_evidence) if delivery_evidence else "none")
        kv("INVALID_DELIVERY_EVIDENCE", ",".join(invalid_evidence) if invalid_evidence else "none")
        kv("CONTEXT_REFERENCES", ",".join(str(r) for r in actual_context_refs) if actual_context_refs else "none")
        kv("ASSERTIONS_PASSED", bool_text(not assertion_failures))
        kv("ASSERTION_FAILURES", " | ".join(assertion_failures) if assertion_failures else "")
        kv("TELEMETRY_PROTOCOL_STATUS", live_telemetry.get("status", "unknown"))
        kv("TELEMETRY_PROTOCOL_VERSION", live_telemetry.get("protocol_version", ""))
        kv("TELEMETRY_SOURCE", live_telemetry.get("telemetry_source", ""))
        kv("TOOL_TRACE_FILE", trace_file); kv("OUTPUT_FILE", output_file)
        kv("CHANNEL_RENDER_FILE", channel_render_file); kv("SEQ", seq)
        kv("RESULT_JSON_FILE", live_result_file)
        return 0 if not assertion_failures else 3

    return blocked("blocked-unknown-mode", f"unhandled mode: {selected_mode}")


if __name__ == "__main__":
    raise SystemExit(main())
