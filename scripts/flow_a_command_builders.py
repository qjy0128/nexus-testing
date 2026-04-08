"""Command builder functions for Flow A surface execution.

Maps file extensions to the correct runtime command (Python, Node, tsx, bash).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sandbox_skill_invoke.core import detect_command, find_bash_executable


def build_bin_command(target: Path, skill_path: Path) -> tuple[list[str] | None, str | None]:
    """Build a --help probe command for a bin surface target."""
    suffix = target.suffix.lower()
    if suffix == ".py":
        return [sys.executable, str(target), "--help"], None
    if suffix in {".js", ".mjs", ".cjs"}:
        node = detect_command("node")
        if not node:
            return None, "node runtime is unavailable"
        return [node, str(target), "--help"], None
    if suffix == ".ts":
        local_tsx = skill_path / "node_modules" / ".bin" / ("tsx.cmd" if os.name == "nt" else "tsx")
        if local_tsx.exists():
            return [str(local_tsx), str(target), "--help"], None
        npx = detect_command("npx")
        if npx:
            return [npx, "--no-install", "tsx", str(target), "--help"], None
        return None, "tsx runtime is unavailable"
    if suffix == ".sh":
        bash = find_bash_executable()
        if not bash:
            return None, "bash runtime is unavailable"
        return [bash, str(target), "--help"], None
    if os.access(target, os.X_OK):
        return [str(target), "--help"], None
    return None, f"unsupported bin target suffix `{suffix or 'none'}`"


def build_launch_command(target: Path, skill_path: Path) -> tuple[list[str] | None, str | None]:
    """Build a launch command for running a surface target (e.g. MCP server)."""
    suffix = target.suffix.lower()
    if suffix == ".py":
        return [sys.executable, str(target)], None
    if suffix in {".js", ".mjs", ".cjs"}:
        node = detect_command("node")
        if not node:
            return None, "node runtime is unavailable"
        return [node, str(target)], None
    if suffix == ".ts":
        local_tsx = skill_path / "node_modules" / ".bin" / ("tsx.cmd" if os.name == "nt" else "tsx")
        if local_tsx.exists():
            return [str(local_tsx), str(target)], None
        npx = detect_command("npx")
        if npx:
            return [npx, "--no-install", "tsx", str(target)], None
        return None, "tsx runtime is unavailable"
    if suffix == ".sh":
        bash = find_bash_executable()
        if not bash:
            return None, "bash runtime is unavailable"
        return [bash, str(target)], None
    if os.access(target, os.X_OK):
        return [str(target)], None
    return None, f"unsupported launch target suffix `{suffix or 'none'}`"


def build_module_probe_command(target: Path, skill_path: Path) -> tuple[list[str] | None, str | None]:
    """Build a command that probes whether a target can be loaded as a module."""
    suffix = target.suffix.lower()
    if suffix == ".py":
        script = (
            "import importlib.util, pathlib, sys; "
            "target = pathlib.Path(sys.argv[1]); "
            "spec = importlib.util.spec_from_file_location('nexus_surface_probe', target); "
            "module = importlib.util.module_from_spec(spec); "
            "assert spec and spec.loader; "
            "spec.loader.exec_module(module); "
            "print('loaded')"
        )
        return [sys.executable, "-c", script, str(target)], None
    if suffix in {".js", ".mjs", ".cjs"}:
        node = detect_command("node")
        if not node:
            return None, "node runtime is unavailable"
        script = (
            "const { pathToFileURL } = require('url'); "
            "const target = process.argv[1]; "
            "import(pathToFileURL(target).href)"
            ".then(() => { console.log('loaded'); })"
            ".catch((error) => { console.error(error && error.stack ? error.stack : String(error)); process.exit(1); });"
        )
        return [node, "-e", script, str(target)], None
    if suffix == ".ts":
        local_tsx = skill_path / "node_modules" / ".bin" / ("tsx.cmd" if os.name == "nt" else "tsx")
        script = "import(process.argv[1]).then(() => console.log('loaded')).catch((error) => { console.error(error?.stack || String(error)); process.exit(1); });"
        if local_tsx.exists():
            return [str(local_tsx), "--eval", script, str(target)], None
        npx = detect_command("npx")
        if npx:
            return [npx, "--no-install", "tsx", "--eval", script, str(target)], None
        return None, "tsx runtime is unavailable"
    if suffix == ".sh":
        bash = find_bash_executable()
        if not bash:
            return None, "bash runtime is unavailable"
        return [bash, "-n", str(target)], None
    return None, f"unsupported module probe suffix `{suffix or 'none'}`"
