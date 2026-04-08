#!/usr/bin/env python3
"""Run Flow A stage-five surface execution and write skill-results output."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from flow_a_localization import add_output_language_argument
from flow_a_command_builders import build_bin_command, build_launch_command, build_module_probe_command
from flow_a_mcp_client import StdioJsonRpcClient, choose_tool_for_call
from sandbox_skill_invoke.core import find_bash_executable, read_text, write_text

PROJECT_DIR = Path(__file__).resolve().parents[1]
INVOKE_SCRIPT = PROJECT_DIR / "scripts" / "sandbox_skill_invoke.py"
OUTPUT_LANGUAGE = "zh-CN"


def tr(zh: str, en: str) -> str:
    return zh if OUTPUT_LANGUAGE == "zh-CN" else en


def load_json(path: Path) -> dict[str, object]:
    return json.loads(read_text(path))


def load_testing_manifest(skill_path: Path) -> dict[str, object]:
    manifest_path = skill_path / "testing.json"
    if not manifest_path.exists():
        return {}
    try:
        return load_json(manifest_path)
    except json.JSONDecodeError:
        return {}


def _safe_timeout(value: object, default: int = 30) -> int:
    """Parse a timeout value with bounds clamping (1–3600 seconds)."""
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(1, min(result, 3600))


def normalize_harness_block(block: object) -> dict[str, object]:
    if isinstance(block, str):
        return {"command": block}
    if isinstance(block, dict):
        return dict(block)
    return {}


def render_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def default_message(surface: dict[str, object]) -> str:
    capabilities = list(surface.get("linkedCapabilityNames", []))
    if capabilities:
        return f"surface-smoke {surface.get('surfaceId')} exercise {' '.join(str(item) for item in capabilities[:2])}"
    return f"surface-smoke {surface.get('surfaceId')} {surface.get('kind')}"


def run_skill_surface(
    surface: dict[str, object],
    skill_path: Path,
    session_id: str,
    sandbox_root: Path,
    channel: str,
    strict_real: bool,
    verification_manifest: Path | None,
) -> dict[str, object]:
    mode = str(surface.get("minimumMode", "trace"))
    message = default_message(surface)
    command = [
        sys.executable,
        str(INVOKE_SCRIPT),
        "--session-id",
        session_id,
        "--skill-path",
        str(skill_path),
        "--message",
        message,
        "--channel",
        channel,
        "--mode",
        mode,
        "--sandbox-root",
        str(sandbox_root),
    ]
    if strict_real and mode in {"live", "shim-live"}:
        command.append("--strict-real")
    if verification_manifest and mode == "shim-live":
        command.extend(["--verification-manifest", str(verification_manifest)])

    proc = subprocess.run(
        command,
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    kv: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        kv[key.strip()] = value.strip()

    invoke_status = kv.get("INVOKE_STATUS", "unknown")
    execution_level = kv.get("EXECUTION_LEVEL", mode)
    if proc.returncode == 0 and invoke_status == "success":
        status = "passed"
    elif invoke_status in {"trace-complete", "dry-run-complete"}:
        status = "incomplete"
    else:
        status = "blocked"

    evidence: list[str] = []
    for key in ("TOOL_TRACE_FILE", "OUTPUT_FILE", "CHANNEL_RENDER_FILE"):
        value = kv.get(key)
        if value:
            evidence.append(value)

    notes = (
        f"invoke-status={invoke_status}; selected-mode={kv.get('SELECTED_MODE', 'unknown')}; "
        f"return-code={proc.returncode}"
    )
    return {
        "surfaceId": surface.get("surfaceId"),
        "kind": surface.get("kind"),
        "identifier": surface.get("identifier"),
        "status": status,
        "executionLevel": execution_level,
        "evidence": evidence,
        "notes": notes,
    }


def mark_incomplete(
    surface: dict[str, object],
    reason: str,
    evidence: str,
    *,
    execution_level: str = "trace",
) -> dict[str, object]:
    return {
        "surfaceId": surface.get("surfaceId"),
        "kind": surface.get("kind"),
        "identifier": surface.get("identifier"),
        "status": "incomplete",
        "executionLevel": execution_level,
        "evidence": [evidence],
        "notes": reason,
    }


def mark_blocked(surface: dict[str, object], reason: str, evidence: str) -> dict[str, object]:
    return {
        "surfaceId": surface.get("surfaceId"),
        "kind": surface.get("kind"),
        "identifier": surface.get("identifier"),
        "status": "blocked",
        "executionLevel": surface.get("minimumMode", "trace"),
        "evidence": [evidence],
        "notes": reason,
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def note_token(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).replace("_", "-").lower()


def execution_logs_dir(execution_dir: Path) -> Path:
    logs_dir = execution_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def resolve_surface_path(skill_path: Path, surface: dict[str, object]) -> Path | None:
    raw_target = surface.get("command") or surface.get("path")
    if not isinstance(raw_target, str) or not raw_target.strip():
        return None
    return (skill_path / raw_target).resolve()


def run_bin_surface(
    surface: dict[str, object],
    skill_path: Path,
    execution_dir: Path,
) -> dict[str, object]:
    target = resolve_surface_path(skill_path, surface)
    if target is None:
        return mark_blocked(surface, tr("bin 表面缺少命令元数据", "bin surface is missing command metadata"), str(skill_path))
    if not target.exists():
        return mark_blocked(surface, tr(f"bin 目标不存在：{target}", f"bin target does not exist: {target}"), str(target))

    command, runtime_issue = build_bin_command(target, skill_path)
    if command is None:
        return mark_incomplete(surface, runtime_issue or tr("bin 运行时不可用", "bin runtime is unavailable"), str(target))

    proc = subprocess.run(
        command,
        cwd=str(skill_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    logs_dir = execution_logs_dir(execution_dir)
    stdout_path = logs_dir / f"{surface.get('surfaceId')}.stdout.log"
    stderr_path = logs_dir / f"{surface.get('surfaceId')}.stderr.log"
    write_text(stdout_path, proc.stdout)
    write_text(stderr_path, proc.stderr)

    status = "passed" if proc.returncode == 0 else "blocked"
    notes = f"command={render_command(command)}; return-code={proc.returncode}"
    return {
        "surfaceId": surface.get("surfaceId"),
        "kind": surface.get("kind"),
        "identifier": surface.get("identifier"),
        "status": status,
        "executionLevel": surface.get("minimumMode", "shim-live"),
        "evidence": [str(stdout_path), str(stderr_path)],
        "notes": notes,
    }


def resolve_command_items(command_value: object) -> list[str] | None:
    if isinstance(command_value, list) and command_value:
        return [str(item) for item in command_value]
    if isinstance(command_value, str) and command_value.strip():
        return shlex.split(command_value, posix=(os.name != "nt"))
    return None


def run_explicit_surface_harness(
    surface: dict[str, object],
    skill_path: Path,
    execution_dir: Path,
    *,
    harness_block: dict[str, object],
    result_flag: str,
    result_key: str,
    verification_note: str,
    execution_level: str | None = None,
    extra_success_flags: tuple[str, ...] = (),
    required_nonempty_fields: tuple[str, ...] = (),
    note_fields: tuple[str, ...] = (),
) -> dict[str, object]:
    command = resolve_command_items(harness_block.get("command"))
    if not command:
        return mark_incomplete(
            surface,
            tr(
                f"{surface.get('kind')} 的显式 harness 配置错误：缺少 command",
                f"explicit harness for {surface.get('kind')} is misconfigured: missing command",
            ),
            str(skill_path / "testing.json"),
            execution_level=execution_level or surface.get("minimumMode", "shim-live"),
        )

    cwd = skill_path / str(harness_block.get("cwd", "."))
    timeout_seconds = _safe_timeout(harness_block.get("timeoutSeconds", 30))
    logs_dir = execution_logs_dir(execution_dir)
    stdout_path = logs_dir / f"{surface.get('surfaceId')}.stdout.log"
    stderr_path = logs_dir / f"{surface.get('surfaceId')}.stderr.log"
    result_path = logs_dir / f"{surface.get('surfaceId')}.harness.json"

    env = os.environ.copy()
    env.update(
        {
            "NEXUS_SURFACE_ID": str(surface.get("surfaceId")),
            "NEXUS_SURFACE_KIND": str(surface.get("kind")),
            "NEXUS_SURFACE_IDENTIFIER": str(surface.get("identifier")),
            "NEXUS_SURFACE_PATH": str(surface.get("path") or ""),
            "NEXUS_SURFACE_COMMAND": str(surface.get("command") or ""),
            "NEXUS_SURFACE_RESULT_FILE": str(result_path),
            "NEXUS_ARTIFACTS_DIR": str(logs_dir),
        }
    )

    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return mark_blocked(
            surface,
            tr(f"显式 harness 超时：{timeout_seconds}s", f"explicit harness timed out after {timeout_seconds}s"),
            str(result_path),
        )
    except OSError as exc:
        return mark_blocked(
            surface,
            tr(f"显式 harness 启动失败：{exc}", f"explicit harness failed to start: {exc}"),
            str(skill_path / "testing.json"),
        )

    write_text(stdout_path, proc.stdout)
    write_text(stderr_path, proc.stderr)
    if proc.returncode != 0:
        return mark_blocked(
            surface,
            tr(f"显式 harness 退出码异常：{proc.returncode}", f"explicit harness exited with code {proc.returncode}"),
            str(stderr_path),
        )
    if not result_path.exists():
        return mark_blocked(
            surface,
            tr("显式 harness 未产出结果文件", "explicit harness did not produce a result file"),
            str(result_path),
        )

    try:
        payload = load_json(result_path)
    except (json.JSONDecodeError, ValueError):
        return mark_blocked(
            surface,
            tr("显式 harness 结果文件不是有效 JSON", "explicit harness result file contains invalid JSON"),
            str(result_path),
        )
    verified = bool(payload.get(result_flag))
    evidence = [str(stdout_path), str(stderr_path), str(result_path)]
    evidence.extend(str(item) for item in payload.get("evidence", []) if str(item).strip())
    notes = str(payload.get("notes", "explicit harness completed")).strip() or "explicit harness completed"
    verification_detail = ""
    result_value = payload.get(result_key)
    token_name = note_token(result_key)
    if isinstance(result_value, list):
        verification_detail = f"{token_name}={len(result_value)}"
        result_present = len(result_value) > 0
    elif isinstance(result_value, dict):
        verification_detail = f"{token_name}={len(result_value)}"
        result_present = len(result_value) > 0
    elif result_value in (None, "", False):
        result_present = False
    else:
        verification_detail = f"{token_name}=present"
        result_present = True
    if verified:
        for flag_name in extra_success_flags:
            if not bool(payload.get(flag_name)):
                return mark_blocked(
                    surface,
                    tr(
                        f"显式 harness 缺少必需成功标记 `{flag_name}=true`",
                        f"explicit harness is missing required success flag `{flag_name}=true`",
                    ),
                    str(result_path),
                )
        for field_name in required_nonempty_fields:
            if payload.get(field_name) in (None, "", False, [], {}):
                return mark_blocked(
                    surface,
                    tr(
                        f"显式 harness 缺少必需字段 `{field_name}`",
                        f"explicit harness is missing required field `{field_name}`",
                    ),
                    str(result_path),
                )
        if not result_present:
            return mark_blocked(
                surface,
                tr(
                    f"显式 harness 标记 {verification_note}=true，但缺少 `{result_key}` 证据",
                    f"explicit harness marked {verification_note}=true without `{result_key}` evidence",
                ),
                str(result_path),
            )
        if verification_detail:
            notes = f"{notes}; {verification_detail}"
        notes = f"{notes}; {verification_note}=true"
        for flag_name in extra_success_flags:
            notes = f"{notes}; {note_token(flag_name)}=true"
        for field_name in note_fields:
            field_value = payload.get(field_name)
            if field_value in (None, "", False, [], {}):
                continue
            notes = f"{notes}; {note_token(field_name)}={field_value}"
        status = "passed"
    else:
        if verification_detail:
            notes = f"{notes}; {verification_detail}"
        notes = f"{notes}; {verification_note}=false"
        status = "blocked"

    return {
        "surfaceId": surface.get("surfaceId"),
        "kind": surface.get("kind"),
        "identifier": surface.get("identifier"),
        "status": status,
        "executionLevel": execution_level or surface.get("minimumMode", "shim-live"),
        "evidence": evidence,
        "notes": notes,
    }


def count_openclaw_hook_entries(skill_path: Path) -> tuple[int, list[str]]:
    hook_manifest = skill_path / "hooks" / "hooks.json"
    if not hook_manifest.exists():
        return 0, []
    try:
        payload = load_json(hook_manifest)
    except (json.JSONDecodeError, ValueError):
        return 0, []
    hooks_block = payload.get("hooks")
    if not isinstance(hooks_block, dict):
        return 0, []
    hook_count = 0
    labels: list[str] = []
    for event_name, entries in hooks_block.items():
        if not isinstance(entries, list):
            continue
        event_hooks = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            hooks = entry.get("hooks")
            if isinstance(hooks, list):
                event_hooks += len(hooks)
        if event_hooks:
            hook_count += event_hooks
            labels.append(f"{event_name}:{event_hooks}")
    return hook_count, labels


def run_openclaw_extension_live_probe(
    surface: dict[str, object],
    skill_path: Path,
    session_id: str,
    sandbox_root: Path,
    channel: str,
    strict_real: bool,
) -> dict[str, object]:
    runtime_surface = dict(surface)
    runtime_surface["minimumMode"] = "live"
    runtime_result = run_skill_surface(
        runtime_surface,
        skill_path,
        session_id,
        sandbox_root,
        channel,
        strict_real,
        verification_manifest=None,
    )
    runtime_result["executionLevel"] = "live"
    if runtime_result.get("status") != "passed":
        runtime_result["notes"] = f"{runtime_result.get('notes', '')}; runtime-probed=false".strip("; ")
        return runtime_result

    hook_count, hook_labels = count_openclaw_hook_entries(skill_path)
    notes = [
        str(runtime_result.get("notes", "")).strip(),
        "runtime-probed=true",
        "runtime-transport=openclaw-live",
    ]
    if hook_count > 0:
        notes.append(f"registered-hooks={hook_count}")
        notes.append(f"hook-manifest-events={','.join(hook_labels)}")
    else:
        notes.append("registered-hooks=0")
    return {
        "surfaceId": surface.get("surfaceId"),
        "kind": surface.get("kind"),
        "identifier": surface.get("identifier"),
        "status": "incomplete",
        "executionLevel": "live",
        "evidence": list(runtime_result.get("evidence", [])),
        "notes": "; ".join(note for note in notes if note),
    }


def probe_module_surface(
    surface: dict[str, object],
    skill_path: Path,
    execution_dir: Path,
    *,
    execution_level: str,
) -> dict[str, object]:
    target = resolve_surface_path(skill_path, surface)
    if target is None:
        return mark_blocked(surface, tr("surface 缺少路径元数据", "surface is missing path metadata"), str(skill_path))
    if not target.exists():
        return mark_blocked(surface, tr(f"surface 目标不存在：{target}", f"surface target does not exist: {target}"), str(target))

    command, runtime_issue = build_module_probe_command(target, skill_path)
    if command is None:
        return mark_incomplete(surface, runtime_issue or tr("模块探针运行时不可用", "module probe runtime is unavailable"), str(target))

    proc = subprocess.run(
        command,
        cwd=str(skill_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    logs_dir = execution_logs_dir(execution_dir)
    stdout_path = logs_dir / f"{surface.get('surfaceId')}.stdout.log"
    stderr_path = logs_dir / f"{surface.get('surfaceId')}.stderr.log"
    write_text(stdout_path, proc.stdout)
    write_text(stderr_path, proc.stderr)

    notes = f"command={render_command(command)}; return-code={proc.returncode}"
    if proc.returncode != 0:
        return {
            "surfaceId": surface.get("surfaceId"),
            "kind": surface.get("kind"),
            "identifier": surface.get("identifier"),
            "status": "blocked",
            "executionLevel": execution_level,
            "evidence": [str(stdout_path), str(stderr_path)],
            "notes": notes,
        }
    return {
        "surfaceId": surface.get("surfaceId"),
        "kind": surface.get("kind"),
        "identifier": surface.get("identifier"),
        "status": "incomplete",
        "executionLevel": execution_level,
        "evidence": [str(stdout_path), str(stderr_path)],
            "notes": f"{notes}; probe-only=true",
        }


def run_generic_mcp_surface(
    surface: dict[str, object],
    skill_path: Path,
    execution_dir: Path,
    *,
    harness_block: dict[str, object] | None = None,
) -> dict[str, object]:
    target = resolve_surface_path(skill_path, surface)
    if target is None:
        return mark_incomplete(
            surface,
            tr("mcp 表面缺少可启动命令元数据", "mcp surface has no launchable command metadata"),
            str(skill_path),
            execution_level=surface.get("minimumMode", "shim-live"),
        )

    command = None
    cwd = skill_path
    timeout_seconds = 20
    protocol_versions: list[str] = []
    if harness_block:
        command = resolve_command_items(harness_block.get("command"))
        cwd = skill_path / str(harness_block.get("cwd", "."))
        timeout_seconds = _safe_timeout(harness_block.get("timeoutSeconds", timeout_seconds), default=timeout_seconds)
        protocol_versions = [str(item) for item in harness_block.get("protocolVersions", []) if str(item).strip()]
    if not command:
        command, runtime_issue = build_launch_command(target, skill_path)
        if command is None:
            return mark_incomplete(
                surface,
                runtime_issue or tr("mcp 运行时不可用", "mcp runtime is unavailable"),
                str(target),
                execution_level=surface.get("minimumMode", "shim-live"),
            )

    if not protocol_versions:
        protocol_versions = ["2025-03-26", "2024-11-05"]

    logs_dir = execution_logs_dir(execution_dir)
    stdout_path = logs_dir / f"{surface.get('surfaceId')}.mcp-transcript.json"
    stderr_path = logs_dir / f"{surface.get('surfaceId')}.stderr.log"

    try:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        return mark_blocked(surface, tr(f"mcp harness 启动失败：{exc}", f"mcp harness failed to start: {exc}"), str(cwd))
    client = StdioJsonRpcClient(proc, stdout_path)
    try:
        init_response: dict[str, object] | None = None
        init_version = ""
        last_error = ""
        for version in protocol_versions:
            try:
                init_response = client.request(
                    1,
                    "initialize",
                    {
                        "protocolVersion": version,
                        "capabilities": {},
                        "clientInfo": {"name": "nexus-testing", "version": "0.9.36"},
                    },
                    timeout=5.0,
                )
                if "result" in init_response:
                    init_version = version
                    break
                last_error = json.dumps(init_response.get("error", {}), ensure_ascii=False)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)

        if init_response is None or "result" not in init_response:
            return mark_blocked(surface, tr(f"mcp initialize 失败：{last_error}", f"mcp initialize failed: {last_error}"), str(stdout_path))

        client.notify("notifications/initialized", {})
        tools_response = client.request(2, "tools/list", {}, timeout=5.0)
        if "result" not in tools_response:
            return mark_blocked(
                surface,
                tr(
                    f"mcp tools/list 失败：{json.dumps(tools_response.get('error', {}), ensure_ascii=False)}",
                    f"mcp tools/list failed: {json.dumps(tools_response.get('error', {}), ensure_ascii=False)}",
                ),
                str(stdout_path),
            )

        tools = list(tools_response.get("result", {}).get("tools", []))
        tool_call_status = "skipped"
        selected_tool = choose_tool_for_call(tools)
        if selected_tool is not None:
            tool_response = client.request(
                3,
                "tools/call",
                {"name": selected_tool.get("name"), "arguments": {}},
                timeout=5.0,
            )
            if "result" in tool_response:
                tool_call_status = f"called:{selected_tool.get('name')}"
            else:
                tool_call_status = f"error:{selected_tool.get('name')}"
        return {
            "surfaceId": surface.get("surfaceId"),
            "kind": surface.get("kind"),
            "identifier": surface.get("identifier"),
            "status": "passed",
            "executionLevel": surface.get("minimumMode", "shim-live"),
            "evidence": [str(stdout_path), str(stderr_path)],
            "notes": f"protocol-version={init_version}; tools={len(tools)}; tool-call={tool_call_status}; protocol-verified=true",
        }
    except Exception as exc:  # noqa: BLE001
        return mark_blocked(surface, tr(f"mcp harness 执行失败：{exc}", f"mcp harness failed: {exc}"), str(stdout_path))
    finally:
        client.write_transcript()
        write_text(stderr_path, client.stderr_text())
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)


def validate_json_surface(
    surface: dict[str, object],
    target: Path,
    execution_dir: Path,
    required_keys: tuple[str, ...] = (),
) -> dict[str, object]:
    if not target.exists():
        return mark_blocked(surface, tr(f"必需文件不存在：{target}", f"required file does not exist: {target}"), str(target))
    try:
        payload = json.loads(read_text(target))
    except json.JSONDecodeError as exc:
        return mark_blocked(surface, tr(f"JSON 解析失败：{exc}", f"json parse failed: {exc}"), str(target))

    missing = [key for key in required_keys if key not in payload]
    if missing:
        return mark_blocked(
            surface,
            tr(
                f"JSON 表面缺少必需字段：{', '.join(missing)}",
                f"json surface is missing required keys: {', '.join(missing)}",
            ),
            str(target),
        )

    logs_dir = execution_logs_dir(execution_dir)
    evidence_path = logs_dir / f"{surface.get('surfaceId')}.trace.json"
    write_json(
        evidence_path,
        {
            "surfaceId": surface.get("surfaceId"),
            "kind": surface.get("kind"),
            "target": str(target),
            "keys": sorted(str(key) for key in payload.keys()),
        },
    )
    return {
        "surfaceId": surface.get("surfaceId"),
        "kind": surface.get("kind"),
        "identifier": surface.get("identifier"),
        "status": "passed",
        "executionLevel": "trace",
        "evidence": [str(evidence_path)],
        "notes": f"validated-json={target.name}",
    }


def render_result_block(entry: dict[str, object]) -> str:
    evidence = ", ".join(entry.get("evidence", [])) or "(none)"
    lines = [
        f"### {entry.get('surfaceId')} - {entry.get('kind')} (`{entry.get('identifier')}`)",
        f"- surface-id: `{entry.get('surfaceId')}`",
        f"- execution-level: `{entry.get('executionLevel')}`",
        f"- status: `{entry.get('status')}`",
        f"- evidence: `{evidence}`",
        f"- notes: {entry.get('notes')}",
        "",
    ]
    return "\n".join(lines)


def render_skill_results(results: list[dict[str, object]]) -> str:
    counts = {"passed": 0, "blocked": 0, "incomplete": 0}
    for item in results:
        counts[str(item["status"])] += 1
    lines = [
        "# TEST-EXECUTION/skill-results",
        "",
        tr("## Surface 汇总", "## Surface Summary"),
        "",
        f"- {tr('passed', 'passed')}: {counts['passed']}",
        f"- {tr('blocked', 'blocked')}: {counts['blocked']}",
        f"- {tr('incomplete', 'incomplete')}: {counts['incomplete']}",
        "",
        tr("## Surface 执行记录", "## Surface Execution Records"),
        "",
    ]
    for result in results:
        lines.append(render_result_block(result))
    return "\n".join(lines)


def update_coverage(coverage: dict[str, object], results: list[dict[str, object]]) -> dict[str, object]:
    result_map = {str(item["surfaceId"]): item for item in results}
    for surface in coverage.get("surfaces", []):
        match = result_map.get(str(surface.get("surfaceId")))
        if not match:
            continue
        surface["status"] = match["status"]
        surface["executionLevel"] = match["executionLevel"]
        surface["evidence"] = match["evidence"]
        surface["notes"] = match["notes"]
    return coverage


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface-plan", required=True)
    parser.add_argument("--skill-path", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--sandbox-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--channel", default="telegram")
    parser.add_argument("--strict-real", action="store_true")
    parser.add_argument("--verification-manifest")
    add_output_language_argument(parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    global OUTPUT_LANGUAGE
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    OUTPUT_LANGUAGE = args.language
    surface_plan_path = Path(args.surface_plan).expanduser().resolve()
    skill_path = Path(args.skill_path).expanduser().resolve()
    sandbox_root = Path(args.sandbox_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    verification_manifest = (
        Path(args.verification_manifest).expanduser().resolve()
        if args.verification_manifest
        else None
    )

    if not surface_plan_path.exists():
        raise SystemExit(f"ERROR: surface plan does not exist: {surface_plan_path}")
    if not skill_path.exists():
        raise SystemExit(f"ERROR: skill path does not exist: {skill_path}")
    if not (sandbox_root / args.session_id).exists():
        raise SystemExit(f"ERROR: session does not exist: {sandbox_root / args.session_id}")

    plan = load_json(surface_plan_path)
    execution_dir = output_dir / "TEST-EXECUTION"
    execution_dir.mkdir(parents=True, exist_ok=True)
    coverage_path = execution_dir / "SURFACE-COVERAGE.json"
    try:
        coverage = load_json(coverage_path) if coverage_path.exists() else {"surfaces": []}
    except (json.JSONDecodeError, ValueError):
        coverage = {"surfaces": []}

    results: list[dict[str, object]] = []
    has_bash = find_bash_executable() is not None
    testing_manifest = load_testing_manifest(skill_path)
    for surface in plan.get("surfaces", []):
        kind = str(surface.get("kind", "unknown"))
        if kind == "skill":
            if not has_bash:
                results.append(
                    mark_incomplete(
                        surface,
                        tr("缺少可运行 bash；已跳过 shim-live/live 执行", "runnable bash is unavailable; shim-live/live execution skipped"),
                        str(surface_plan_path),
                    )
                )
            else:
                results.append(
                    run_skill_surface(
                        surface=surface,
                        skill_path=skill_path,
                        session_id=args.session_id,
                        sandbox_root=sandbox_root,
                        channel=args.channel,
                        strict_real=args.strict_real,
                        verification_manifest=verification_manifest,
                    )
                )
            continue

        if kind == "bin":
            results.append(run_bin_surface(surface, skill_path, execution_dir))
            continue

        if kind == "package":
            target = resolve_surface_path(skill_path, surface)
            if target is None:
                target = skill_path / "package.json"
            results.append(validate_json_surface(surface, target, execution_dir, ("name",)))
            continue

        if kind == "plugin-manifest":
            target = resolve_surface_path(skill_path, surface)
            if target is None:
                target = skill_path / "openclaw.plugin.json"
            results.append(validate_json_surface(surface, target, execution_dir))
            continue

        if kind == "openclaw-extension":
            runtime_harness_block = normalize_harness_block(testing_manifest.get("openclawExtensionRuntimeHarness"))
            harness_block = normalize_harness_block(testing_manifest.get("openclawExtensionHarness"))
            if runtime_harness_block:
                results.append(
                    run_explicit_surface_harness(
                        surface,
                        skill_path,
                        execution_dir,
                        harness_block=runtime_harness_block,
                        result_flag="behaviorVerified",
                        result_key="registeredHooks",
                        verification_note="behavior-verified",
                        execution_level="live",
                        extra_success_flags=("runtimeVerified",),
                        required_nonempty_fields=("runtimeTransport",),
                        note_fields=("runtimeTransport",),
                    )
                )
            elif harness_block:
                results.append(
                    run_explicit_surface_harness(
                        surface,
                        skill_path,
                        execution_dir,
                        harness_block=harness_block,
                        result_flag="behaviorVerified",
                        result_key="registeredHooks",
                        verification_note="behavior-verified",
                    )
                )
            elif has_bash:
                results.append(
                    run_openclaw_extension_live_probe(
                        surface,
                        skill_path,
                        args.session_id,
                        sandbox_root,
                        args.channel,
                        args.strict_real,
                    )
                )
            else:
                results.append(
                    probe_module_surface(
                        surface,
                        skill_path,
                        execution_dir,
                        execution_level=surface.get("minimumMode", "shim-live"),
                    )
                )
            continue

        if kind == "mcp":
            results.append(
                run_generic_mcp_surface(
                    surface,
                    skill_path,
                    execution_dir,
                    harness_block=normalize_harness_block(testing_manifest.get("mcpHarness")) or None,
                )
            )
            continue

        results.append(
            mark_incomplete(
                surface,
                tr(
                    f"surface 类型 `{kind}` 缺少通用阶段五执行器；需要专用运行时",
                    f"no generic stage-five executor for surface kind `{kind}`; requires specialized runtime",
                ),
                str(surface_plan_path),
            )
        )

    write_text(execution_dir / "skill-results.md", render_skill_results(results) + "\n")
    write_text(
        coverage_path,
        json.dumps(update_coverage(coverage, results), ensure_ascii=False, indent=2) + "\n",
    )

    passed = sum(1 for item in results if item["status"] == "passed")
    blocked = sum(1 for item in results if item["status"] == "blocked")
    incomplete = sum(1 for item in results if item["status"] == "incomplete")
    print(f"PASSED_SURFACES={passed}")
    print(f"BLOCKED_SURFACES={blocked}")
    print(f"INCOMPLETE_SURFACES={incomplete}")
    print(f"SKILL_RESULTS={execution_dir / 'skill-results.md'}")
    print(f"SURFACE_COVERAGE={coverage_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
