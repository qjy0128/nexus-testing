"""Adapter detection: testing.json and scripts/test-entry.* support."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from nexus_testing.sandbox_skill_invoke.core import (
    CommandSpec,
    detect_command,
    find_bash_executable,
    read_text,
)


def build_auto_install_commands(skill_root: Path) -> tuple[list[CommandSpec], str | None]:
    commands: list[CommandSpec] = []
    if (skill_root / "requirements.txt").exists():
        commands.append([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    if (skill_root / "package-lock.json").exists():
        if not detect_command("npm"):
            return [], "package-lock.json present but npm is unavailable"
        commands.append(["npm", "ci"])
    elif (skill_root / "package.json").exists():
        if not detect_command("npm"):
            return [], "package.json present but npm is unavailable"
        commands.append(["npm", "install"])
    return commands, None


def _normalize_adapter_block(block: object) -> dict[str, object]:
    if block is None:
        return {}
    if isinstance(block, str):
        return {"command": block}
    if isinstance(block, dict):
        return block
    return {}


def _normalize_command(cmd: object) -> CommandSpec:
    if isinstance(cmd, (list, tuple)):
        return [str(part) for part in cmd]
    return str(cmd).strip()


def _normalize_command_list(cmd: object) -> list[CommandSpec]:
    if isinstance(cmd, list) and cmd and all(isinstance(item, (list, tuple)) for item in cmd):
        return [[str(part) for part in item] for item in cmd]
    normalized = _normalize_command(cmd)
    if _command_is_empty(normalized):
        return []
    return [normalized]


def _command_is_empty(command: CommandSpec) -> bool:
    if isinstance(command, str):
        return not command
    return not command or not str(command[0]).strip()


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

    invoke_command = _normalize_command(invoke.get("command", ""))
    if _command_is_empty(invoke_command):
        return {"available": False, "error": "testing.json is missing invoke.command"}

    return {
        "available": True,
        "source": "testing.json",
        "install_commands": _normalize_command_list(install.get("command", "")),
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
    install_commands, install_error = build_auto_install_commands(skill_root)
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
            "install_commands": install_commands,
            "install_cwd": ".",
            "invoke_command": command,
            "invoke_cwd": ".",
            "supports_multi_turn": "unknown",
        }

    return {"available": False, "error": "no testing.json or scripts/test-entry.* found"}


def _build_entry_command(candidate: str, entry: Path) -> CommandSpec | None:
    if candidate.endswith(".py"):
        return [sys.executable, entry.as_posix()]
    if candidate.endswith((".js", ".mjs", ".cjs")):
        node = detect_command("node")
        if not node:
            return None
        return [node, entry.as_posix()]
    if candidate.endswith(".ts"):
        local_tsx = entry.parent.parent / "node_modules" / ".bin" / ("tsx.cmd" if os.name == "nt" else "tsx")
        if local_tsx.exists():
            return [str(local_tsx), entry.as_posix()]
        npx = detect_command("npx")
        if npx:
            return [npx, "--no-install", "tsx", entry.as_posix()]
        return None
    # .sh
    bash = find_bash_executable()
    if not bash:
        return None
    return [bash, entry.as_posix()]
