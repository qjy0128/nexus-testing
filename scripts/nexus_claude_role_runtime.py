#!/usr/bin/env python3
"""Run a stage-role payload through Claude Code in non-interactive print mode."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import argparse
import json
import subprocess
import sys

from nexus_testing.json_utils import load_json
from nexus_testing.path_utils import ROOT, resolve_path
from nexus_testing.role_runtime_prompt import build_runtime_prompt
from nexus_testing.sandbox_skill_invoke.core import read_text

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "resultFile": {"type": ["string", "null"]},
        "note": {"type": "string"},
        "status": {"type": "string"},
        "needsMainAgentTakeover": {"type": "boolean"},
        "blockers": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["resultFile", "note"],
    "additionalProperties": False,
}
def build_command(args: argparse.Namespace) -> list[str]:
    command = [args.claude_command]
    if args.claude_args:
        command.extend(args.claude_args)
    command.extend(
        [
            "--print",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(RESULT_SCHEMA, ensure_ascii=False),
            "--permission-mode",
            args.permission_mode,
        ]
    )
    if args.allowed_tools:
        command.extend(["--allowedTools", *args.allowed_tools])
    if args.model:
        command.extend(["--model", args.model])
    if args.add_dir:
        for item in args.add_dir:
            command.extend(["--add-dir", item])
    return command


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-file", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--claude-command", default="claude")
    parser.add_argument("--claude-args", nargs="*")
    parser.add_argument("--permission-mode", default="bypassPermissions")
    parser.add_argument("--allowed-tools", nargs="*")
    parser.add_argument("--model")
    parser.add_argument("--add-dir", nargs="*")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    payload = load_json(resolve_path(args.payload_file), label="role payload")
    if not isinstance(payload, dict):
        raise SystemExit("ERROR: payload must be a JSON object")
    prompt_text = read_text(resolve_path(args.prompt_file))

    prompt = build_runtime_prompt(payload, prompt_text, language="en", include_json_response_rules=True)
    command = build_command(args)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "cwd": str(ROOT),
                    "command": command,
                    "prompt": prompt,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    proc = subprocess.run(
        command + [prompt],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"ERROR: claude runtime failed with exit {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    text = proc.stdout.strip()
    if not text:
        raise SystemExit("ERROR: claude runtime returned empty output")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise SystemExit("ERROR: claude runtime output must be a JSON object")
    print(json.dumps(parsed, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
