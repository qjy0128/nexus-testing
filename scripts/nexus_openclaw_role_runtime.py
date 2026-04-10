#!/usr/bin/env python3
"""Run a stage-role payload through OpenClaw CLI invoke mode."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from json_utils import load_json
from path_utils import ROOT, resolve_path
from role_runtime_prompt import build_runtime_prompt
from sandbox_skill_invoke.core import read_text
def render_existing_artifacts(report_dir: Path, patterns: list[object]) -> set[str]:
    found: set[str] = set()
    for item in patterns:
        pattern = str(item)
        if pattern.startswith("("):
            continue
        if "*" in pattern:
            for path in report_dir.glob(pattern):
                if path.is_file():
                    found.add(str(path.resolve()))
            continue
        target = report_dir / pattern
        if target.exists():
            found.add(str(target.resolve()))
    return found


def detect_new_artifact(report_dir: Path, patterns: list[object], before: set[str]) -> str | None:
    candidates = sorted(render_existing_artifacts(report_dir, patterns) - before)
    return candidates[0] if candidates else None


def build_command(args: argparse.Namespace, prompt: str, output_file: Path, result_file: Path) -> list[str]:
    command = [args.openclaw_command]
    if args.openclaw_args:
        command.extend(args.openclaw_args)
    command.extend(
        [
            "invoke",
            "--skill",
            str(resolve_path(args.skill_path)),
            "--message",
            prompt,
            "--channel",
            args.channel,
            "--output",
            str(output_file),
            "--result",
            str(result_file),
        ]
    )
    return command


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-file", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--openclaw-command", default="openclaw")
    parser.add_argument("--openclaw-args", nargs="*")
    parser.add_argument("--skill-path", default=str(ROOT))
    parser.add_argument("--channel", default="telegram")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    payload = load_json(resolve_path(args.payload_file), label="role payload")
    if not isinstance(payload, dict):
        raise SystemExit("ERROR: payload must be a JSON object")
    prompt_text = read_text(resolve_path(args.prompt_file))
    prompt = build_runtime_prompt(payload, prompt_text, language="zh", include_json_response_rules=False)

    payload_file = resolve_path(args.payload_file)
    runtime_dir = payload_file.parent
    output_file = runtime_dir / f"{payload_file.stem}.openclaw-output.md"
    result_file = runtime_dir / f"{payload_file.stem}.openclaw-result.json"

    command = build_command(args, prompt, output_file, result_file)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "cwd": str(resolve_path(args.skill_path)),
                    "command": command,
                    "prompt": prompt,
                    "outputFile": str(output_file),
                    "resultFile": str(result_file),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    report_dir = resolve_path(str(payload["reportDir"]))
    before = render_existing_artifacts(report_dir, list(payload.get("missingDeliverables", [])))
    env = dict(os.environ)
    env.update(
        {
            "NEXUS_REPORT_DIR": str(report_dir),
            "NEXUS_ROLE_ID": str(payload["roleId"]),
            "NEXUS_STAGE_ID": str(payload["stageId"]),
            "NEXUS_STAGE_LABEL": str(payload["stageLabel"]),
            "NEXUS_MISSING_DELIVERABLES": json.dumps(payload.get("missingDeliverables", []), ensure_ascii=False),
        }
    )

    proc = subprocess.run(
        command,
        cwd=str(resolve_path(args.skill_path)),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"ERROR: openclaw runtime failed with exit {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    structured_result = None
    if result_file.exists():
        try:
            structured_result = json.loads(result_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            structured_result = None

    result_path = None
    note = "openclaw invoke completed"
    status = None
    needs_takeover = False
    blockers: list[str] = []
    if isinstance(structured_result, dict):
        if structured_result.get("resultFile"):
            result_path = str(structured_result["resultFile"])
        if structured_result.get("note"):
            note = str(structured_result["note"])
        if structured_result.get("status"):
            status = str(structured_result["status"])
        needs_takeover = bool(structured_result.get("needsMainAgentTakeover", False))
        raw_blockers = structured_result.get("blockers", [])
        if isinstance(raw_blockers, list):
            blockers = [str(item) for item in raw_blockers if str(item).strip()]

    if not result_path:
        result_path = detect_new_artifact(report_dir, list(payload.get("missingDeliverables", [])), before)
    if not result_path and output_file.exists():
        result_path = str(output_file)

    print(
        json.dumps(
            {
                "resultFile": result_path,
                "note": note,
                "status": status,
                "needsMainAgentTakeover": needs_takeover,
                "blockers": blockers,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
