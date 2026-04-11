#!/usr/bin/env python3
"""Smoke tests for Flow A browser-backed execution helpers."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import shutil
import socketserver
import sys
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from run_flow_a_browser_execution import run_browser_probe
from test_helpers import assert_equal, make_temp_root

PROJECT_DIR = Path(__file__).resolve().parents[1]
MOCK_BROWSER = PROJECT_DIR / "scripts" / "fixtures" / "mock_browser_dump.py"


class _BrowserHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = b"<html><body><div id='app'>__INJECT_JS_RESULT__</div></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class LocalServer:
    def __enter__(self) -> "LocalServer":
        self.server = socketserver.TCPServer(("127.0.0.1", 0), _BrowserHandler)
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/page"

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def test_browser_probe_via_mock_command() -> None:
    temp_root = make_temp_root("flowa-browser-")
    try:
        with LocalServer() as server:
            result = run_browser_probe(
                server.url,
                ["bridge-browser"],
                browser_command=[sys.executable, str(MOCK_BROWSER)],
            )
            assert_equal(result["status"], "passed", "browser probe status")
            assert_equal("bridge-browser" in str(result.get("dom", "")), True, "rendered keyword present")
        print("  [PASS] test_browser_probe_via_mock_command")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Flow A Browser Execution Smoke Tests")
    print("=" * 40)
    try:
        test_browser_probe_via_mock_command()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_browser_probe_via_mock_command: {exc}")
        failed += 1
    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
