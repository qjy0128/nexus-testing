#!/usr/bin/env python3
"""E2E smoke test: sandbox lifecycle with fixture skills.

Tests the full create → invoke → cleanup cycle using the fixture-pass-skill.
Runs in trace/dry-run mode since no OpenClaw CLI is available in CI.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from test_helpers import find_runnable_bash, make_temp_root

PROJECT_DIR = Path(__file__).resolve().parents[1]
FIXTURE_PASS = PROJECT_DIR / "scripts" / "fixtures" / "fixture-pass-skill"
FIXTURE_DEFECT = PROJECT_DIR / "scripts" / "fixtures" / "fixture-defect-skill"
SANDBOX_CREATE = PROJECT_DIR / "scripts" / "sandbox-create.sh"
SANDBOX_CLEANUP = PROJECT_DIR / "scripts" / "sandbox-cleanup.sh"
INVOKE_SCRIPT = PROJECT_DIR / "scripts" / "sandbox_skill_invoke.py"
SECURITY_SCANNER = PROJECT_DIR / "scripts" / "security-scanner.py"


class SkipTest(Exception):
    """Raised by a test to indicate it should be skipped."""


def run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def test_security_scanner_pass_skill() -> None:
    """Security scanner should report SAFE for the pass fixture."""
    proc = run([sys.executable, str(SECURITY_SCANNER), str(FIXTURE_PASS), "--format", "json"])
    assert proc.returncode == 0, f"pass-skill should be SAFE, got exit {proc.returncode}: {proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["verdict"] == "SAFE", f"Expected SAFE, got {data['verdict']}"
    assert data["total_findings"] == 0, f"Expected 0 findings, got {data['total_findings']}"
    print("  [PASS] security_scanner_pass_skill")


def test_security_scanner_defect_skill() -> None:
    """Security scanner should report CRITICAL for the defect fixture."""
    proc = run([sys.executable, str(SECURITY_SCANNER), str(FIXTURE_DEFECT), "--format", "json"])
    assert proc.returncode != 0, f"defect-skill should be CRITICAL, got exit {proc.returncode}"
    data = json.loads(proc.stdout)
    assert data["verdict"] in ("CRITICAL", "UNSAFE"), f"Expected CRITICAL/UNSAFE, got {data['verdict']}"
    assert data["total_findings"] >= 5, f"Expected >= 5 findings, got {data['total_findings']}"
    print("  [PASS] security_scanner_defect_skill")


def test_sandbox_create_cleanup_cycle() -> None:
    """Test sandbox create and cleanup lifecycle."""
    bash = find_runnable_bash()
    if not bash:
        raise SkipTest("sandbox_create_cleanup (no runnable bash)")

    session_id = f"test-{int(time.time())}-abc123"
    sandbox_root = make_temp_root("nexus-e2e-")

    try:
        # Create
        proc = run([bash, str(SANDBOX_CREATE), "--session-id", session_id, "--sandbox-root", str(sandbox_root)])
        assert proc.returncode == 0, f"sandbox-create failed: {proc.stderr}"
        session_dir = sandbox_root / session_id
        assert session_dir.exists(), "Session directory not created"
        assert (session_dir / "META.json").exists(), "META.json not created"

        meta = json.loads((session_dir / "META.json").read_text())
        assert meta.get("sessionId") == session_id, f"Session ID mismatch: {meta}"
        print("  [PASS] sandbox_create")

        # Verify directory structure
        for subdir in ("workspace", "workspace/fixtures", "workspace/outputs",
                        "workspace/temp", "workspace/state", "workspace/artifacts",
                        "runtime", "logs"):
            assert (session_dir / subdir).exists(), f"Missing subdir: {subdir}"
        print("  [PASS] sandbox_directory_structure")

        # Cleanup
        proc = run([bash, str(SANDBOX_CLEANUP), "--session-id", session_id, "--sandbox-root", str(sandbox_root), "--force"])
        assert proc.returncode == 0, f"sandbox-cleanup failed: {proc.stderr}"
        assert not session_dir.exists(), "Session directory still exists after cleanup"
        print("  [PASS] sandbox_cleanup")

    finally:
        shutil.rmtree(sandbox_root, ignore_errors=True)


def test_skill_invoke_trace_mode() -> None:
    """Test sandbox-skill-invoke in trace mode with pass fixture."""
    bash = find_runnable_bash()
    if not bash:
        raise SkipTest("skill_invoke_trace (no runnable bash)")

    session_id = f"test-{int(time.time())}-trace01"
    sandbox_root = make_temp_root("nexus-e2e-")

    try:
        # Create session first
        create_proc = run([bash, str(SANDBOX_CREATE), "--session-id", session_id, "--sandbox-root", str(sandbox_root)])
        assert create_proc.returncode == 0, f"sandbox-create failed: {create_proc.stderr}\n{create_proc.stdout}"

        # Invoke in trace mode
        proc = run([
            sys.executable, str(INVOKE_SCRIPT),
            "--session-id", session_id,
            "--skill-path", str(FIXTURE_PASS),
            "--message", "Convert 5 km to miles",
            "--channel", "telegram",
            "--mode", "trace",
            "--sandbox-root", str(sandbox_root),
        ], timeout=30)

        assert proc.returncode == 0, f"trace invoke failed (exit {proc.returncode}): {proc.stderr}\n{proc.stdout}"
        assert "EXECUTION_LEVEL=trace" in proc.stdout, f"Missing EXECUTION_LEVEL=trace in output:\n{proc.stdout}"
        assert "REAL_EXECUTED=false" in proc.stdout, "REAL_EXECUTED should be false for trace"
        print("  [PASS] skill_invoke_trace_mode")

    finally:
        run([bash, str(SANDBOX_CLEANUP), "--session-id", session_id, "--sandbox-root", str(sandbox_root)], timeout=10)
        shutil.rmtree(sandbox_root, ignore_errors=True)


def test_skill_invoke_dry_run_mode() -> None:
    """Test sandbox-skill-invoke in dry-run mode."""
    bash = find_runnable_bash()
    if not bash:
        raise SkipTest("skill_invoke_dry_run (no runnable bash)")

    session_id = f"test-{int(time.time())}-dry01"
    sandbox_root = make_temp_root("nexus-e2e-")

    try:
        create_proc = run([bash, str(SANDBOX_CREATE), "--session-id", session_id, "--sandbox-root", str(sandbox_root)])
        assert create_proc.returncode == 0, f"sandbox-create failed: {create_proc.stderr}\n{create_proc.stdout}"

        proc = run([
            sys.executable, str(INVOKE_SCRIPT),
            "--session-id", session_id,
            "--skill-path", str(FIXTURE_PASS),
            "--channel", "telegram",
            "--mode", "dry-run",
            "--sandbox-root", str(sandbox_root),
        ], timeout=30)

        assert proc.returncode == 0, f"dry-run failed (exit {proc.returncode}): {proc.stderr}\n{proc.stdout}"
        assert "SELECTED_MODE=dry-run" in proc.stdout or "EXECUTION_LEVEL=dry-run" in proc.stdout, \
            f"Missing dry-run output:\n{proc.stdout}"
        print("  [PASS] skill_invoke_dry_run_mode")

    finally:
        run([bash, str(SANDBOX_CLEANUP), "--session-id", session_id, "--sandbox-root", str(sandbox_root)], timeout=10)
        shutil.rmtree(sandbox_root, ignore_errors=True)


def test_fixture_pass_skill_structure() -> None:
    """Verify fixture-pass-skill has valid SKILL.md structure."""
    skill_md = FIXTURE_PASS / "SKILL.md"
    assert skill_md.exists(), "fixture-pass-skill SKILL.md missing"

    content = skill_md.read_text(encoding="utf-8")
    assert content.strip().startswith("---"), "Missing frontmatter"
    assert "name:" in content, "Missing name field"
    assert "description:" in content, "Missing description field"
    print("  [PASS] fixture_pass_skill_structure")


def test_fixture_defect_skill_structure() -> None:
    """Verify fixture-defect-skill contains intentional defects."""
    skill_md = FIXTURE_DEFECT / "SKILL.md"
    assert skill_md.exists(), "fixture-defect-skill SKILL.md missing"

    content = skill_md.read_text(encoding="utf-8")
    # Should contain at least eval and API_KEY
    assert "eval(" in content, "Missing eval() defect"
    assert "API_KEY" in content, "Missing API_KEY defect"
    assert "curl" in content and "| bash" in content, "Missing curl|bash defect"
    print("  [PASS] fixture_defect_skill_structure")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    tests = [
        test_fixture_pass_skill_structure,
        test_fixture_defect_skill_structure,
        test_security_scanner_pass_skill,
        test_security_scanner_defect_skill,
        test_sandbox_create_cleanup_cycle,
        test_skill_invoke_trace_mode,
        test_skill_invoke_dry_run_mode,
    ]

    passed = 0
    failed = 0
    skipped = 0

    print("Sandbox Lifecycle E2E Tests")
    print("=" * 40)

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as exc:
            print(f"  [FAIL] {test.__name__}: {exc}")
            failed += 1
        except SkipTest as exc:
            print(f"  [SKIP] {test.__name__}: {exc}")
            skipped += 1
        except Exception as exc:
            print(f"  [ERROR] {test.__name__}: {type(exc).__name__}: {exc}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
