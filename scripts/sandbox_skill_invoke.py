#!/usr/bin/env python3
"""Skill invocation harness with strict real-execution gating."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
WINDOWS_BASH_BLACKLIST = {"c:\\windows\\system32\\bash.exe"}
WINDOWS_GIT_BASH_CANDIDATES = (
    Path(r"C:\Program Files\Git\bin\bash.exe"),
    Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
    Path(r"C:\Program Files (x86)\Git\bin\bash.exe"),
    Path(r"C:\Program Files (x86)\Git\usr\bin\bash.exe"),
)
LIVE_TELEMETRY_PROTOCOL_VERSION = "nexus-live-telemetry/v1"
LIVE_TELEMETRY_SOURCE = "openclaw-runtime"
LIVE_TELEMETRY_REQUIRED_FIELDS = (
    "triggerMatched",
    "toolsCalled",
    "contextReferences",
    "deliveryStatus",
    "deliveryReceipts",
    "deliveryEvidence",
)


def kv(key: str, value: object) -> None:
    print(f"{key}={value}")


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def sanitize_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", name).strip("-")
    return safe or "unknown-skill"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def detect_command(*candidates: str) -> str | None:
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def is_supported_bash(candidate: str | Path) -> bool:
    resolved = str(Path(candidate)).strip()
    if not resolved:
        return False
    if os.name == "nt" and resolved.lower() in WINDOWS_BASH_BLACKLIST:
        return False
    try:
        proc = subprocess.run(
            [resolved, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    combined = f"{proc.stdout}\n{proc.stderr}".lower()
    return proc.returncode == 0 and "bash" in combined


def find_bash_executable() -> str | None:
    candidates: list[str] = []
    env_bash = os.environ.get("BASH")
    if env_bash:
        candidates.append(env_bash)
    if os.name == "nt":
        candidates.extend(str(p) for p in WINDOWS_GIT_BASH_CANDIDATES if p.exists())
    detected = detect_command("bash")
    if detected:
        candidates.append(detected)
    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(Path(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        if is_supported_bash(normalized):
            return normalized
    return None


def shell_quote_path(raw_path: str) -> str:
    return shlex.quote(Path(raw_path).as_posix())


def session_relative(path: Path | None, session_dir: Path) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(session_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def compute_source_fingerprint(skill_root: Path) -> str:
    digest = hashlib.sha256()
    ignored_parts = {
        ".git", ".hg", ".svn", ".nexus-sandbox", ".venv", "venv",
        "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
        "dist", "build", "coverage",
    }
    for path in sorted(item for item in skill_root.rglob("*") if item.is_file()):
        if any(part in ignored_parts for part in path.relative_to(skill_root).parts):
            continue
        digest.update(path.relative_to(skill_root).as_posix().encode("utf-8"))
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    return digest.hexdigest()


def load_json_list(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


@contextmanager
def audit_lock(session_dir: Path, timeout_seconds: float = 5.0):
    lock_dir = session_dir / "logs" / ".audit-lock"
    deadline = time.time() + timeout_seconds
    while True:
        try:
            lock_dir.mkdir(parents=False, exist_ok=False)
            break
        except FileExistsError:
            if time.time() >= deadline:
                raise TimeoutError("Timed out waiting for sandbox audit lock")
            time.sleep(0.05)
    try:
        yield
    finally:
        shutil.rmtree(lock_dir, ignore_errors=True)


def update_meta_metrics_unlocked(session_dir: Path, duration_ms: int) -> None:
    meta_file = session_dir / "META.json"
    if not meta_file.exists():
        return
    try:
        payload = json.loads(read_text(meta_file))
    except json.JSONDecodeError:
        return
    payload["commandCount"] = int(payload.get("commandCount", 0) or 0) + 1
    payload["totalDurationMs"] = int(payload.get("totalDurationMs", 0) or 0) + max(duration_ms, 0)
    write_text(meta_file, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def append_audit_entry(
    session_dir: Path, command_text: str, exit_code: int, duration_ms: int,
    status: str, execution_level: str, real_executed: bool,
    stdout_file: Path | None = None, stderr_file: Path | None = None,
    output_file: Path | None = None, extra: dict[str, object] | None = None,
) -> int:
    exit_codes_file = session_dir / "logs" / "exit-codes.json"
    with audit_lock(session_dir):
        existing = load_json_list(exit_codes_file)
        seq = len(existing) + 1
        entry: dict[str, object] = {
            "seq": seq, "tag": "", "command": command_text[:500],
            "exitCode": exit_code,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "durationMs": max(duration_ms, 0),
            "stdoutFile": session_relative(stdout_file, session_dir),
            "stderrFile": session_relative(stderr_file, session_dir),
            "outputFile": session_relative(output_file, session_dir),
            "status": status, "executionLevel": execution_level,
            "realExecuted": real_executed,
        }
        if extra:
            entry.update(extra)
        existing.append(entry)
        write_text(exit_codes_file, json.dumps(existing, ensure_ascii=False, indent=2) + "\n")
        update_meta_metrics_unlocked(session_dir, duration_ms)
        return seq


def parse_int_list(raw_values: list[str] | None) -> list[int]:
    result: list[int] = []
    if not raw_values:
        return result
    for raw_value in raw_values:
        for item in str(raw_value).split(","):
            item = item.strip()
            if item:
                result.append(int(item))
    return result


def normalize_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    return []


def normalize_context_references(value: object) -> list[int]:
    result: list[int] = []
    if not isinstance(value, list):
        return result
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def resolve_delivery_evidence_path(raw_value: str, session_dir: Path) -> Path | None:
    candidate = Path(raw_value.strip())
    path_like = (
        candidate.is_absolute()
        or "/" in raw_value
        or "\\" in raw_value
        or raw_value.startswith(".")
    )
    if not path_like:
        return None
    resolved = candidate.resolve() if candidate.is_absolute() else (session_dir / candidate).resolve()
    try:
        resolved.relative_to(session_dir.resolve())
    except ValueError:
        return None
    if not resolved.exists():
        return None
    return resolved


def dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in values:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def collect_delivery_metadata(result_payload: dict[str, object], session_dir: Path) -> tuple[str, list[str], list[str], list[str]]:
    status = "unknown"
    receipts: list[str] = []
    evidence_items: list[str] = []
    delivery = result_payload.get("delivery")
    if isinstance(delivery, dict):
        raw_status = str(delivery.get("status", "")).strip()
        if raw_status:
            status = raw_status
        for key in ("receipt", "receiptId"):
            raw_value = delivery.get(key)
            if raw_value:
                receipts.extend(normalize_string_list(raw_value))
        evidence_items.extend(normalize_string_list(delivery.get("evidence")))
        evidence_items.extend(normalize_string_list(delivery.get("proof")))
    top_status = str(result_payload.get("deliveryStatus", "")).strip()
    if top_status:
        status = top_status
    receipts.extend(normalize_string_list(result_payload.get("deliveryReceipt")))
    receipts.extend(normalize_string_list(result_payload.get("deliveryReceipts")))
    evidence_items.extend(normalize_string_list(result_payload.get("deliveryEvidence")))
    valid_evidence: list[str] = []
    invalid_evidence: list[str] = []
    for item in dedupe_strings(evidence_items):
        resolved = resolve_delivery_evidence_path(item, session_dir)
        if resolved is None:
            invalid_evidence.append(item)
        else:
            valid_evidence.append(session_relative(resolved, session_dir))
    return status, dedupe_strings(receipts), dedupe_strings(valid_evidence), dedupe_strings(invalid_evidence)


def evaluate_assertions(
    *, expect_trigger: str | None, require_tools: list[str],
    expect_context_refs: list[int], require_delivery_status: str | None,
    require_delivery_evidence: bool, actual_trigger: str, actual_tools: list[str],
    actual_context_refs: list[int], delivery_status: str,
    delivery_receipts: list[str], delivery_evidence: list[str],
    invalid_delivery_evidence: list[str],
) -> list[str]:
    failures: list[str] = []
    if expect_trigger is not None and actual_trigger != expect_trigger:
        failures.append(f"expected triggerMatched={expect_trigger}, got {actual_trigger}")
    if require_tools:
        actual_tool_set = {item.strip() for item in actual_tools if item.strip()}
        missing = [item for item in require_tools if item not in actual_tool_set]
        if missing:
            failures.append(f"missing expected tools: {', '.join(missing)}")
    if expect_context_refs:
        actual_ref_set = set(actual_context_refs)
        missing_refs = [str(item) for item in expect_context_refs if item not in actual_ref_set]
        if missing_refs:
            failures.append(f"missing expected context references: {', '.join(missing_refs)}")
    if require_delivery_status and delivery_status != require_delivery_status:
        failures.append(f"expected deliveryStatus={require_delivery_status}, got {delivery_status}")
    if require_delivery_evidence and not delivery_evidence:
        failures.append("delivery evidence is required but missing verified proof files")
    if invalid_delivery_evidence:
        failures.append(f"invalid delivery evidence paths: {', '.join(invalid_delivery_evidence)}")
    if require_delivery_status and not delivery_receipts and not delivery_evidence:
        failures.append("delivery status was asserted but neither receipts nor verified proof files were present")
    return failures


def resolve_skill_path(raw_path: str) -> tuple[Path, Path]:
    target = Path(raw_path).expanduser()
    if target.is_file():
        return target.parent.resolve(), target.resolve()
    if target.is_dir():
        skill_md = (target / "SKILL.md").resolve()
        if skill_md.exists():
            return target.resolve(), skill_md
        raise SystemExit(f"ERROR: No SKILL.md found in {raw_path}")
    raise SystemExit(f"ERROR: Skill path does not exist: {raw_path}")


def extract_skill_name(skill_md: Path) -> str:
    content = read_text(skill_md)
    match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"').strip("'")
    return skill_md.parent.name or "unknown-skill"


def read_declared_tools(skill_md: Path) -> list[str]:
    content = read_text(skill_md)
    tools: list[str] = []
    in_allowed_tools = False
    for line in content.splitlines():
        if re.match(r"^allowed[_-]tools:", line, re.IGNORECASE):
            in_allowed_tools = True
            continue
        if in_allowed_tools:
            match = re.match(r"^\s*-\s*(.+)$", line)
            if match:
                tools.append(match.group(1).strip())
            elif line.strip() and not line.startswith(" "):
                in_allowed_tools = False
    return tools


def build_auto_install_command(skill_root: Path) -> tuple[str, str | None]:
    commands: list[str] = []
    if (skill_root / "requirements.txt").exists():
        commands.append(f"{shell_quote_path(sys.executable)} -m pip install -r requirements.txt")
    if (skill_root / "package-lock.json").exists():
        if not detect_command("npm"):
            return "", "package-lock.json present but npm is unavailable"
        commands.append("npm ci")
    elif (skill_root / "package.json").exists():
        if not detect_command("npm"):
            return "", "package.json present but npm is unavailable"
        commands.append("npm install")
    return " && ".join(commands), None


def path_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def detect_repo_root(start: Path) -> Path | None:
    resolved = start.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def resolve_cwd_within_root(root: Path, requested: str, root_label: str) -> Path:
    resolved = (root / (requested or ".")).resolve()
    if resolved == root or path_within(root, resolved):
        return resolved
    raise ValueError(f"cwd escapes the {root_label} directory")


def load_result_payload(result_file: Path, stdout_text: str = "", stderr_text: str = "") -> dict[str, object]:
    payload: dict[str, object] = {}
    if result_file.exists():
        try:
            payload = json.loads(read_text(result_file))
        except json.JSONDecodeError:
            payload = {}
    if not payload and stdout_text:
        payload = extract_result_payload_from_text(stdout_text)
    if not payload and stderr_text:
        payload = extract_result_payload_from_text(stderr_text)
    return payload


def load_verifier_manifest(raw_path: str | None, skill_root: Path) -> dict[str, object]:
    if not raw_path:
        return {"available": False, "source": "none", "trust": "self-reported", "required": False}
    manifest_path = Path(raw_path).expanduser()
    if not manifest_path.is_absolute():
        manifest_path = (PROJECT_DIR / manifest_path).resolve()
    if not manifest_path.exists():
        return {"available": False, "error": f"verification manifest not found: {raw_path}", "source": str(manifest_path), "required": True}
    if path_within(skill_root, manifest_path):
        return {"available": False, "error": "verification manifest must live outside the skill directory to be independent", "source": str(manifest_path), "required": True}
    skill_repo_root = detect_repo_root(skill_root)
    manifest_repo_root = detect_repo_root(manifest_path)
    if skill_repo_root and manifest_repo_root and skill_repo_root == manifest_repo_root:
        return {"available": False, "error": "verification manifest must live outside the skill source repository to be independent", "source": str(manifest_path), "required": True}
    try:
        raw = json.loads(read_text(manifest_path))
    except json.JSONDecodeError as exc:
        return {"available": False, "error": f"verification manifest parse failed: {exc}", "source": str(manifest_path), "required": True}
    verify_block: object = raw.get("verify", raw) if isinstance(raw, dict) else raw
    if isinstance(verify_block, str):
        verify = {"command": verify_block}
    elif isinstance(verify_block, dict):
        verify = verify_block
    else:
        verify = {}
    command = str(verify.get("command", "")).strip()
    if not command:
        return {"available": False, "error": "verification manifest is missing verify.command", "source": str(manifest_path), "required": True}
    manifest_dir = manifest_path.parent.resolve()
    try:
        cwd = resolve_cwd_within_root(manifest_dir, str(verify.get("cwd", ".")).strip() or ".", "verification manifest")
    except ValueError as exc:
        return {"available": False, "error": str(exc), "source": str(manifest_path), "required": True}
    timeout = verify.get("timeoutSeconds")
    timeout_seconds = int(timeout) if isinstance(timeout, int) and timeout > 0 else None
    return {"available": True, "source": str(manifest_path), "manifest_path": manifest_path, "command": command, "cwd": cwd, "trust": "independent", "timeout_seconds": timeout_seconds, "required": True}


def detect_adapter(skill_root: Path) -> dict[str, object]:
    testing_json = skill_root / "testing.json"
    if testing_json.exists():
        try:
            raw = json.loads(read_text(testing_json))
        except json.JSONDecodeError as exc:
            return {"available": False, "error": f"testing.json parse failed: {exc}"}
        def normalize(block: object) -> dict[str, object]:
            if block is None:
                return {}
            if isinstance(block, str):
                return {"command": block}
            if isinstance(block, dict):
                return block
            return {}
        install = normalize(raw.get("install"))
        invoke = normalize(raw.get("invoke"))
        supports = raw.get("supportsMultiTurn")
        supports_text = "unknown"
        if supports is True:
            supports_text = "true"
        elif supports is False:
            supports_text = "false"
        invoke_command = str(invoke.get("command", "")).strip()
        if not invoke_command:
            return {"available": False, "error": "testing.json is missing invoke.command"}
        return {"available": True, "source": "testing.json", "install_command": str(install.get("command", "")).strip(), "install_cwd": str(install.get("cwd", ".")).strip() or ".", "invoke_command": invoke_command, "invoke_cwd": str(invoke.get("cwd", ".")).strip() or ".", "supports_multi_turn": supports_text}
    candidates = ("scripts/test-entry.py", "scripts/test-entry.js", "scripts/test-entry.mjs", "scripts/test-entry.cjs", "scripts/test-entry.ts", "scripts/test-entry.sh")
    install_command, install_error = build_auto_install_command(skill_root)
    if install_error:
        return {"available": False, "error": install_error}
    for candidate in candidates:
        entry = skill_root / candidate
        if not entry.exists():
            continue
        if candidate.endswith(".py"):
            command = f"{shell_quote_path(sys.executable)} {shlex.quote(Path(candidate).as_posix())}"
        elif candidate.endswith((".js", ".mjs", ".cjs")):
            node = detect_command("node")
            if not node:
                return {"available": False, "error": "Node adapter present but node is unavailable"}
            command = f"{shell_quote_path(node)} {shlex.quote(Path(candidate).as_posix())}"
        elif candidate.endswith(".ts"):
            local_tsx = skill_root / "node_modules" / ".bin" / ("tsx.cmd" if os.name == "nt" else "tsx")
            if local_tsx.exists():
                command = f"{shell_quote_path(str(local_tsx))} {shlex.quote(Path(candidate).as_posix())}"
            elif detect_command("npx"):
                command = f"{shell_quote_path(detect_command('npx') or 'npx')} --no-install tsx {shlex.quote(Path(candidate).as_posix())}"
            else:
                return {"available": False, "error": "TypeScript adapter requires local tsx or npx"}
        else:
            bash = find_bash_executable()
            if not bash:
                return {"available": False, "error": "Shell adapter present but bash is unavailable"}
            command = f"{shell_quote_path(bash)} {shlex.quote(Path(candidate).as_posix())}"
        return {"available": True, "source": candidate, "install_command": install_command, "install_cwd": ".", "invoke_command": command, "invoke_cwd": ".", "supports_multi_turn": "unknown"}
    return {"available": False, "error": "no testing.json or scripts/test-entry.* found"}


def resolve_cwd_within_skill(skill_root: Path, requested: str) -> Path:
    return resolve_cwd_within_root(skill_root, requested, "skill")


def run_shell(command: str, cwd: Path, timeout: int, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    bash = find_bash_executable()
    if not bash:
        raise RuntimeError("bash is required for shim-live command execution")
    return subprocess.run([bash, "-lc", command], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env)


def build_trace(skill_md: Path, message: str, channel: str, tools: list[str], strict_real: bool, requested_mode: str, skill_name: str, skill_target: Path) -> dict[str, object]:
    content = read_text(skill_md)
    trigger_lines: list[str] = []
    in_trigger_block = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if any(token in lower for token in ("trigger", "\u89e6\u53d1", "activation")):
            in_trigger_block = True
            continue
        if in_trigger_block:
            if line.startswith(("-", "*", "\u2022")):
                trigger_lines.append(line.lstrip("-*\u2022 ").strip())
            elif not line and trigger_lines:
                break
    message_lower = message.lower()
    trigger_matched: bool | None = None
    trace_steps: list[dict[str, object]] = []
    for trigger_line in trigger_lines:
        keywords = re.findall(r"[\w\u4e00-\u9fff]{2,}", trigger_line.lower())
        if any(keyword in message_lower for keyword in keywords):
            trigger_matched = True
            trace_steps.append({"step": 1, "action": "trigger-match", "detail": f"Message matched trigger: {trigger_line}", "tools": []})
            break
    if trigger_matched is None:
        trace_steps.append({"step": 1, "action": "trigger-match-undetermined", "detail": "Only static trace available; trace output cannot prove a real pass", "tools": []})
    for index, tool in enumerate(tools, start=2):
        trace_steps.append({"step": index, "action": "tool-trace", "detail": f"Would call tool: {tool}", "tools": [tool]})
    return {"requestedMode": requested_mode, "selectedMode": "trace", "executionLevel": "trace", "realExecuted": False, "strictReal": strict_real, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()), "skillName": skill_name, "skillPath": str(skill_target), "message": message, "channel": channel, "triggerMatched": trigger_matched, "toolsCalled": tools, "traceSteps": trace_steps, "status": "trace-complete"}


def extract_result_payload_from_text(raw_text: str) -> dict[str, object]:
    text = (raw_text or "").strip()
    if not text:
        return {}
    if text.startswith("{") and text.endswith("}"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return payload
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("NEXUS_RESULT_JSON="):
            raw_value = stripped.split("=", 1)[1].strip()
            try:
                payload = json.loads(raw_value)
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}
    marker_start = "NEXUS_RESULT_JSON_START"
    marker_end = "NEXUS_RESULT_JSON_END"
    if marker_start in text and marker_end in text:
        inner = text.split(marker_start, 1)[1].split(marker_end, 1)[0].strip()
        try:
            payload = json.loads(inner)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def inspect_live_runtime_telemetry(result_payload: dict[str, object]) -> dict[str, object]:
    protocol_version = str(result_payload.get("telemetryProtocolVersion", "")).strip()
    telemetry_source = str(result_payload.get("telemetrySource", "")).strip()
    issues: list[str] = []
    if not result_payload or not protocol_version:
        return {"status": "missing", "protocol_version": protocol_version or "missing", "telemetry_source": telemetry_source or "unknown", "issues": [f"OpenClaw CLI did not emit runtime telemetry protocol {LIVE_TELEMETRY_PROTOCOL_VERSION}"]}
    if protocol_version != LIVE_TELEMETRY_PROTOCOL_VERSION:
        issues.append(f"expected telemetryProtocolVersion={LIVE_TELEMETRY_PROTOCOL_VERSION}, got {protocol_version}")
    if telemetry_source != LIVE_TELEMETRY_SOURCE:
        issues.append(f"expected telemetrySource={LIVE_TELEMETRY_SOURCE}, got {telemetry_source or 'missing'}")
    if not isinstance(result_payload.get("triggerMatched"), bool):
        issues.append("runtime telemetry is missing boolean triggerMatched")
    if not isinstance(result_payload.get("toolsCalled"), list):
        issues.append("runtime telemetry is missing array toolsCalled")
    if not isinstance(result_payload.get("contextReferences"), list):
        issues.append("runtime telemetry is missing array contextReferences")
    if not str(result_payload.get("deliveryStatus", "")).strip():
        issues.append("runtime telemetry is missing non-empty deliveryStatus")
    if not isinstance(result_payload.get("deliveryReceipts"), list):
        issues.append("runtime telemetry is missing array deliveryReceipts")
    if not isinstance(result_payload.get("deliveryEvidence"), list):
        issues.append("runtime telemetry is missing array deliveryEvidence")
    return {"status": "passed" if not issues else "invalid", "protocol_version": protocol_version or "missing", "telemetry_source": telemetry_source or "unknown", "issues": issues}


def merge_telemetry_payload(adapter_payload: dict[str, object], verifier_payload: dict[str, object]) -> dict[str, object]:
    merged = dict(adapter_payload)
    if not verifier_payload:
        return merged
    for key in ("triggerMatched", "toolsCalled", "contextReferences", "assistantMessage", "delivery", "deliveryStatus", "deliveryReceipt", "deliveryReceipts", "deliveryEvidence", "artifacts", "notes"):
        if key in verifier_payload:
            merged[key] = verifier_payload[key]
    return merged


def write_preferred_output(result_payload: dict[str, object], output_file: Path, stdout_text: str) -> None:
    assistant_message = str(result_payload.get("assistantMessage", "") or "")
    existing_output = read_text(output_file) if output_file.exists() else ""
    if assistant_message:
        write_text(output_file, assistant_message if assistant_message.endswith("\n") else assistant_message + "\n")
    elif existing_output:
        return
    elif stdout_text:
        write_text(output_file, stdout_text)
    else:
        write_text(output_file, "")


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
    source_fingerprint = compute_source_fingerprint(skill_dir)
    verifier_manifest = load_verifier_manifest(args.verification_manifest, skill_dir)
    if args.verification_manifest and not verifier_manifest.get("available"):
        raise SystemExit(f"ERROR: {verifier_manifest.get('error', 'invalid verification manifest')}")
    skill_target = skills_dir / f"{skill_name_safe}-{source_fingerprint[:12]}"
    if not (skill_target / "SKILL.md").exists():
        if skill_target.exists():
            shutil.rmtree(skill_target)
        shutil.copytree(skill_dir, skill_target)
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

    if args.strict_real and selected_mode == "trace":
        return blocked("blocked-no-real-exec", "Neither OpenClaw live runtime nor shim adapter is available")

    kv("SESSION_ID", args.session_id); kv("SKILL_NAME", skill_name_safe); kv("INSTALL_STATUS", install_status)

    if selected_mode == "dry-run":
        if adapter.get("available") and adapter.get("install_command"):
            install_stdout_file = logs_dir / f"{timestamp}-install.stdout.log"
            install_stderr_file = logs_dir / f"{timestamp}-install.stderr.log"
            try:
                install_cwd = resolve_cwd_within_skill(skill_target, str(adapter.get("install_cwd", ".")))
                env = os.environ.copy()
                env.update({"NEXUS_SESSION_ID": args.session_id, "NEXUS_MESSAGE": args.message or "", "NEXUS_CHANNEL": args.channel, "NEXUS_SKILL_PATH": str(skill_target), "NEXUS_WORKSPACE_DIR": str(workspace_dir), "NEXUS_OUTPUT_FILE": str(output_file), "NEXUS_RESULT_JSON_FILE": str(result_json_file), "NEXUS_HISTORY_FILE": str(history_file or ""), "NEXUS_ARTIFACTS_DIR": str(artifacts_dir), "NEXUS_STRICT_REAL": bool_text(args.strict_real)})
                install_proc = run_shell(str(adapter["install_command"]), install_cwd, max(args.timeout, 120), env)
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
        if adapter.get("install_command"):
            install_stdout_file = logs_dir / f"{timestamp}-install.stdout.log"
            install_stderr_file = logs_dir / f"{timestamp}-install.stderr.log"
            try:
                install_cwd = resolve_cwd_within_skill(skill_target, str(adapter.get("install_cwd", ".")))
                install_proc = run_shell(str(adapter["install_command"]), install_cwd, max(args.timeout, 120), env)
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
            invoke_proc = run_shell(str(adapter["invoke_command"]), invoke_cwd, args.timeout, env)
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
                verifier_proc = run_shell(
                    str(verifier_manifest["command"]),
                    verifier_cwd, verifier_timeout, verifier_env,
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
            live_cmd = f"{shell_quote_path(openclaw)} invoke --skill {shell_quote_path(str(skill_target))} --message {shlex.quote(args.message or '')} --channel {args.channel} --output {shell_quote_path(str(output_file))} --result {shell_quote_path(str(live_result_file))}"
            live_proc = run_shell(live_cmd, skill_target, args.timeout, live_env)
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
        return 0 if not assertion_failures else 3

    return blocked("blocked-unknown-mode", f"unhandled mode: {selected_mode}")


if __name__ == "__main__":
    raise SystemExit(main())
