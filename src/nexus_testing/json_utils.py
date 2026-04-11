#!/usr/bin/env python3
"""Shared JSON loading helpers with consistent error handling."""

from __future__ import annotations

import json
from pathlib import Path

from nexus_testing.sandbox_skill_invoke.core import read_text

_MISSING = object()


def load_json(path: Path, default: object = _MISSING, *, label: str | None = None) -> object:
    if not path.exists():
        if default is not _MISSING:
            return default
        raise SystemExit(f"ERROR: JSON file does not exist: {path}")
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        target = label or path.name
        raise SystemExit(f"ERROR: invalid JSON in {target}: {path} ({exc})") from exc
