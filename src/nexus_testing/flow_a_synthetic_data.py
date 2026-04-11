#!/usr/bin/env python3
"""Synthetic dataset helpers for Flow A takeover execution."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def build_news_dataset(spec: dict[str, object]) -> dict[str, object]:
    record_count = max(1, int(spec.get("recordCount", 10)))
    duplicate_ratio = max(0.0, min(1.0, float(spec.get("duplicateRatio", 0.0))))
    duplicate_count = min(record_count, int(math.floor(record_count * duplicate_ratio)))
    languages = [str(item).strip() for item in spec.get("languages", ["zh-CN", "en"]) if str(item).strip()]
    if not languages:
        languages = ["zh-CN"]
    missing_fields = [str(item).strip() for item in spec.get("missingFields", []) if str(item).strip()]

    items: list[dict[str, object]] = []
    unique_count = max(1, record_count - duplicate_count)
    for index in range(unique_count):
        items.append(
            {
                "id": f"news-{index + 1:03d}",
                "title": f"Synthetic News {index + 1}",
                "summary": f"Synthetic summary {index + 1}",
                "url": f"https://synthetic.local/news/{index + 1}",
                "publishedAt": f"2026-04-10T{(index % 24):02d}:00:00Z",
                "language": languages[index % len(languages)],
                "source": f"synthetic-source-{(index % 9) + 1}",
            }
        )
    for index in range(duplicate_count):
        items.append(dict(items[index % len(items)]))
    items = items[:record_count]

    for item_index, field in enumerate(missing_fields):
        if item_index >= len(items):
            break
        items[item_index].pop(field, None)

    return {
        "kind": "news-feed",
        "recordCount": len(items),
        "duplicateRatio": duplicate_ratio,
        "duplicateCount": duplicate_count,
        "missingFields": missing_fields,
        "items": items,
    }


def build_dataset(spec: dict[str, object]) -> dict[str, object]:
    kind = str(spec.get("kind", "news-feed"))
    if kind == "news-feed":
        return build_news_dataset(spec)
    raise ValueError(f"unsupported synthetic dataset kind: {kind}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec-json", required=True)
    parser.add_argument("--output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    spec = json.loads(args.spec_json)
    if not isinstance(spec, dict):
        raise SystemExit("ERROR: --spec-json must decode to an object")
    dataset = build_dataset(spec)
    output = str(args.output or "").strip()
    if output:
        Path(output).write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dataset, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
