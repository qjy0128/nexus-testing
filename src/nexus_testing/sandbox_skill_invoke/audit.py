"""Audit trail: lock, append entries, update META metrics."""

from __future__ import annotations

import json
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

from nexus_testing.sandbox_skill_invoke.core import read_text, session_relative, write_text


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
    try:
        payload["commandCount"] = int(payload.get("commandCount", 0) or 0) + 1
    except (TypeError, ValueError):
        payload["commandCount"] = 1
    try:
        payload["totalDurationMs"] = int(payload.get("totalDurationMs", 0) or 0) + max(duration_ms, 0)
    except (TypeError, ValueError):
        payload["totalDurationMs"] = max(duration_ms, 0)
    write_text(meta_file, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def append_audit_entry(
    session_dir: Path,
    command_text: str,
    exit_code: int,
    duration_ms: int,
    status: str,
    execution_level: str,
    real_executed: bool,
    stdout_file: Path | None = None,
    stderr_file: Path | None = None,
    output_file: Path | None = None,
    extra: dict[str, object] | None = None,
) -> int:
    exit_codes_file = session_dir / "logs" / "exit-codes.json"
    with audit_lock(session_dir):
        existing = load_json_list(exit_codes_file)
        seq = len(existing) + 1
        entry: dict[str, object] = {
            "seq": seq,
            "tag": "",
            "command": command_text[:500],
            "exitCode": exit_code,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "durationMs": max(duration_ms, 0),
            "stdoutFile": session_relative(stdout_file, session_dir),
            "stderrFile": session_relative(stderr_file, session_dir),
            "outputFile": session_relative(output_file, session_dir),
            "status": status,
            "executionLevel": execution_level,
            "realExecuted": real_executed,
        }
        if extra:
            entry.update(extra)
        existing.append(entry)
        write_text(exit_codes_file, json.dumps(existing, ensure_ascii=False, indent=2) + "\n")
        update_meta_metrics_unlocked(session_dir, duration_ms)
        return seq
