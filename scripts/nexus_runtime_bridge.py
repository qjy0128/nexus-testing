#!/usr/bin/env python3
"""Host runtime bridge that executes DISPATCH bundles with external commands."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from nexus_dispatch_runner import (
    complete_role,
    fail_role,
    load_json,
    prepare_bundle,
    role_state_path,
    runner_root,
    stage_run_status,
    start_role,
)
from nexus_stage_executor import resolve_path
from sandbox_skill_invoke.core import read_text, write_text

ROOT = Path(__file__).resolve().parents[1]


def load_runtime_config(path_value: str | None) -> dict[str, object]:
    if not path_value:
        raise SystemExit("ERROR: --runtime-config is required")
    path = resolve_path(path_value)
    if not path.exists():
        raise SystemExit(f"ERROR: runtime config does not exist: {path}")
    payload = json.loads(read_text(path))
    if not isinstance(payload, dict):
        raise SystemExit("ERROR: runtime config must be a JSON object")
    return payload


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
    bundle_manifest = load_json(manifest_file, {})
    if not isinstance(bundle_manifest, dict):
        raise SystemExit("ERROR: invalid bundle manifest")
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


def parse_role_stdout(stdout: str) -> tuple[str | None, str | None]:
    text = stdout.strip()
    if not text:
        return None, None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None, text
    if not isinstance(parsed, dict):
        return None, text
    result_file = parsed.get("resultFile")
    note = parsed.get("note")
    return (str(result_file) if result_file else None), (str(note) if note else None)


def log_file_prefix(report_dir: Path, stage_id: str, role_id: str) -> Path:
    return runner_root(report_dir, stage_id) / role_id


def save_process_logs(report_dir: Path, stage_id: str, role_id: str, stdout: str, stderr: str) -> tuple[str, str]:
    prefix = log_file_prefix(report_dir, stage_id, role_id)
    stdout_path = prefix.with_suffix(".stdout.log")
    stderr_path = prefix.with_suffix(".stderr.log")
    write_text(stdout_path, stdout)
    write_text(stderr_path, stderr)
    return str(stdout_path), str(stderr_path)


def execute_role(report_dir: Path, bundle: dict[str, object], payload: dict[str, object], config: dict[str, object]) -> dict[str, object]:
    role_id = str(payload["roleId"])
    stage_id = str(payload["stageId"])
    context = payload_context(report_dir, bundle, payload)
    spec = runtime_spec(config, role_id)
    command_value = spec.get("command")
    if not isinstance(command_value, list) or not command_value:
        raise SystemExit(f"ERROR: runtime config for role {role_id} must provide a non-empty command list")
    command = render_list(command_value, context)

    cwd_value = spec.get("cwd")
    cwd = render_value(str(cwd_value), context) if cwd_value else str(ROOT)

    env = None
    env_value = spec.get("env")
    if isinstance(env_value, dict):
        env = dict(os.environ)
        env.update({key: render_value(str(value), context) for key, value in env_value.items()})

    timeout_value = spec.get("timeoutSeconds", config.get("timeoutSeconds", 900))
    timeout_seconds = int(timeout_value)
    runtime_name = str(spec.get("name") or config.get("name") or "external-runtime")

    start_role(report_dir, stage_id, role_id, runtime_name)
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        stdout_path, stderr_path = save_process_logs(report_dir, stage_id, role_id, "", f"timeout after {timeout_seconds} seconds\n")
        failed = fail_role(report_dir, stage_id, role_id, f"timeout after {timeout_seconds} seconds; logs={stdout_path},{stderr_path}")
        return {"roleId": role_id, "status": "failed", "detail": failed}
    except Exception as exc:
        stdout_path, stderr_path = save_process_logs(report_dir, stage_id, role_id, "", f"{type(exc).__name__}: {exc}\n")
        failed = fail_role(
            report_dir,
            stage_id,
            role_id,
            f"runtime exception {type(exc).__name__}: {exc}; logs={stdout_path},{stderr_path}",
        )
        return {"roleId": role_id, "status": "failed", "detail": failed}

    stdout_path, stderr_path = save_process_logs(report_dir, stage_id, role_id, proc.stdout, proc.stderr)
    if proc.returncode != 0:
        note = f"exit={proc.returncode}; logs={stdout_path},{stderr_path}"
        failed = fail_role(report_dir, stage_id, role_id, note)
        return {"roleId": role_id, "status": "failed", "detail": failed}

    result_file, note = parse_role_stdout(proc.stdout)
    if result_file:
        result_path = Path(result_file)
        if not result_path.is_absolute():
            result_file = str((report_dir / result_path).resolve())
    success_note = note or f"logs={stdout_path},{stderr_path}"
    completed = complete_role(report_dir, stage_id, role_id, result_file, success_note)
    return {"roleId": role_id, "status": "completed", "detail": completed}


def actionable_payloads(bundle: dict[str, object]) -> list[dict[str, object]]:
    items = bundle.get("dispatchPayloads", [])
    return [item for item in items if isinstance(item, dict)]


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
    failed_results = [item for item in results if item.get("status") == "failed"]
    if failed_results:
        return {
            "status": "role-failed",
            "stageId": bundle["stageId"],
            "roleResults": results,
            "runStatus": run_status,
        }

    from nexus_dispatch_runner import advance

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
        if status in {"await-approval", "no-go", "complete", "role-failed"}:
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
