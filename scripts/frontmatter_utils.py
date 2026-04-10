#!/usr/bin/env python3
"""Shared helpers for simple YAML frontmatter parsing."""

from __future__ import annotations

import re

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def parse_boolean_text(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"true", "yes", "on", "enabled"}:
        return True
    if normalized in {"false", "no", "off", "disabled"}:
        return False
    return None


def parse_frontmatter(text: str) -> dict[str, object] | None:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None

    lines = match.group(1).splitlines()
    result: dict[str, object] = {}
    current_key: str | None = None
    current_mode: str | None = None

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key and current_mode == "list":
            result.setdefault(current_key, [])
            casted = result[current_key]
            if isinstance(casted, list):
                casted.append(line[4:].strip().strip('"').strip("'"))
            continue
        if line.startswith((" ", "\t")) and current_key and current_mode == "scalar":
            previous = str(result.get(current_key, "")).strip()
            continuation = line.strip()
            result[current_key] = f"{previous}\n{continuation}".strip()
            continue

        current_key = None
        current_mode = None
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if not value:
            result[key] = []
            current_mode = "list"
            continue
        scalar = value.strip('"').strip("'")
        boolean = parse_boolean_text(scalar)
        result[key] = boolean if boolean is not None else scalar
        current_mode = "scalar"

    return result
