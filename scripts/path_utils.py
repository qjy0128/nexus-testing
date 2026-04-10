#!/usr/bin/env python3
"""Shared repository path helpers."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def resolve_path(path_value: str) -> Path:
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        return (ROOT / candidate).resolve()
    return candidate.resolve()
