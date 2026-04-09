#!/usr/bin/env python3
"""Run a stage-role payload through Claude Code in non-interactive print mode."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from sandbox_skill_invoke.core import read_text

ROOT = Path(__file__).resolve().parents[1]

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


def resolve_path(path_value: str) -> Path:
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        return (ROOT / candidate).resolve()
    return candidate.resolve()


def extend_prompt_section(lines: list[str], title: str, items: list[object]) -> None:
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        return
    lines.extend(["", f"{title}:", *[f"- {item}" for item in values]])


def build_prompt(payload: dict[str, object], prompt_text: str) -> str:
    report_dir = str(payload["reportDir"])
    role_file = str(payload["roleFile"])
    role_id = str(payload["roleId"])
    stage_label = str(payload["stageLabel"])
    stage_name = str(payload["stageName"])
    missing = ", ".join(str(item) for item in payload.get("missingDeliverables", [])) or "(none)"
    lines = [
        f"You are the stage-role subagent `{role_id}` for {stage_label} {stage_name}.",
        f"Role file: {role_file}",
        f"Report directory: {report_dir}",
        f"Missing deliverables: {missing}",
        "",
        "Execution rules:",
        "- Work only for this role and this stage.",
        "- Create or update only the deliverables needed for this role in the report directory.",
        "- Do not ask the user for approval; that is handled by the orchestrator.",
        "- Do not leave TODOs, placeholders, or vague summaries in the final artifacts.",
        "- If you cannot finish real execution, record explicit blockers and mark the situation clearly instead of claiming success.",
        "- When finished, return only JSON matching the required schema.",
        "- Put the primary artifact path in resultFile. Use a path under the report directory when possible.",
    ]
    extend_prompt_section(lines, "Responsibilities", list(payload.get("responsibilities", [])))
    extend_prompt_section(lines, "Hard boundaries", list(payload.get("hardBoundaries", [])))
    extend_prompt_section(lines, "Execution rules from role doc", list(payload.get("executionRules", [])))
    extend_prompt_section(lines, "Evidence requirements", list(payload.get("evidenceRequirements", [])))
    extend_prompt_section(lines, "Anti-patterns to avoid", list(payload.get("antiPatterns", [])))
    extend_prompt_section(lines, "Minimum output structure", list(payload.get("minimumOutput", [])))
    lines.extend(
        [
            "",
            "Self-check before returning:",
            "- Every deliverable you claim to have produced exists on disk.",
            "- The deliverable content follows the role's required structure, not just a stub.",
            "- Blockers and residual gaps are explicit when anything remains unverified.",
            "",
            "Role launch prompt:",
            prompt_text.strip(),
            "",
            "JSON response requirements:",
            "- resultFile: primary artifact path you produced, or null if there is no single primary file.",
            "- note: one short sentence summarizing what you completed.",
            "- status: optional. Use `completed` when done, or `blocked` if you need takeover.",
            "- needsMainAgentTakeover: optional boolean. Set true when the host/main agent must continue the work because your environment is insufficient.",
            "- blockers: optional array of short blocker reasons.",
        ]
    )
    return "\n".join(lines)


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

    payload = json.loads(read_text(resolve_path(args.payload_file)))
    if not isinstance(payload, dict):
        raise SystemExit("ERROR: payload must be a JSON object")
    prompt_text = read_text(resolve_path(args.prompt_file))

    prompt = build_prompt(payload, prompt_text)
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
