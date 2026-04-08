#!/usr/bin/env python3
"""Shared output-language helpers for Flow A generators and runners."""

from __future__ import annotations

import argparse
import os

SUPPORTED_LANGUAGES = ("zh-CN", "en")
_LANGUAGE_ALIASES = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh_hans": "zh-CN",
    "chinese": "zh-CN",
    "cn": "zh-CN",
    "en": "en",
    "en-us": "en",
    "english": "en",
}


def normalize_language(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        raw = os.environ.get("NEXUS_OUTPUT_LANGUAGE", "zh-CN").strip()
    normalized = _LANGUAGE_ALIASES.get(raw.lower(), raw)
    if normalized not in SUPPORTED_LANGUAGES:
        supported = ", ".join(SUPPORTED_LANGUAGES)
        raise ValueError(f"unsupported language: {value!r}; expected one of {supported}")
    return normalized


def argparse_language(value: str) -> str:
    try:
        return normalize_language(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def default_output_language() -> str:
    return normalize_language(os.environ.get("NEXUS_OUTPUT_LANGUAGE", "zh-CN"))


def add_output_language_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--language",
        default=default_output_language(),
        type=argparse_language,
        help="Output language for descriptive content (`zh-CN` or `en`).",
    )
