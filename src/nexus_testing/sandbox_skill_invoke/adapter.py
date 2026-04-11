"""Adapter detection: testing.json and scripts/test-entry.* support."""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

from nexus_testing.sandbox_skill_invoke.core import (
    detect_command,
    find_bash_executable,
    read_text,
    shell_quote_path,
)


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


def _normalize_adapter_block(block: object) -> dict[str, object]:
    if block is None:
        return {}
    if isinstance(block, str):
        return {"command": block}
    if isinstance(block, dict):
        return block
    return {}


def _command_to_str(cmd: object) -> str:
    """Convert a command value (str or list) to a shell string."""
    if isinstance(cmd, list):
        return shlex.join(str(c) for c in cmd)
    return str(cmd).strip()


def detect_adapter(skill_root: Path) -> dict[str, object]:
    testing_json = skill_root / "testing.json"
    if testing_json.exists():
        return _detect_from_testing_json(testing_json)

    return _detect_from_entry_scripts(skill_root)


def _detect_from_testing_json(testing_json: Path) -> dict[str, object]:
    try:
        raw = json.loads(read_text(testing_json))
    except json.JSONDecodeError as exc:
        return {"available": False, "error": f"testing.json parse failed: {exc}"}

    install = _normalize_adapter_block(raw.get("install"))
    invoke = _normalize_adapter_block(raw.get("invoke"))
    supports = raw.get("supportsMultiTurn")
    supports_text = "unknown"
    if supports is True:
        supports_text = "true"
    elif supports is False:
        supports_text = "false"

    invoke_command = _command_to_str(invoke.get("command", ""))
    if not invoke_command:
        return {"available": False, "error": "testing.json is missing invoke.command"}

    return {
        "available": True,
        "source": "testing.json",
        "install_command": _command_to_str(install.get("command", "")),
        "install_cwd": str(install.get("cwd", ".")).strip() or ".",
        "invoke_command": invoke_command,
        "invoke_cwd": str(invoke.get("cwd", ".")).strip() or ".",
        "supports_multi_turn": supports_text,
    }


def _detect_from_entry_scripts(skill_root: Path) -> dict[str, object]:
    candidates = (
        "scripts/test-entry.py",
        "scripts/test-entry.js",
        "scripts/test-entry.mjs",
        "scripts/test-entry.cjs",
        "scripts/test-entry.ts",
        "scripts/test-entry.sh",
    )
    install_command, install_error = build_auto_install_command(skill_root)
    if install_error:
        return {"available": False, "error": install_error}

    for candidate in candidates:
        entry = skill_root / candidate
        if not entry.exists():
            continue

        command = _build_entry_command(candidate, entry)
        if command is None:
            return {"available": False, "error": f"Cannot build command for {candidate}"}

        return {
            "available": True,
            "source": candidate,
            "install_command": install_command,
            "install_cwd": ".",
            "invoke_command": command,
            "invoke_cwd": ".",
            "supports_multi_turn": "unknown",
        }

    return {"available": False, "error": "no testing.json or scripts/test-entry.* found"}


def _build_entry_command(candidate: str, entry: Path) -> str | None:
    if candidate.endswith(".py"):
        return f"{shell_quote_path(sys.executable)} {shlex.quote(entry.as_posix())}"
    if candidate.endswith((".js", ".mjs", ".cjs")):
        node = detect_command("node")
        if not node:
            return None
        return f"{shell_quote_path(node)} {shlex.quote(entry.as_posix())}"
    if candidate.endswith(".ts"):
        local_tsx = entry.parent.parent / "node_modules" / ".bin" / ("tsx.cmd" if os.name == "nt" else "tsx")
        if local_tsx.exists():
            return f"{shell_quote_path(str(local_tsx))} {shlex.quote(entry.as_posix())}"
        npx = detect_command("npx")
        if npx:
            return f"{shell_quote_path(npx)} --no-install tsx {shlex.quote(entry.as_posix())}"
        return None
    # .sh
    bash = find_bash_executable()
    if not bash:
        return None
    return f"{shell_quote_path(bash)} {shlex.quote(entry.as_posix())}"
