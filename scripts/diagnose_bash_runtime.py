#!/usr/bin/env python3
"""Diagnose why a runnable bash executable is unavailable."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from sandbox_skill_invoke.core import (
    WINDOWS_BASH_BLACKLIST,
    WINDOWS_GIT_BASH_CANDIDATES,
    find_bash_executable,
)


def collect_candidates() -> list[dict[str, object]]:
    raw_candidates: list[tuple[str, str]] = []
    env_bash = os.environ.get("BASH")
    if env_bash:
        raw_candidates.append(("env:BASH", env_bash))

    if os.name == "nt":
        for path in WINDOWS_GIT_BASH_CANDIDATES:
            raw_candidates.append(("windows-default", str(path)))
        raw_candidates.append(("windows-system32", r"C:\Windows\System32\bash.exe"))

    which_bash = shutil.which("bash")
    if which_bash:
        raw_candidates.append(("PATH", which_bash))

    candidates: list[dict[str, object]] = []
    seen: set[str] = set()
    for source, raw_path in raw_candidates:
        normalized = str(Path(raw_path)).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        path = Path(normalized)
        entry: dict[str, object] = {
            "source": source,
            "path": normalized,
            "exists": path.exists(),
            "blacklisted": os.name == "nt" and normalized.lower() in WINDOWS_BASH_BLACKLIST,
            "usable": False,
            "returncode": None,
            "versionOutput": "",
        }
        if entry["exists"] and not entry["blacklisted"]:
            try:
                proc = subprocess.run(
                    [normalized, "--version"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                )
                combined = "\n".join(
                    part for part in (proc.stdout.strip(), proc.stderr.strip()) if part.strip()
                )
                entry["returncode"] = proc.returncode
                entry["versionOutput"] = combined[:400]
                entry["usable"] = proc.returncode == 0 and "bash" in combined.lower()
            except (OSError, subprocess.SubprocessError) as exc:
                entry["versionOutput"] = str(exc)
        candidates.append(entry)
    return candidates


def build_suggestions(candidates: list[dict[str, object]], selected: str | None) -> list[str]:
    if selected:
        return [
            f"Runnable bash already available: {selected}",
            "If validation still warns, rerun the command in the same terminal session so PATH and env vars match.",
        ]

    suggestions: list[str] = []
    if not candidates:
        return [
            "Install Git for Windows and make sure Git Bash is included.",
            "Expected working paths are usually `C:\\Program Files\\Git\\bin\\bash.exe` or `C:\\Program Files\\Git\\usr\\bin\\bash.exe`.",
            "Restart the terminal after installation so PATH changes take effect.",
        ]

    if any(bool(item.get("blacklisted")) for item in candidates):
        suggestions.append(
            "Do not rely on `C:\\Windows\\System32\\bash.exe`; this project intentionally rejects that legacy bash path."
        )

    existing = [item for item in candidates if bool(item.get("exists"))]
    if not existing:
        suggestions.append("Git Bash does not exist in the standard locations. Reinstall Git for Windows with Git Bash enabled.")
        return suggestions

    unusable = [item for item in existing if not bool(item.get("usable")) and not bool(item.get("blacklisted"))]
    if unusable:
        suggestions.append(
            "A bash executable exists but failed `bash --version`. Reinstall Git Bash or check endpoint security / ACL restrictions."
        )
        suggestions.append(
            "Test one candidate manually with `\"<path-to-bash>\" --version` outside Codex and confirm it prints a normal Bash version string."
        )

    if any(item.get("source") == "PATH" for item in candidates):
        suggestions.append(
            "If PATH resolves to the wrong bash first, prepend Git Bash to PATH or set the `BASH` environment variable to the correct executable."
        )
    else:
        suggestions.append(
            "If Git Bash is installed but not auto-detected, set the `BASH` environment variable to the full `bash.exe` path before running tests."
        )
    return suggestions


def build_report() -> dict[str, object]:
    candidates = collect_candidates()
    selected = find_bash_executable()
    return {
        "selectedBash": selected,
        "isRunnable": selected is not None,
        "os": os.name,
        "cwd": str(Path.cwd()),
        "candidates": candidates,
        "suggestions": build_suggestions(candidates, selected),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the full JSON report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print("Bash Runtime Diagnosis")
    print("=" * 40)
    print(f"Runnable: {'yes' if report['isRunnable'] else 'no'}")
    print(f"Selected: {report['selectedBash'] or '(none)'}")
    print("")
    print("Candidates:")
    if not report["candidates"]:
        print("- (none)")
    else:
        for item in report["candidates"]:
            print(f"- {item['source']}: {item['path']}")
            print(
                f"  exists={item['exists']} blacklisted={item['blacklisted']} usable={item['usable']}"
            )
            if item.get("returncode") is not None:
                print(f"  returncode={item['returncode']}")
            if item.get("versionOutput"):
                print(f"  version={item['versionOutput']}")
    print("")
    print("Suggestions:")
    for suggestion in report["suggestions"]:
        print(f"- {suggestion}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
