"""Shared test utilities: session creation, assertions, I/O helpers."""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

from sandbox_skill_invoke.core import find_bash_executable

TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".tmp-test-runs"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def parse_kv_output(output: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: expected to find {needle!r} in {text!r}")


def make_temp_root(prefix: str) -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    for attempt in range(20):
        candidate = TEST_TMP_ROOT / f"{prefix}{Path.cwd().name}-{time.time_ns()}-{attempt}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"unable to allocate temp root under {TEST_TMP_ROOT}")


def find_runnable_bash() -> str | None:
    return find_bash_executable()


def create_session(
    sandbox_root: Path,
    session_id: str,
    extra_dirs: tuple[str, ...] = (),
) -> Path:
    """Create a sandbox session directory with standard structure.

    Parameters
    ----------
    sandbox_root : Path
        Root directory for all sandbox sessions.
    session_id : str
        Unique session identifier.
    extra_dirs : tuple[str, ...]
        Additional directories to create under the session workspace
        (e.g. ``("workspace/skills",)`` for integration tests).
    """
    session_dir = sandbox_root / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir)
    standard_dirs = (
        "workspace/fixtures",
        "workspace/outputs",
        "workspace/temp",
        "workspace/state",
        "workspace/artifacts",
        "runtime",
        "logs",
    )
    for relative in standard_dirs + extra_dirs:
        (session_dir / relative).mkdir(parents=True, exist_ok=True)
    write_text(session_dir / "logs" / "exit-codes.json", "[]\n")
    write_text(session_dir / "logs" / "file-ops.json", "[]\n")
    write_text(
        session_dir / "META.json",
        json.dumps(
            {
                "sessionId": session_id,
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                "status": "active",
                "platform": sys.platform,
                "runtime": {"python": sys.version.split()[0], "node": ""},
                "capabilities": "full",
                "parentTestReport": None,
                "commandCount": 0,
                "totalDurationMs": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return session_dir
