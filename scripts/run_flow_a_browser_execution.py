#!/usr/bin/env python3
"""Browser-backed takeover probes for Flow A dynamic pages."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path


def detect_browser_command() -> list[str] | None:
    env_command = str(os.environ.get("NEXUS_BROWSER_DUMP_COMMAND", "")).strip()
    if env_command:
        if env_command.startswith("["):
            try:
                parsed = json.loads(env_command)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list) and all(str(item).strip() for item in parsed):
                return [str(item) for item in parsed]
        return shlex.split(env_command, posix=False)
    candidates = (
        "msedge",
        "msedge.exe",
        "microsoft-edge",
        "chrome",
        "chrome.exe",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    )
    for name in candidates:
        resolved = shutil.which(name)
        if resolved:
            return [resolved, "--headless", "--disable-gpu", "--dump-dom", "--virtual-time-budget=10000"]
    return None


def run_browser_probe(
    url: str,
    expected_keywords: list[str],
    *,
    browser_command: list[str] | None = None,
    timeout_seconds: int = 20,
) -> dict[str, object]:
    command = list(browser_command or detect_browser_command() or [])
    if not command:
        return {"status": "unsupported", "note": "no browser command available", "dom": ""}
    command.append(url)
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "note": f"{type(exc).__name__}: {exc}", "dom": ""}

    if proc.returncode != 0:
        return {
            "status": "failed",
            "note": f"browser exit={proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}",
            "dom": proc.stdout,
        }
    dom = proc.stdout
    lowered = dom.lower()
    missing = [item for item in expected_keywords if item.lower() not in lowered]
    return {
        "status": "passed" if not missing else "blocked",
        "note": "browser-rendered-dom" if not missing else f"missing rendered keywords: {', '.join(missing)}",
        "dom": dom,
        "keywordHits": [item for item in expected_keywords if item.lower() in lowered],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--expected-keyword", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--browser-command")
    parser.add_argument("--dom-output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    browser_command = shlex.split(args.browser_command, posix=False) if args.browser_command else None
    result = run_browser_probe(
        args.url,
        [str(item) for item in args.expected_keyword],
        browser_command=browser_command,
        timeout_seconds=int(args.timeout_seconds),
    )
    dom_output = str(args.dom_output or "").strip()
    if dom_output:
        Path(dom_output).write_text(str(result.get("dom", "")), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "dom"}, ensure_ascii=False))
    return 0 if str(result.get("status")) in {"passed", "blocked", "unsupported"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
