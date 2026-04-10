#!/usr/bin/env python3
"""Mock browser dump command for browser takeover smoke tests."""

from __future__ import annotations

import sys
import urllib.request


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if not args:
        raise SystemExit("usage: mock_browser_dump.py <url>")
    url = args[-1]
    with urllib.request.urlopen(url, timeout=10) as response:
        html = response.read().decode("utf-8", errors="replace")
    html = html.replace("__INJECT_JS_RESULT__", "bridge-browser")
    sys.stdout.write(html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
