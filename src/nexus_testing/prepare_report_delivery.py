#!/usr/bin/env python3
"""Mirror a generated report artifact into the workspace `files/` relay path."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nexus_testing.delivery.relay import mirror_report, resolve_input

ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = (ROOT / "memory" / "nexus-reports").resolve()


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
    source = resolve_input(ROOT, args.report_file)
    try:
        target, relay_relative = mirror_report(ROOT, REPORT_ROOT, source)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

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
