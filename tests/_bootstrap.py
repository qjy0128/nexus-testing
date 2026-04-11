from __future__ import annotations

import sys
from pathlib import Path


def bootstrap_paths() -> tuple[Path, Path]:
    root = Path(__file__).resolve().parents[1]
    src_root = root / "src"
    scripts_root = root / "scripts"
    tests_root = root / "tests"
    for candidate in (root, src_root, scripts_root, tests_root):
        value = str(candidate)
        if value not in sys.path:
            sys.path.insert(0, value)
    return root, src_root
