from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
SCRIPTS_ROOT = ROOT / "scripts"
TESTS_ROOT = ROOT / "tests"

for candidate in (SRC_ROOT, SCRIPTS_ROOT, TESTS_ROOT):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)
