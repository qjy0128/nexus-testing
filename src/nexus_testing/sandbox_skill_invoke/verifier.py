"""Verifier manifest loading and independent verification support."""

from __future__ import annotations

import json
from pathlib import Path

from nexus_testing.sandbox_skill_invoke.core import (
    PROJECT_DIR,
    detect_repo_root,
    path_within,
    read_text,
    resolve_cwd_within_root,
)


def load_verifier_manifest(raw_path: str | None, skill_root: Path) -> dict[str, object]:
    if not raw_path:
        return {"available": False, "source": "none", "trust": "self-reported", "required": False}

    manifest_path = Path(raw_path).expanduser()
    if not manifest_path.is_absolute():
        manifest_path = (PROJECT_DIR / manifest_path).resolve()

    if not manifest_path.exists():
        return {
            "available": False,
            "error": f"verification manifest not found: {raw_path}",
            "source": str(manifest_path),
            "required": True,
        }

    if path_within(skill_root, manifest_path):
        return {
            "available": False,
            "error": "verification manifest must live outside the skill directory to be independent",
            "source": str(manifest_path),
            "required": True,
        }

    skill_repo_root = detect_repo_root(skill_root)
    manifest_repo_root = detect_repo_root(manifest_path)
    if skill_repo_root and manifest_repo_root and skill_repo_root == manifest_repo_root:
        return {
            "available": False,
            "error": "verification manifest must live outside the skill source repository to be independent",
            "source": str(manifest_path),
            "required": True,
        }

    try:
        raw = json.loads(read_text(manifest_path))
    except json.JSONDecodeError as exc:
        return {
            "available": False,
            "error": f"verification manifest parse failed: {exc}",
            "source": str(manifest_path),
            "required": True,
        }

    verify_block: object = raw.get("verify", raw) if isinstance(raw, dict) else raw
    if isinstance(verify_block, str):
        verify: dict[str, object] = {"command": verify_block}
    elif isinstance(verify_block, dict):
        verify = verify_block
    else:
        verify = {}

    command = str(verify.get("command", "")).strip()
    if not command:
        return {
            "available": False,
            "error": "verification manifest is missing verify.command",
            "source": str(manifest_path),
            "required": True,
        }

    manifest_dir = manifest_path.parent.resolve()
    try:
        cwd = resolve_cwd_within_root(
            manifest_dir,
            str(verify.get("cwd", ".")).strip() or ".",
            "verification manifest",
        )
    except ValueError as exc:
        return {
            "available": False,
            "error": str(exc),
            "source": str(manifest_path),
            "required": True,
        }

    timeout = verify.get("timeoutSeconds")
    timeout_seconds = int(timeout) if isinstance(timeout, int) and timeout > 0 else None

    return {
        "available": True,
        "source": str(manifest_path),
        "manifest_path": manifest_path,
        "command": command,
        "cwd": cwd,
        "trust": "independent",
        "timeout_seconds": timeout_seconds,
        "required": True,
    }
