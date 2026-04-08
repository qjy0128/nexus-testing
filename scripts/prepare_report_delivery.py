#!/usr/bin/env python3
"""Mirror a generated report artifact into the workspace `files/` relay path."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = (ROOT / "memory" / "nexus-reports").resolve()
FILES_ROOT = ROOT / "files"


def resolve_input(path_value: str) -> Path:
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        candidate = (ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def build_target_path(source: Path) -> tuple[Path, str]:
    if REPORT_ROOT in source.parents:
        relative = source.relative_to(REPORT_ROOT)
        relay_relative = Path("files") / "nexus-reports" / relative
    elif ROOT in source.parents:
        relative = source.relative_to(ROOT)
        relay_relative = Path("files") / relative
    else:
        raise SystemExit(
            f"ERROR: report file must stay under the workspace root: {source}"
        )
    return ROOT / relay_relative, relay_relative.as_posix()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-file",
        required=True,
        help="Path to a generated report artifact under the workspace.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    source = resolve_input(args.report_file)
    if not source.exists():
        raise SystemExit(f"ERROR: report file does not exist: {source}")
    if not source.is_file():
        raise SystemExit(f"ERROR: report file must be a file: {source}")

    target, relay_relative = build_target_path(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

    try:
        source_relative = source.relative_to(ROOT).as_posix()
    except ValueError:
        source_relative = str(source)

    print(f"SOURCE_PATH={source_relative}")
    print(f"SENDABLE_PATH={relay_relative}")
    print(f"SENDABLE_ABS={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
