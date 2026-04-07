#!/usr/bin/env python3
"""Smoke tests for extract_product_fingerprint.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_helpers import assert_contains, assert_equal, make_temp_root, write_text

PROJECT_DIR = Path(__file__).resolve().parents[1]
EXTRACTOR = PROJECT_DIR / "scripts" / "extract_product_fingerprint.py"


def build_mixed_fixture(base_dir: Path) -> Path:
    repo_dir = base_dir / "mixed-target"
    (repo_dir / "skills" / "agentguard").mkdir(parents=True, exist_ok=True)
    (repo_dir / "scripts").mkdir(parents=True, exist_ok=True)

    write_text(
        repo_dir / "package.json",
        json.dumps(
            {
                "name": "@example/agentguard-lite",
                "version": "1.2.3",
                "license": "MIT",
                "bin": {"agentguard-lite": "./dist/mcp-server.js"},
                "engines": {"node": ">=18.0.0"},
                "openclaw": {"extensions": ["./dist/index.js"]},
                "dependencies": {"@modelcontextprotocol/sdk": "1.0.0"},
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
    )
    write_text(
        repo_dir / "openclaw.plugin.json",
        json.dumps({"name": "agentguard-lite-plugin"}, ensure_ascii=False, indent=2) + "\n",
    )
    write_text(
        repo_dir / "skills" / "agentguard" / "SKILL.md",
        "\n".join(
            [
                "---",
                "name: agentguard-lite",
                "description: Demo security skill.",
                "argument-hint: \"[scan|action|report] [args...]\"",
                "---",
                "",
                "# Demo Skill",
                "",
                "- **`scan <path>`** — scan a target path",
                "- **`action <description>`** — evaluate an action",
                "",
                "## Subcommand: report",
                "",
                "Generate a report.",
                "",
            ]
        ) + "\n",
    )
    write_text(repo_dir / "README.md", "# Demo\n")
    return repo_dir


def run_extractor(target: Path) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, str(EXTRACTOR), str(target)],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert_equal(proc.returncode, 0, "extractor exit code")
    return json.loads(proc.stdout)


def test_mixed_target() -> None:
    temp_root = make_temp_root("fingerprint-")
    try:
        repo_dir = build_mixed_fixture(temp_root)
        payload = run_extractor(repo_dir)

        assert_equal(payload.get("version", {}).get("value"), "1.2.3", "package version")
        assert_equal(payload.get("license", {}).get("value"), "MIT", "package license")
        assert_equal(payload.get("runtime"), ["node"], "runtime detection")

        product_type = payload.get("productType", [])
        for expected in ("skill", "package", "plugin", "cli", "mcp"):
            assert expected in product_type, f"missing product type {expected}: {product_type}"

        entry_surfaces = json.dumps(payload.get("entrySurfaces", []), ensure_ascii=False)
        assert_contains(entry_surfaces, "skills/agentguard/SKILL.md", "skill entry surface")
        assert_contains(entry_surfaces, "agentguard-lite", "cli/bin entry surface")

        capabilities = json.dumps(payload.get("capabilitySurfaces", []), ensure_ascii=False)
        assert_contains(capabilities, "scan", "scan capability")
        assert_contains(capabilities, "action", "action capability")
        assert_contains(capabilities, "report", "report capability")
        print("  [PASS] test_mixed_target")
    finally:
        import shutil

        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    tests = [test_mixed_target]
    passed = 0
    failed = 0

    print("Product Fingerprint Smoke Tests")
    print("=" * 40)
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as exc:
            print(f"  [FAIL] {test.__name__}: {exc}")
            failed += 1

    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
