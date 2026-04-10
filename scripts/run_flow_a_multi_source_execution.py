#!/usr/bin/env python3
"""Multi-source aggregation helpers for Flow A takeover execution."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def fetch_json(url: str, timeout: float) -> tuple[bool, object, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "nexus-testing-multi-source/0.9.44",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return False, None, f"http-{exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, None, f"{type(exc).__name__}: {exc}"
    try:
        return True, json.loads(body), "ok"
    except json.JSONDecodeError:
        return True, body, "text"


def extract_items(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("articles", "items", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def dedupe_items(items: list[dict[str, object]], dedupe_key: str) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.get(dedupe_key, "")).strip()
        if not key:
            key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def run_multi_source_probe(
    urls: list[str],
    *,
    min_sources_required: int = 2,
    dedupe_key: str = "title",
    timeout_seconds: float = 8.0,
) -> dict[str, object]:
    per_source: list[dict[str, object]] = []
    aggregated: list[dict[str, object]] = []
    success_count = 0
    for url in urls:
        ok, payload, note = fetch_json(url, timeout_seconds)
        items = extract_items(payload)
        if ok and items:
            success_count += 1
            aggregated.extend(items)
        per_source.append(
            {
                "url": url,
                "ok": ok,
                "note": note,
                "itemCount": len(items),
            }
        )
    deduped = dedupe_items(aggregated, dedupe_key)
    status = "passed" if success_count >= max(1, min_sources_required) and deduped else "blocked"
    return {
        "status": status,
        "sourceCount": len(urls),
        "successSourceCount": success_count,
        "dedupeKey": dedupe_key,
        "dedupedItemCount": len(deduped),
        "items": deduped,
        "sources": per_source,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", action="append", default=[])
    parser.add_argument("--min-sources-required", type=int, default=2)
    parser.add_argument("--dedupe-key", default="title")
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_multi_source_probe(
        [str(item) for item in args.url if str(item).strip()],
        min_sources_required=int(args.min_sources_required),
        dedupe_key=str(args.dedupe_key),
        timeout_seconds=float(args.timeout_seconds),
    )
    output = str(args.output or "").strip()
    if output:
        Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if str(result.get("status")) in {"passed", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
