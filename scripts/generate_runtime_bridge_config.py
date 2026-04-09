#!/usr/bin/env python3
"""Generate runtime-config JSON files for nexus_runtime_bridge.py."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from runtime_config_schema import validate_runtime_config
from sandbox_skill_invoke.core import write_text

ROOT = Path(__file__).resolve().parents[1]


def mock_config() -> dict[str, object]:
    return {
        "name": "mock-runtime",
        "default": {
            "command": [
                sys.executable,
                str(ROOT / "scripts" / "fixtures" / "mock_role_runtime.py"),
                "--payload-file",
                "{payload_file}",
                "--prompt-file",
                "{prompt_file}",
            ],
            "cwd": "{workspace_root}",
            "timeoutSeconds": 30,
        },
    }


def openclaw_config(
    openclaw_command: str,
    channel: str,
    skill_path: str,
) -> dict[str, object]:
    return {
        "name": "openclaw-role-runtime",
        "default": {
            "command": [
                sys.executable,
                str(ROOT / "scripts" / "nexus_openclaw_role_runtime.py"),
                "--payload-file",
                "{payload_file}",
                "--prompt-file",
                "{prompt_file}",
                "--openclaw-command",
                openclaw_command,
                "--skill-path",
                skill_path,
                "--channel",
                channel,
            ],
            "cwd": "{workspace_root}",
            "timeoutSeconds": 900,
        },
    }


def claude_config(
    claude_command: str,
    permission_mode: str,
    model: str | None,
    allowed_tools: list[str],
) -> dict[str, object]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "nexus_claude_role_runtime.py"),
        "--payload-file",
        "{payload_file}",
        "--prompt-file",
        "{prompt_file}",
        "--claude-command",
        claude_command,
        "--permission-mode",
        permission_mode,
    ]
    if model:
        command.extend(["--model", model])
    if allowed_tools:
        command.append("--allowed-tools")
        command.extend(allowed_tools)

    return {
        "name": "claude-role-runtime",
        "default": {
            "command": command,
            "cwd": "{workspace_root}",
            "timeoutSeconds": 900,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=("mock", "claude", "openclaw"), required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--claude-command", default="claude")
    parser.add_argument("--permission-mode", default="bypassPermissions")
    parser.add_argument("--model")
    parser.add_argument("--allowed-tools", nargs="*")
    parser.add_argument("--openclaw-command", default="openclaw")
    parser.add_argument("--channel", default="telegram")
    parser.add_argument("--skill-path", default=str(ROOT))
    args = parser.parse_args(argv)

    if args.preset == "mock":
        config = mock_config()
    elif args.preset == "openclaw":
        config = openclaw_config(
            openclaw_command=args.openclaw_command,
            channel=args.channel,
            skill_path=args.skill_path,
        )
    elif args.preset == "claude":
        config = claude_config(
            claude_command=args.claude_command,
            permission_mode=args.permission_mode,
            model=args.model,
            allowed_tools=args.allowed_tools or [],
        )
    else:
        raise SystemExit(f"ERROR: unsupported preset {args.preset}")

    config = validate_runtime_config(config)

    output_path = Path(args.output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_text(output_path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "generated", "preset": args.preset, "outputFile": str(output_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
