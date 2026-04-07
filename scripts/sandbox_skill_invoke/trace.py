"""Trace mode: static SKILL.md analysis without real execution."""

from __future__ import annotations

import re
import time
from pathlib import Path

from sandbox_skill_invoke.core import read_text


def build_trace(
    skill_md: Path,
    message: str,
    channel: str,
    tools: list[str],
    strict_real: bool,
    requested_mode: str,
    skill_name: str,
    skill_target: Path,
) -> dict[str, object]:
    content = read_text(skill_md)
    trigger_lines = _extract_trigger_lines(content)
    message_lower = message.lower()

    trigger_matched: bool | None = None
    trace_steps: list[dict[str, object]] = []

    for trigger_line in trigger_lines:
        keywords = re.findall(r"[\w\u4e00-\u9fff]{2,}", trigger_line.lower())
        if any(keyword in message_lower for keyword in keywords):
            trigger_matched = True
            trace_steps.append({
                "step": 1,
                "action": "trigger-match",
                "detail": f"Message matched trigger: {trigger_line}",
                "tools": [],
            })
            break

    if trigger_matched is None:
        trace_steps.append({
            "step": 1,
            "action": "trigger-match-undetermined",
            "detail": "Only static trace available; trace output cannot prove a real pass",
            "tools": [],
        })

    for index, tool in enumerate(tools, start=2):
        trace_steps.append({
            "step": index,
            "action": "tool-trace",
            "detail": f"Would call tool: {tool}",
            "tools": [tool],
        })

    return {
        "requestedMode": requested_mode,
        "selectedMode": "trace",
        "executionLevel": "trace",
        "realExecuted": False,
        "strictReal": strict_real,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "skillName": skill_name,
        "skillPath": str(skill_target),
        "message": message,
        "channel": channel,
        "triggerMatched": trigger_matched,
        "toolsCalled": tools,
        "traceSteps": trace_steps,
        "status": "trace-complete",
    }


def _extract_trigger_lines(content: str) -> list[str]:
    lines: list[str] = []
    in_trigger_block = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if any(token in lower for token in ("trigger", "触发", "activation")):
            in_trigger_block = True
            continue
        if in_trigger_block:
            if line.startswith(("-", "*", "\u2022")):
                lines.append(line.lstrip("-*\u2022 ").strip())
            elif not line and lines:
                break
    return lines
