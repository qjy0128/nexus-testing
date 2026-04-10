#!/usr/bin/env python3
"""Host runtime bridge that executes DISPATCH bundles with external commands."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dispatch_payload_schema import validate_bundle_manifest, validate_dispatch_payload_list
from json_utils import load_json
from nexus_dispatch_runner import (
    advance,
    complete_role,
    fail_role,
    prepare_bundle,
    role_state_path,
    runner_root,
    stage_run_status,
    start_role,
    takeover_role,
)
from nexus_stage_executor import resolve_path
from runtime_config_schema import validate_runtime_config
from sandbox_skill_invoke.core import read_text, write_text

ROOT = Path(__file__).resolve().parents[1]
FLOW_A_SKILL_VALIDATOR = ROOT / "scripts" / "validate_flow_a_skill_results.py"


def load_runtime_config(path_value: str | None) -> dict[str, object]:
    if not path_value:
        raise SystemExit("ERROR: --runtime-config is required")
    path = resolve_path(path_value)
    if not path.exists():
        raise SystemExit(f"ERROR: runtime config does not exist: {path}")
    payload = load_json(path, label="runtime config")
    if not isinstance(payload, dict):
        raise SystemExit(f"ERROR: runtime config must be a JSON object: {path}")
    try:
        return validate_runtime_config(payload)
    except ValueError as exc:
        raise SystemExit(f"ERROR: invalid runtime config: {exc}") from exc


class SafeDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        raise SystemExit(f"ERROR: missing runtime template variable: {key}")


def render_value(value: str, context: dict[str, str]) -> str:
    return value.format_map(SafeDict(context))


def render_list(values: list[object], context: dict[str, str]) -> list[str]:
    rendered: list[str] = []
    for item in values:
        rendered.append(render_value(str(item), context))
    return rendered


def role_bundle_info(bundle: dict[str, object], role_id: str) -> dict[str, object]:
    manifest_file = Path(str(bundle["manifestFile"]))
    try:
        bundle_manifest = validate_bundle_manifest(load_json(manifest_file, {}, label="bundle manifest"))
    except ValueError as exc:
        raise SystemExit(f"ERROR: invalid bundle manifest: {exc}") from exc
    for item in bundle_manifest.get("roles", []):
        if isinstance(item, dict) and str(item.get("roleId")) == role_id:
            return item
    raise SystemExit(f"ERROR: role {role_id} not found in bundle manifest")


def payload_context(report_dir: Path, bundle: dict[str, object], payload: dict[str, object]) -> dict[str, str]:
    role_info = role_bundle_info(bundle, str(payload["roleId"]))
    bundle_dir = Path(str(bundle["bundleDir"]))
    run_dir = runner_root(report_dir, str(payload["stageId"]))
    payload_file = bundle_dir / str(role_info["payloadFile"])
    prompt_file = bundle_dir / str(role_info["promptFile"])
    if not payload_file.is_file():
        raise SystemExit(f"ERROR: dispatch payload file is missing: {payload_file}")
    if not prompt_file.is_file():
        raise SystemExit(f"ERROR: dispatch prompt file is missing: {prompt_file}")
    return {
        "workspace_root": str(ROOT),
        "report_dir": str(report_dir),
        "bundle_dir": str(bundle_dir),
        "run_dir": str(run_dir),
        "manifest_file": str(bundle["manifestFile"]),
        "payload_file": str(payload_file),
        "prompt_file": str(prompt_file),
        "stage_id": str(payload["stageId"]),
        "stage_name": str(payload["stageName"]),
        "stage_label": str(payload["stageLabel"]),
        "role_id": str(payload["roleId"]),
        "role_type": str(payload["roleType"]),
        "role_file": str(payload["roleFile"]),
    }


def runtime_spec(config: dict[str, object], role_id: str) -> dict[str, object]:
    roles = config.get("roles", {})
    if isinstance(roles, dict):
        selected = roles.get(role_id)
        if isinstance(selected, dict):
            return selected
    default = config.get("default")
    if isinstance(default, dict):
        return default
    raise SystemExit(f"ERROR: runtime config missing default command for role {role_id}")


def parse_role_stdout(stdout: str) -> dict[str, object]:
    text = stdout.strip()
    if not text:
        return {
            "resultFile": None,
            "note": None,
            "status": None,
            "needsMainAgentTakeover": False,
            "blockers": [],
            "rawText": "",
        }
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {
            "resultFile": None,
            "note": text,
            "status": None,
            "needsMainAgentTakeover": False,
            "blockers": [],
            "rawText": text,
        }
    if not isinstance(parsed, dict):
        return {
            "resultFile": None,
            "note": text,
            "status": None,
            "needsMainAgentTakeover": False,
            "blockers": [],
            "rawText": text,
        }
    result_file = parsed.get("resultFile")
    blockers = parsed.get("blockers", [])
    return {
        "resultFile": str(result_file) if result_file else None,
        "note": str(parsed.get("note")) if parsed.get("note") else None,
        "status": str(parsed.get("status")) if parsed.get("status") else None,
        "needsMainAgentTakeover": bool(parsed.get("needsMainAgentTakeover", False)),
        "blockers": [str(item) for item in blockers] if isinstance(blockers, list) else [],
        "rawText": text,
    }


def log_file_prefix(report_dir: Path, stage_id: str, role_id: str) -> Path:
    return runner_root(report_dir, stage_id) / role_id


def save_process_logs(
    report_dir: Path,
    stage_id: str,
    role_id: str,
    stdout: str,
    stderr: str,
    label: str = "runtime",
) -> tuple[str, str]:
    prefix = runner_root(report_dir, stage_id) / f"{role_id}.{label}"
    stdout_path = prefix.with_suffix(".stdout.log")
    stderr_path = prefix.with_suffix(".stderr.log")
    write_text(stdout_path, stdout)
    write_text(stderr_path, stderr)
    return str(stdout_path), str(stderr_path)


def render_env_map(env_value: object, context: dict[str, str]) -> dict[str, str] | None:
    if not isinstance(env_value, dict):
        return None
    env = dict(os.environ)
    env.update({key: render_value(str(value), context) for key, value in env_value.items()})
    return env


def resolved_runtime_spec(
    runtime_name: str,
    raw_spec: dict[str, object],
    context: dict[str, str],
    fallback_to_root: str,
) -> dict[str, object]:
    command_value = raw_spec.get("command")
    if not isinstance(command_value, list) or not command_value:
        raise SystemExit(f"ERROR: runtime config for {runtime_name} must provide a non-empty command list")
    cwd_value = raw_spec.get("cwd")
    timeout_value = raw_spec.get("timeoutSeconds", 900)
    return {
        "name": str(raw_spec.get("name") or runtime_name),
        "command": render_list(command_value, context),
        "cwd": render_value(str(cwd_value), context) if cwd_value else fallback_to_root,
        "env": render_env_map(raw_spec.get("env"), context),
        "timeoutSeconds": int(timeout_value),
    }


def invoke_runtime_command(
    report_dir: Path,
    stage_id: str,
    role_id: str,
    spec: dict[str, object],
    *,
    label: str,
) -> dict[str, object]:
    command = list(spec["command"])
    cwd = str(spec["cwd"])
    env = spec.get("env")
    timeout_seconds = int(spec["timeoutSeconds"])
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            env=env if isinstance(env, dict) else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        stdout_path, stderr_path = save_process_logs(
            report_dir,
            stage_id,
            role_id,
            "",
            f"timeout after {timeout_seconds} seconds\n",
            label,
        )
        return {
            "ok": False,
            "returnCode": None,
            "stdout": "",
            "stderr": "",
            "stdoutPath": stdout_path,
            "stderrPath": stderr_path,
            "note": f"timeout after {timeout_seconds} seconds; logs={stdout_path},{stderr_path}",
            "runtimeName": spec["name"],
            "command": command,
        }
    except Exception as exc:
        stdout_path, stderr_path = save_process_logs(
            report_dir,
            stage_id,
            role_id,
            "",
            f"{type(exc).__name__}: {exc}\n",
            label,
        )
        return {
            "ok": False,
            "returnCode": None,
            "stdout": "",
            "stderr": "",
            "stdoutPath": stdout_path,
            "stderrPath": stderr_path,
            "note": f"runtime exception {type(exc).__name__}: {exc}; logs={stdout_path},{stderr_path}",
            "runtimeName": spec["name"],
            "command": command,
        }

    stdout_path, stderr_path = save_process_logs(report_dir, stage_id, role_id, proc.stdout, proc.stderr, label)
    if proc.returncode != 0:
        return {
            "ok": False,
            "returnCode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "stdoutPath": stdout_path,
            "stderrPath": stderr_path,
            "note": f"exit={proc.returncode}; logs={stdout_path},{stderr_path}",
            "runtimeName": spec["name"],
            "command": command,
        }
    return {
        "ok": True,
        "returnCode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "stdoutPath": stdout_path,
        "stderrPath": stderr_path,
        "note": f"logs={stdout_path},{stderr_path}",
        "runtimeName": spec["name"],
        "command": command,
    }


def merge_takeover_policy(base: dict[str, object], overrides: object) -> dict[str, object]:
    result = {
        "enabled": bool(base.get("enabled", False)),
        "statuses": [str(item).lower() for item in base.get("statuses", []) if str(item).strip()],
        "patterns": [str(item).lower() for item in base.get("patterns", []) if str(item).strip()],
        "onProcessFailure": bool(base.get("onProcessFailure", False)),
    }
    if not isinstance(overrides, dict):
        return result
    if "enabled" in overrides:
        result["enabled"] = bool(overrides.get("enabled"))
    if isinstance(overrides.get("statuses"), list):
        result["statuses"] = [str(item).lower() for item in overrides.get("statuses", []) if str(item).strip()]
    if isinstance(overrides.get("patterns"), list):
        result["patterns"] = [str(item).lower() for item in overrides.get("patterns", []) if str(item).strip()]
    if "onProcessFailure" in overrides:
        result["onProcessFailure"] = bool(overrides.get("onProcessFailure"))
    return result


def resolved_takeover_policy(payload: dict[str, object], config: dict[str, object], spec: dict[str, object]) -> dict[str, object]:
    policy = merge_takeover_policy(payload.get("mainAgentTakeoverPolicy", {}), config.get("mainAgentTakeoverPolicy"))
    policy = merge_takeover_policy(policy, spec.get("mainAgentTakeoverPolicy"))
    if isinstance(config.get("mainAgentTakeoverPatterns"), list):
        policy["patterns"] = list(policy.get("patterns", [])) + [
            str(item).lower() for item in config.get("mainAgentTakeoverPatterns", []) if str(item).strip()
        ]
    if isinstance(spec.get("mainAgentTakeoverPatterns"), list):
        policy["patterns"] = list(policy.get("patterns", [])) + [
            str(item).lower() for item in spec.get("mainAgentTakeoverPatterns", []) if str(item).strip()
        ]
    policy["patterns"] = list(dict.fromkeys(str(item) for item in policy.get("patterns", [])))
    policy["statuses"] = list(dict.fromkeys(str(item) for item in policy.get("statuses", [])))
    return policy


def should_request_takeover(
    payload: dict[str, object],
    config: dict[str, object],
    spec: dict[str, object],
    parsed_stdout: dict[str, object],
    attempt: dict[str, object],
) -> bool:
    if bool(parsed_stdout.get("needsMainAgentTakeover")):
        return True
    if bool(spec.get("mainAgentTakeover")) or bool(config.get("mainAgentTakeover")):
        return True
    policy = resolved_takeover_policy(payload, config, spec)
    if not bool(policy.get("enabled", False)):
        return False
    parsed_status = str(parsed_stdout.get("status") or "").lower()
    statuses = {str(item).lower() for item in policy.get("statuses", []) if str(item).strip()}
    patterns = tuple(str(item).lower() for item in policy.get("patterns", []) if str(item).strip())
    if not attempt.get("ok") and not bool(policy.get("onProcessFailure", False)):
        return False
    if statuses and parsed_status not in statuses:
        return False
    haystack = "\n".join(
        str(item or "")
        for item in (
            parsed_stdout.get("note"),
            parsed_stdout.get("status"),
            " ".join(str(item) for item in parsed_stdout.get("blockers", [])),
            attempt.get("note"),
            attempt.get("stdout"),
            attempt.get("stderr"),
        )
    ).lower()
    return any(pattern in haystack for pattern in patterns)


def write_takeover_file(
    report_dir: Path,
    bundle: dict[str, object],
    payload: dict[str, object],
    context: dict[str, str],
    parsed_stdout: dict[str, object],
    attempts: list[dict[str, object]],
    reason: str,
) -> Path:
    stage_id = str(payload["stageId"])
    role_id = str(payload["roleId"])
    takeover_path = runner_root(report_dir, stage_id) / f"{role_id}.takeover.json"
    attempt_rows = []
    for attempt in attempts:
        attempt_rows.append(
            {
                "runtimeName": attempt.get("runtimeName"),
                "command": attempt.get("command"),
                "returnCode": attempt.get("returnCode"),
                "stdoutLog": attempt.get("stdoutPath"),
                "stderrLog": attempt.get("stderrPath"),
                "note": attempt.get("note"),
            }
        )
    payload_data = {
        "status": "takeover-required",
        "stageId": stage_id,
        "stageLabel": payload.get("stageLabel"),
        "stageName": payload.get("stageName"),
        "roleId": role_id,
        "roleFile": payload.get("roleFile"),
        "reportDir": str(report_dir),
        "missingDeliverables": payload.get("missingDeliverables", []),
        "reason": reason,
        "parsedStdout": {
            "status": parsed_stdout.get("status"),
            "note": parsed_stdout.get("note"),
            "blockers": parsed_stdout.get("blockers", []),
        },
        "attempts": attempt_rows,
        "promptFile": context.get("prompt_file"),
        "payloadFile": context.get("payload_file"),
        "bundleManifest": context.get("manifest_file"),
        "instruction": "Main agent should take over this role in the current host session and continue writing the missing deliverables in the report directory.",
    }
    write_text(takeover_path, json.dumps(payload_data, ensure_ascii=False, indent=2) + "\n")
    return takeover_path


def normalize_heading_marker(text: str) -> str:
    normalized = str(text).strip()
    normalized = re.sub(r"^[#\s]+", "", normalized)
    normalized = re.sub(r"[（(].*?[）)]", "", normalized)
    normalized = re.sub(r"^[0-9一二三四五六七八九十百千]+[、.．\s]*", "", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def markdown_paths_to_validate(report_dir: Path, payload: dict[str, object]) -> list[Path]:
    paths: list[Path] = []
    for item in payload.get("missingDeliverables", []):
        relative = str(item).strip()
        if not relative.endswith(".md"):
            continue
        path = report_dir / relative
        if path.exists():
            paths.append(path)
    return paths


def validate_markdown_structure(report_dir: Path, payload: dict[str, object]) -> str | None:
    if not bool(payload.get("validateMarkdownStructure", False)):
        return None
    required_headings = [str(item).strip() for item in payload.get("minimumOutput", []) if str(item).strip()]
    if not required_headings:
        return None
    aliases = payload.get("minimumOutputAliases", {})
    if not isinstance(aliases, dict):
        aliases = {}
    for path in markdown_paths_to_validate(report_dir, payload):
        content = read_text(path)
        actual_markers = [normalize_heading_marker(match.group(1)) for match in re.finditer(r"^#{2,6}\s+(.+?)\s*$", content, re.MULTILINE)]
        missing: list[str] = []
        for heading in required_headings:
            marker = normalize_heading_marker(aliases.get(heading, heading))
            if marker and not any(marker in actual for actual in actual_markers):
                missing.append(heading)
        if missing:
            return f"{path.name} is missing required sections: {', '.join(missing)}"
    return None


def blocking_note(parsed_stdout: dict[str, object], fallback_note: str) -> str:
    parts: list[str] = []
    status = str(parsed_stdout.get("status") or "").strip()
    note = str(parsed_stdout.get("note") or "").strip()
    blockers = [str(item).strip() for item in parsed_stdout.get("blockers", []) if str(item).strip()]
    if status:
        parts.append(f"runtime-status={status}")
    if note:
        parts.append(note)
    if blockers:
        parts.append("blockers=" + "; ".join(blockers))
    if not parts:
        parts.append(fallback_note)
    return "; ".join(parts)


def validate_role_outputs(report_dir: Path, payload: dict[str, object]) -> str | None:
    role_id = str(payload["roleId"])
    structure_error = validate_markdown_structure(report_dir, payload)
    if structure_error:
        return structure_error
    if role_id != "skill-tester":
        return None
    surface_plan = report_dir / "SURFACE-EXECUTION-PLAN.json"
    skill_results = report_dir / "TEST-EXECUTION" / "skill-results.md"
    surface_coverage = report_dir / "TEST-EXECUTION" / "SURFACE-COVERAGE.json"
    command = [
        sys.executable,
        str(FLOW_A_SKILL_VALIDATOR),
        "--surface-plan",
        str(surface_plan),
        "--skill-results",
        str(skill_results),
        "--surface-coverage",
        str(surface_coverage),
    ]
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stage_id = str(payload["stageId"])
    role_id = str(payload["roleId"])
    stdout_path, stderr_path = save_process_logs(report_dir, stage_id, role_id, proc.stdout, proc.stderr, "validator")
    if proc.returncode == 0:
        return None
    summary = proc.stdout.strip().splitlines()[:3]
    summary_text = " | ".join(summary) if summary else "validator returned non-zero"
    return f"post-run validator failed: {summary_text}; logs={stdout_path},{stderr_path}"


def execute_role(report_dir: Path, bundle: dict[str, object], payload: dict[str, object], config: dict[str, object]) -> dict[str, object]:
    role_id = str(payload["roleId"])
    stage_id = str(payload["stageId"])
    context = payload_context(report_dir, bundle, payload)
    raw_spec = runtime_spec(config, role_id)
    primary_spec = resolved_runtime_spec(
        str(raw_spec.get("name") or config.get("name") or "external-runtime"),
        raw_spec,
        context,
        str(ROOT),
    )
    fallback_spec: dict[str, object] | None = None
    raw_fallback = raw_spec.get("fallback")
    if isinstance(raw_fallback, dict):
        fallback_spec = resolved_runtime_spec(
            str(raw_fallback.get("name") or f"{primary_spec['name']}-fallback"),
            raw_fallback,
            context,
            str(primary_spec["cwd"]),
        )

    start_role(report_dir, stage_id, role_id, str(primary_spec["name"]))
    attempts: list[dict[str, object]] = []

    primary_attempt = invoke_runtime_command(report_dir, stage_id, role_id, primary_spec, label="runtime")
    attempts.append(primary_attempt)
    final_attempt = primary_attempt

    if not primary_attempt["ok"] and fallback_spec is not None:
        fallback_attempt = invoke_runtime_command(report_dir, stage_id, role_id, fallback_spec, label="fallback")
        attempts.append(fallback_attempt)
        final_attempt = fallback_attempt

    parsed_stdout = parse_role_stdout(str(final_attempt.get("stdout", "")))
    takeover_note = str(parsed_stdout.get("note") or final_attempt.get("note") or "")
    if should_request_takeover(payload, config, raw_spec, parsed_stdout, final_attempt):
        takeover_file = write_takeover_file(
            report_dir,
            bundle,
            payload,
            context,
            parsed_stdout,
            attempts,
            takeover_note or "runtime requested main-agent takeover",
        )
        takeover_state = takeover_role(
            report_dir,
            stage_id,
            role_id,
            takeover_note or "runtime requested main-agent takeover",
            str(takeover_file),
        )
        return {
            "roleId": role_id,
            "status": "takeover-required",
            "detail": takeover_state,
            "takeoverFile": str(takeover_file),
        }

    if not final_attempt["ok"]:
        failed = fail_role(report_dir, stage_id, role_id, str(final_attempt["note"]))
        return {"roleId": role_id, "status": "failed", "detail": failed}

    parsed_status = str(parsed_stdout.get("status") or "").lower()
    if parsed_status in {"blocked", "failed"}:
        failed = fail_role(
            report_dir,
            stage_id,
            role_id,
            blocking_note(parsed_stdout, str(final_attempt.get("note") or "runtime returned blocked status")),
        )
        return {"roleId": role_id, "status": "failed", "detail": failed}

    result_file = parsed_stdout.get("resultFile")
    if result_file:
        result_path = Path(str(result_file))
        if not result_path.is_absolute():
            result_file = str((report_dir / result_path).resolve())
    validation_error = validate_role_outputs(report_dir, payload)
    if validation_error:
        failed = fail_role(report_dir, stage_id, role_id, validation_error)
        return {"roleId": role_id, "status": "failed", "detail": failed}

    success_note = str(parsed_stdout.get("note") or final_attempt.get("note") or "")
    completed = complete_role(
        report_dir,
        stage_id,
        role_id,
        str(result_file) if result_file else None,
        success_note,
    )
    return {"roleId": role_id, "status": "completed", "detail": completed}


def actionable_payloads(bundle: dict[str, object]) -> list[dict[str, object]]:
    try:
        return validate_dispatch_payload_list(bundle.get("dispatchPayloads", []))
    except ValueError as exc:
        raise SystemExit(f"ERROR: invalid dispatch payloads: {exc}") from exc


def run_stage_once(report_dir: Path, config: dict[str, object]) -> dict[str, object]:
    bundle = prepare_bundle(report_dir)
    status = str(bundle.get("status"))
    if status not in {"run-stage", "run-post-stage"}:
        return bundle

    payloads = actionable_payloads(bundle)
    dispatch_mode = str(bundle.get("dispatchMode", "serial"))
    results: list[dict[str, object]] = []

    if dispatch_mode == "parallel" and len(payloads) > 1:
        with ThreadPoolExecutor(max_workers=len(payloads)) as executor:
            futures = [executor.submit(execute_role, report_dir, bundle, payload, config) for payload in payloads]
            for future in futures:
                results.append(future.result())
    else:
        for payload in payloads:
            results.append(execute_role(report_dir, bundle, payload, config))

    run_status = stage_run_status(report_dir, str(bundle["stageId"]))
    takeover_results = [item for item in results if item.get("status") == "takeover-required"]
    if takeover_results:
        return {
            "status": "takeover-required",
            "stageId": bundle["stageId"],
            "roleResults": results,
            "runStatus": run_status,
            "takeovers": takeover_results,
        }
    failed_results = [item for item in results if item.get("status") == "failed"]
    if failed_results:
        return {
            "status": "role-failed",
            "stageId": bundle["stageId"],
            "roleResults": results,
            "runStatus": run_status,
        }

    return {
        "status": "stage-run-finished",
        "stageId": bundle["stageId"],
        "roleResults": results,
        "advanceResult": advance(report_dir),
    }


def run_until_gate(report_dir: Path, config: dict[str, object], max_cycles: int) -> dict[str, object]:
    cycles: list[dict[str, object]] = []
    for _ in range(max_cycles):
        step = run_stage_once(report_dir, config)
        cycles.append(step)
        status = str(step.get("status"))
        if status in {"await-approval", "no-go", "complete", "role-failed", "takeover-required"}:
            return {"status": status, "cycles": cycles, "final": step, "gateAction": step}
        if status != "stage-run-finished":
            return {"status": status, "cycles": cycles, "final": step}
        advance_result = step.get("advanceResult", {})
        if not isinstance(advance_result, dict):
            return {"status": "invalid-advance-result", "cycles": cycles, "final": step}
        next_action = advance_result.get("nextAction", {})
        if not isinstance(next_action, dict):
            return {"status": "invalid-next-action", "cycles": cycles, "final": step}
        next_status = str(next_action.get("status"))
        if next_status in {"await-approval", "no-go", "complete"}:
            return {"status": next_status, "cycles": cycles, "final": step, "gateAction": next_action}
    return {"status": "max-cycles-exceeded", "cycles": cycles}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run_once_parser = sub.add_parser("run-once", help="Execute the current actionable stage via external runtime commands")
    run_once_parser.add_argument("--report-dir", required=True)
    run_once_parser.add_argument("--runtime-config", required=True)

    run_until_parser = sub.add_parser("run-until-gate", help="Keep executing stages until approval/no-go/complete/failure")
    run_until_parser.add_argument("--report-dir", required=True)
    run_until_parser.add_argument("--runtime-config", required=True)
    run_until_parser.add_argument("--max-cycles", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    report_dir = resolve_path(args.report_dir)
    config = load_runtime_config(args.runtime_config)

    if args.command == "run-once":
        result = run_stage_once(report_dir, config)
    elif args.command == "run-until-gate":
        result = run_until_gate(report_dir, config, args.max_cycles)
    else:
        raise SystemExit(f"ERROR: unsupported command {args.command}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
