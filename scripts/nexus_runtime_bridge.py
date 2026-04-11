#!/usr/bin/env python3
"""Host runtime bridge that executes DISPATCH bundles with external commands."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from nexus_dispatch_runner import (
    advance,
    complete_role,
    fail_role,
    prepare_bundle,
    runner_root,
    stage_run_status,
    start_role,
    takeover_role,
)
from nexus_stage_executor import append_stage_log, now_text, read_executor_state, resolve_path

from nexus_testing.delivery.models import DeliveryRequest
from nexus_testing.delivery.relay import mirror_report
from nexus_testing.delivery.sender import relay_only_receipt, run_command_sender
from nexus_testing.delivery.store import delivery_record_path
from nexus_testing.delivery.store import read_json as read_delivery_record
from nexus_testing.delivery.store import write_json as write_delivery_record
from nexus_testing.dispatch_payload_schema import (
    validate_bundle_manifest,
    validate_dispatch_payload_list,
)
from nexus_testing.json_utils import load_json
from nexus_testing.runtime.policy import EXECUTION_PROFILES, resolve_execution_policy
from nexus_testing.runtime_config_schema import validate_runtime_config
from nexus_testing.sandbox_skill_invoke.core import read_text, write_text

ROOT = Path(__file__).resolve().parents[1]
FLOW_A_SKILL_VALIDATOR = ROOT / "scripts" / "validate_flow_a_skill_results.py"
FLOW_A_TAKEOVER_EXECUTOR = ROOT / "scripts" / "run_flow_a_takeover_execution.py"
FINAL_REPORT_FILE = "FINAL-TEST-REPORT.md"


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


def orchestration_settings(
    report_dir: Path,
    *,
    execution_profile_override: str | None = None,
    strict_real_override: bool = False,
    delivery_backend_override: str | None = None,
    delivery_channel_override: str | None = None,
    delivery_caption_override: str | None = None,
    delivery_command_override: list[str] | None = None,
    delivery_timeout_override: int | None = None,
    auto_delivery_override: bool | None = None,
) -> dict[str, object]:
    plan, _, _, _ = read_executor_state(report_dir)
    base_profile = str(plan.get("executionProfile", "internal-fast"))
    base_strict_real = bool(plan.get("strictReal", False))
    policy = resolve_execution_policy(execution_profile_override or base_profile, strict_real_override or base_strict_real)
    base_delivery = plan.get("delivery", {})
    if not isinstance(base_delivery, dict):
        base_delivery = {}
    delivery_command = delivery_command_override
    if delivery_command is None:
        raw_command = base_delivery.get("command", [])
        delivery_command = [str(item).strip() for item in raw_command if str(item).strip()] if isinstance(raw_command, list) else []
    backend = str(delivery_backend_override or base_delivery.get("backend") or policy.default_sender_backend).strip().lower()
    if backend not in {"relay-only", "command"}:
        backend = policy.default_sender_backend
    if backend == "command" and not delivery_command:
        backend = "relay-only"
    timeout_seconds = delivery_timeout_override if delivery_timeout_override is not None else int(base_delivery.get("timeoutSeconds", 60) or 60)
    delivery = {
        "enabled": bool(base_delivery.get("enabled", True)),
        "autoSendOnComplete": bool(base_delivery.get("autoSendOnComplete", True)) if auto_delivery_override is None else bool(auto_delivery_override),
        "channel": str(delivery_channel_override or base_delivery.get("channel") or "telegram").strip() or "telegram",
        "caption": str(delivery_caption_override if delivery_caption_override is not None else base_delivery.get("caption", "")),
        "backend": backend,
        "command": delivery_command,
        "timeoutSeconds": max(1, int(timeout_seconds)),
    }
    return {
        "executionProfile": policy.name,
        "strictReal": policy.strict_real,
        "executionPolicy": policy.to_dict(),
        "delivery": delivery,
    }


def payload_context(
    report_dir: Path,
    bundle: dict[str, object],
    payload: dict[str, object],
    execution_settings: dict[str, object] | None = None,
) -> dict[str, str]:
    role_info = role_bundle_info(bundle, str(payload["roleId"]))
    bundle_dir = Path(str(bundle["bundleDir"]))
    run_dir = runner_root(report_dir, str(payload["stageId"]))
    payload_file = bundle_dir / str(role_info["payloadFile"])
    prompt_file = bundle_dir / str(role_info["promptFile"])
    if not payload_file.is_file():
        raise SystemExit(f"ERROR: dispatch payload file is missing: {payload_file}")
    if not prompt_file.is_file():
        raise SystemExit(f"ERROR: dispatch prompt file is missing: {prompt_file}")
    context = {
        "workspace_root": str(ROOT),
        "python_executable": sys.executable,
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
    if isinstance(execution_settings, dict):
        context["execution_profile"] = str(execution_settings.get("executionProfile", "internal-fast"))
        context["strict_real"] = "true" if bool(execution_settings.get("strictReal", False)) else "false"
        execution_policy = execution_settings.get("executionPolicy", {})
        if isinstance(execution_policy, dict):
            context["default_sender_backend"] = str(execution_policy.get("default_sender_backend", "relay-only"))
    return context


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


def attempt_flow_a_host_takeover(
    report_dir: Path,
    payload: dict[str, object],
    takeover_file: Path | None = None,
) -> dict[str, object] | None:
    if str(payload.get("roleId", "")) != "skill-tester":
        return None
    surface_plan = report_dir / "SURFACE-EXECUTION-PLAN.json"
    case_plan = report_dir / "CASE-EXECUTION-PLAN.json"
    if not FLOW_A_TAKEOVER_EXECUTOR.exists() or not surface_plan.exists() or not case_plan.exists():
        return None
    command = [sys.executable, str(FLOW_A_TAKEOVER_EXECUTOR), "--report-dir", str(report_dir)]
    if takeover_file is not None:
        command.extend(["--takeover-file", str(takeover_file)])
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if proc.returncode != 0:
        return {
            "status": "failed",
            "note": f"flow-a host takeover failed: {proc.stderr.strip() or proc.stdout.strip() or f'exit={proc.returncode}'}",
        }
    try:
        payload_data = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        return {"status": "failed", "note": f"flow-a host takeover returned invalid JSON: {exc}"}
    if not isinstance(payload_data, dict):
        return {"status": "failed", "note": "flow-a host takeover returned non-object JSON"}
    return payload_data


def execute_role(
    report_dir: Path,
    bundle: dict[str, object],
    payload: dict[str, object],
    config: dict[str, object],
    settings: dict[str, object],
) -> dict[str, object]:
    role_id = str(payload["roleId"])
    stage_id = str(payload["stageId"])
    context = payload_context(report_dir, bundle, payload, settings)
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
        host_takeover = attempt_flow_a_host_takeover(report_dir, payload)
        if isinstance(host_takeover, dict) and str(host_takeover.get("status")) == "completed":
            validation_error = validate_role_outputs(report_dir, payload)
            if validation_error:
                failed = fail_role(report_dir, stage_id, role_id, validation_error)
                return {"roleId": role_id, "status": "failed", "detail": failed}
            completed = complete_role(
                report_dir,
                stage_id,
                role_id,
                str(host_takeover.get("resultFile") or report_dir / "TEST-EXECUTION" / "skill-results.md"),
                str(host_takeover.get("note") or "flow-a host takeover completed"),
            )
            return {"roleId": role_id, "status": "completed", "detail": completed}
        if isinstance(host_takeover, dict):
            note = str(host_takeover.get("note") or "").strip()
            if note:
                takeover_note = f"{takeover_note}; {note}".strip("; ")
            remaining_file = str(host_takeover.get("remainingCasesMarkdown") or host_takeover.get("remainingCasesFile") or "").strip()
            if remaining_file:
                takeover_note = f"{takeover_note}; remaining-cases={remaining_file}".strip("; ")
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


def final_report_path(report_dir: Path) -> Path | None:
    candidate = report_dir / FINAL_REPORT_FILE
    return candidate if candidate.is_file() else None


def auto_deliver_final_report(report_dir: Path, settings: dict[str, object]) -> dict[str, object] | None:
    delivery = settings.get("delivery", {})
    if not isinstance(delivery, dict) or not bool(delivery.get("enabled", True)):
        return None
    if not bool(delivery.get("autoSendOnComplete", True)):
        return None
    report_file = final_report_path(report_dir)
    if report_file is None:
        return {"status": "skipped", "reason": "missing-final-report"}
    existing = read_delivery_record(delivery_record_path(report_file))
    if existing.get("receipt"):
        return {
            "status": "already-recorded",
            "reportFile": str(report_file),
            "recordFile": str(delivery_record_path(report_file)),
            "delivery": existing,
        }
    relay_abs, relay_path = mirror_report(ROOT, report_dir, report_file)
    request = DeliveryRequest(
        report_file=report_file.relative_to(report_dir).as_posix(),
        source_path=str(report_file),
        relay_path=relay_path,
        relay_abs_path=str(relay_abs),
        channel=str(delivery.get("channel", "telegram")),
        caption=str(delivery.get("caption", "")),
        metadata={
            "reportDir": str(report_dir),
            "executionProfile": settings.get("executionProfile", "internal-fast"),
            "strictReal": bool(settings.get("strictReal", False)),
        },
    )
    backend = str(delivery.get("backend", "relay-only"))
    command = [str(item).strip() for item in delivery.get("command", []) if str(item).strip()] if isinstance(delivery.get("command"), list) else []
    if backend == "command" and command:
        receipt = run_command_sender(
            request,
            command,
            cwd=ROOT,
            timeout_seconds=int(delivery.get("timeoutSeconds", 60)),
        )
    else:
        backend = "relay-only"
        receipt = relay_only_receipt()
    payload = {
        "request": request.to_dict(),
        "receipt": receipt.to_dict(),
        "userConfirmationRequired": True,
    }
    record_path = delivery_record_path(report_file)
    write_delivery_record(record_path, payload)
    append_stage_log(
        report_dir,
        {
            "from_stage": "delivery",
            "to_stage": "delivery",
            "timestamp": now_text(),
            "deliverable_file": FINAL_REPORT_FILE,
            "approval_required": False,
            "gate_check_passed": receipt.status not in {"failed"},
            "event": "report-delivery-recorded",
            "backend": backend,
            "delivery_status": receipt.status,
            "delivery_record": str(record_path),
        },
    )
    return {
        "status": receipt.status,
        "backend": backend,
        "reportFile": str(report_file),
        "recordFile": str(record_path),
        "receipt": receipt.to_dict(),
    }


def run_stage_once(report_dir: Path, config: dict[str, object], settings: dict[str, object]) -> dict[str, object]:
    bundle = prepare_bundle(report_dir)
    status = str(bundle.get("status"))
    if status not in {"run-stage", "run-post-stage"}:
        if status == "complete":
            delivered = auto_deliver_final_report(report_dir, settings)
            if delivered is not None:
                result = dict(bundle)
                result["delivery"] = delivered
                return result
        return bundle

    payloads = actionable_payloads(bundle)
    dispatch_mode = str(bundle.get("dispatchMode", "serial"))
    results: list[dict[str, object]] = []

    if dispatch_mode == "parallel" and len(payloads) > 1:
        with ThreadPoolExecutor(max_workers=len(payloads)) as executor:
            futures = [executor.submit(execute_role, report_dir, bundle, payload, config, settings) for payload in payloads]
            for future in futures:
                results.append(future.result())
    else:
        for payload in payloads:
            results.append(execute_role(report_dir, bundle, payload, config, settings))

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

    advance_result = advance(report_dir)
    delivery_result = None
    if isinstance(advance_result, dict):
        next_action = advance_result.get("nextAction", {})
        if isinstance(next_action, dict) and str(next_action.get("status")) == "complete":
            delivery_result = auto_deliver_final_report(report_dir, settings)
    return {
        "status": "stage-run-finished",
        "stageId": bundle["stageId"],
        "roleResults": results,
        "advanceResult": advance_result,
        "delivery": delivery_result,
    }


def run_until_gate(report_dir: Path, config: dict[str, object], max_cycles: int, settings: dict[str, object]) -> dict[str, object]:
    cycles: list[dict[str, object]] = []
    for _ in range(max_cycles):
        step = run_stage_once(report_dir, config, settings)
        cycles.append(step)
        status = str(step.get("status"))
        if status in {"await-approval", "no-go", "complete", "role-failed", "takeover-required"}:
            return {"status": status, "cycles": cycles, "final": step, "gateAction": step, "delivery": step.get("delivery")}
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
            return {
                "status": next_status,
                "cycles": cycles,
                "final": step,
                "gateAction": next_action,
                "delivery": step.get("delivery"),
            }
    return {"status": "max-cycles-exceeded", "cycles": cycles}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run_once_parser = sub.add_parser("run-once", help="Execute the current actionable stage via external runtime commands")
    run_once_parser.add_argument("--report-dir", required=True)
    run_once_parser.add_argument("--runtime-config", required=True)
    run_once_parser.add_argument("--execution-profile", choices=EXECUTION_PROFILES)
    run_once_parser.add_argument("--strict-real", action="store_true")
    run_once_parser.add_argument("--delivery-backend", choices=("relay-only", "command"))
    run_once_parser.add_argument("--delivery-channel")
    run_once_parser.add_argument("--delivery-caption")
    run_once_parser.add_argument("--delivery-command", nargs="+")
    run_once_parser.add_argument("--delivery-timeout-seconds", type=int)
    run_once_parser.set_defaults(auto_delivery=None)
    run_once_delivery_group = run_once_parser.add_mutually_exclusive_group()
    run_once_delivery_group.add_argument("--auto-delivery", dest="auto_delivery", action="store_true")
    run_once_delivery_group.add_argument("--no-auto-delivery", dest="auto_delivery", action="store_false")

    run_until_parser = sub.add_parser("run-until-gate", help="Keep executing stages until approval/no-go/complete/failure")
    run_until_parser.add_argument("--report-dir", required=True)
    run_until_parser.add_argument("--runtime-config", required=True)
    run_until_parser.add_argument("--max-cycles", type=int, default=20)
    run_until_parser.add_argument("--execution-profile", choices=EXECUTION_PROFILES)
    run_until_parser.add_argument("--strict-real", action="store_true")
    run_until_parser.add_argument("--delivery-backend", choices=("relay-only", "command"))
    run_until_parser.add_argument("--delivery-channel")
    run_until_parser.add_argument("--delivery-caption")
    run_until_parser.add_argument("--delivery-command", nargs="+")
    run_until_parser.add_argument("--delivery-timeout-seconds", type=int)
    run_until_parser.set_defaults(auto_delivery=None)
    run_until_delivery_group = run_until_parser.add_mutually_exclusive_group()
    run_until_delivery_group.add_argument("--auto-delivery", dest="auto_delivery", action="store_true")
    run_until_delivery_group.add_argument("--no-auto-delivery", dest="auto_delivery", action="store_false")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    report_dir = resolve_path(args.report_dir)
    config = load_runtime_config(args.runtime_config)
    settings = orchestration_settings(
        report_dir,
        execution_profile_override=args.execution_profile,
        strict_real_override=args.strict_real,
        delivery_backend_override=args.delivery_backend,
        delivery_channel_override=args.delivery_channel,
        delivery_caption_override=args.delivery_caption,
        delivery_command_override=args.delivery_command,
        delivery_timeout_override=args.delivery_timeout_seconds,
        auto_delivery_override=args.auto_delivery,
    )

    if args.command == "run-once":
        result = run_stage_once(report_dir, config, settings)
    elif args.command == "run-until-gate":
        result = run_until_gate(report_dir, config, args.max_cycles, settings)
    else:
        raise SystemExit(f"ERROR: unsupported command {args.command}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
