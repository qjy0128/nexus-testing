#!/usr/bin/env python3
"""Smoke tests for Flow A multi-source aggregation helpers."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import json
import shutil
import socketserver
import sys
import threading
from http.server import BaseHTTPRequestHandler

from run_flow_a_multi_source_execution import run_multi_source_probe
from test_helpers import assert_equal, make_temp_root


class _SourceHandler(BaseHTTPRequestHandler):
    payload: bytes = b"[]"

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class LocalServer:
    def __init__(self, items: list[dict[str, object]]) -> None:
        payload = json.dumps({"articles": items}, ensure_ascii=False).encode("utf-8")
        self.handler = type("SourceHandler", (_SourceHandler,), {"payload": payload})

    def __enter__(self) -> "LocalServer":
        self.server = socketserver.TCPServer(("127.0.0.1", 0), self.handler)
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/feed"

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def test_multi_source_probe_dedupes_items() -> None:
    temp_root = make_temp_root("flowa-multi-")
    try:
        items_a = [{"title": "News A", "url": "https://a/1"}, {"title": "News B", "url": "https://a/2"}]
        items_b = [{"title": "News B", "url": "https://b/2"}, {"title": "News C", "url": "https://b/3"}]
        with LocalServer(items_a) as server_a, LocalServer(items_b) as server_b:
            result = run_multi_source_probe(
                [server_a.url, server_b.url],
                min_sources_required=2,
                dedupe_key="title",
            )
            assert_equal(result["status"], "passed", "multi-source status")
            assert_equal(result["successSourceCount"], 2, "source success count")
            assert_equal(result["dedupedItemCount"], 3, "deduped item count")
        print("  [PASS] test_multi_source_probe_dedupes_items")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Flow A Multi-Source Smoke Tests")
    print("=" * 40)
    try:
        test_multi_source_probe_dedupes_items()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_multi_source_probe_dedupes_items: {exc}")
        failed += 1
    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
