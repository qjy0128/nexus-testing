#!/usr/bin/env python3
"""Smoke tests for Flow A synthetic dataset helpers."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import shutil
import sys

from test_helpers import assert_equal, make_temp_root

from nexus_testing.flow_a_synthetic_data import build_dataset


def test_build_news_dataset() -> None:
    temp_root = make_temp_root("flowa-synth-")
    try:
        dataset = build_dataset(
            {
                "enabled": True,
                "kind": "news-feed",
                "recordCount": 110,
                "duplicateRatio": 0.1,
                "languages": ["zh-CN", "en"],
                "missingFields": ["summary"],
            }
        )
        assert_equal(dataset["kind"], "news-feed", "dataset kind")
        assert_equal(dataset["recordCount"], 110, "record count")
        assert_equal(len(dataset["items"]), 110, "item count")
        missing_summary = sum(1 for item in dataset["items"] if "summary" not in item)
        assert_equal(missing_summary >= 1, True, "missing field injection")
        print("  [PASS] test_build_news_dataset")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Flow A Synthetic Dataset Smoke Tests")
    print("=" * 40)
    try:
        test_build_news_dataset()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_build_news_dataset: {exc}")
        failed += 1
    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
