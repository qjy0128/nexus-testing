#!/usr/bin/env python3
"""E2E integration tests for sandbox_skill_invoke.py covering critical paths.

Covers: auto-mode trace fallback, non-strict shim-live, adapter failure,
strict verifier flow, dry-run mode, source refresh, and link hardening.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from sandbox_skill_invoke.core import find_bash_executable

ROOT = Path(__file__).resolve().parents[1]
INVOKE_SCRIPT = ROOT / "scripts" / "sandbox_skill_invoke.py"
SANDBOX_EXEC_SCRIPT = ROOT / "scripts" / "sandbox-exec.sh"
TEST_TMP_ROOT = ROOT / ".tmp-test-runs"


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


def create_session(sandbox_root: Path, session_id: str) -> Path:
    session_dir = sandbox_root / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir)
    for relative in (
        "workspace/fixtures",
        "workspace/outputs",
        "workspace/temp",
        "workspace/state",
        "workspace/artifacts",
        "workspace/skills",
        "runtime",
        "logs",
    ):
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


def run_invoke(args: list[str], env: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    proc = subprocess.run(
        [sys.executable, str(INVOKE_SCRIPT)] + args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return proc, parse_kv_output(proc.stdout)


def make_temp_root(prefix: str) -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    for attempt in range(20):
        candidate = TEST_TMP_ROOT / f"{prefix}{os.getpid()}-{time.time_ns()}-{attempt}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"unable to allocate temp root under {TEST_TMP_ROOT}")


def build_minimal_skill(base_dir: Path, *, adapter_body: str | None = None) -> Path:
    """Create a minimal skill with optional adapter script."""
    skill_dir = base_dir / "minimal-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    
    # Create fake .git directories to simulate separate repositories
    (skill_dir / ".git").mkdir(parents=True, exist_ok=True)

    write_text(
        skill_dir / "SKILL.md",
        "\n".join([
            "---",
            "name: Integration Test Skill",
            "description: Minimal skill for E2E integration tests",
            "---",
            "",
            "# Integration Test Skill",
            "",
            "## Trigger",
            "- Respond to messages containing test keywords",
            "- Handle greeting messages",
            "",
            "allowed_tools:",
            "  - echo_tool",
            "",
            "## Description",
            "A minimal skill used by integration tests.",
            "",
        ]) + "\n",
    )

    if adapter_body is not None:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        write_text(scripts_dir / "test-entry.py", adapter_body)

    return skill_dir


def build_success_adapter() -> str:
    """Return adapter script body that writes a successful result."""
    return "\n".join([
        "#!/usr/bin/env python3",
        "from __future__ import annotations",
        "",
        "import json",
        "import os",
        "from pathlib import Path",
        "",
        "message = os.environ.get('NEXUS_MESSAGE', '')",
        "output_file = Path(os.environ['NEXUS_OUTPUT_FILE'])",
        "result_file = Path(os.environ['NEXUS_RESULT_JSON_FILE'])",
        "artifacts_dir = Path(os.environ['NEXUS_ARTIFACTS_DIR'])",
        "artifacts_dir.mkdir(parents=True, exist_ok=True)",
        "proof_file = artifacts_dir / 'proof.txt'",
        "proof_file.write_text('delivered\\n', encoding='utf-8')",
        "payload = {",
        "    'triggerMatched': True,",
        "    'toolsCalled': ['echo_tool'],",
        "    'contextReferences': [],",
        "    'assistantMessage': f'Handled: {message}',",
        "    'deliveryStatus': 'delivered',",
        "    'deliveryReceipts': ['receipt-integration-001'],",
        "    'deliveryEvidence': [str(proof_file)],",
        "}",
        "output_file.parent.mkdir(parents=True, exist_ok=True)",
        "output_file.write_text(payload['assistantMessage'] + '\\n', encoding='utf-8')",
        "result_file.parent.mkdir(parents=True, exist_ok=True)",
        "result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')",
        "",
    ])


def build_dist_version_adapter() -> str:
    """Return adapter body that reads dist/version.txt from the copied skill."""
    return "\n".join([
        "#!/usr/bin/env python3",
        "from __future__ import annotations",
        "",
        "import json",
        "import os",
        "from pathlib import Path",
        "",
        "skill_root = Path(__file__).resolve().parents[1]",
        "version = (skill_root / 'dist' / 'version.txt').read_text(encoding='utf-8-sig').strip()",
        "output_file = Path(os.environ['NEXUS_OUTPUT_FILE'])",
        "result_file = Path(os.environ['NEXUS_RESULT_JSON_FILE'])",
        "payload = {",
        "    'triggerMatched': True,",
        "    'toolsCalled': ['echo_tool'],",
        "    'contextReferences': [],",
        "    'assistantMessage': f'Dist version: {version}',",
        "    'deliveryStatus': 'delivered',",
        "    'deliveryReceipts': ['receipt-dist-version'],",
        "    'deliveryEvidence': [],",
        "}",
        "output_file.parent.mkdir(parents=True, exist_ok=True)",
        "output_file.write_text(payload['assistantMessage'] + '\\n', encoding='utf-8')",
        "result_file.parent.mkdir(parents=True, exist_ok=True)",
        "result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')",
        "",
    ])


def build_versioned_skill(base_dir: Path, version: str) -> Path:
    """Create a skill whose runtime behavior depends on dist/version.txt."""
    skill_dir = build_minimal_skill(base_dir, adapter_body=build_dist_version_adapter())
    write_text(skill_dir / "dist" / "version.txt", f"{version}\n")
    return skill_dir


def build_fail_adapter() -> str:
    """Return adapter script body that exits with code 1."""
    return "\n".join([
        "#!/usr/bin/env python3",
        "from __future__ import annotations",
        "import sys",
        "",
        "print('adapter failed intentionally', file=sys.stderr)",
        "raise SystemExit(1)",
        "",
    ])


def build_verifier(base_dir: Path) -> Path:
    """Create an independent verifier that echoes the adapter result."""
    verifier_dir = base_dir / "independent-verifier"
    verifier_dir.mkdir(parents=True, exist_ok=True)
    
    # Create fake .git directories to simulate separate repositories
    (verifier_dir / ".git").mkdir(parents=True, exist_ok=True)

    write_text(
        verifier_dir / "verify.py",
        "\n".join([
            "#!/usr/bin/env python3",
            "from __future__ import annotations",
            "",
            "import json",
            "import os",
            "from pathlib import Path",
            "",
            "adapter_result = Path(os.environ['NEXUS_ADAPTER_RESULT_JSON_FILE'])",
            "verifier_result = Path(os.environ['NEXUS_VERIFIER_RESULT_FILE'])",
            "payload = json.loads(adapter_result.read_text(encoding='utf-8-sig'))",
            "verified = {",
            "    'triggerMatched': payload.get('triggerMatched'),",
            "    'toolsCalled': payload.get('toolsCalled', []),",
            "    'contextReferences': payload.get('contextReferences', []),",
            "    'assistantMessage': payload.get('assistantMessage', ''),",
            "    'deliveryStatus': payload.get('deliveryStatus', 'unknown'),",
            "    'deliveryReceipts': payload.get('deliveryReceipts', []),",
            "    'deliveryEvidence': payload.get('deliveryEvidence', []),",
            "    'notes': ['integration-verifier'],",
            "}",
            "verifier_result.parent.mkdir(parents=True, exist_ok=True)",
            "verifier_result.write_text(json.dumps(verified, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')",
            "",
        ]),
    )

    python_cmd = shlex.quote(Path(sys.executable).as_posix())
    verifier_cmd = f"{python_cmd} verify.py"
    write_text(
        verifier_dir / "verifier.json",
        json.dumps(
            {"verify": {"command": verifier_cmd, "cwd": ".", "timeoutSeconds": 30}},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
    )
    return verifier_dir / "verifier.json"


def create_escape_link(skill_dir: Path, outside_dir: Path) -> str:
    """Create a symlink or junction that points outside the skill root."""
    outside_dir.mkdir(parents=True, exist_ok=True)
    write_text(outside_dir / "secret.txt", "outside-secret\n")

    file_link = skill_dir / "linked-secret.txt"
    try:
        os.symlink(outside_dir / "secret.txt", file_link)
        return file_link.name
    except (AttributeError, NotImplementedError, OSError):
        pass

    dir_link = skill_dir / "linked-dir"
    if os.name == "nt":
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(dir_link), str(outside_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0:
            return dir_link.name
    else:
        try:
            os.symlink(outside_dir, dir_link, target_is_directory=True)
            return dir_link.name
        except (NotImplementedError, OSError):
            pass

    raise RuntimeError("environment cannot create a test symlink or junction")


def main() -> int:
    temp_root = make_temp_root("nexus-e2e-integration-")
    try:
        sandbox_root = temp_root / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        bash_available = find_bash_executable() is not None

        passed = 0
        failed = 0
        skipped = 0

        # ── Test 1: auto mode trace fallback (no adapter, no openclaw) ──
        create_session(sandbox_root, "e2e-trace-fallback")
        skill_no_adapter = build_minimal_skill(temp_root / "t1")
        proc, kv = run_invoke([
            "--session-id", "e2e-trace-fallback",
            "--skill-path", str(skill_no_adapter),
            "--message", "hello test",
            "--channel", "telegram",
            "--mode", "auto",
            "--sandbox-root", str(sandbox_root),
        ], env)
        try:
            assert_equal(proc.returncode, 0, "trace-fallback return code")
            assert_equal(kv.get("SELECTED_MODE"), "trace", "trace-fallback selected mode")
            assert_equal(kv.get("EXECUTION_LEVEL"), "trace", "trace-fallback execution level")
            assert_equal(kv.get("REAL_EXECUTED"), "false", "trace-fallback real executed")
            assert_equal(kv.get("INVOKE_STATUS"), "trace-complete", "trace-fallback status")
            passed += 1
            print("[PASS] 1: auto mode trace fallback")
        except AssertionError as exc:
            failed += 1
            print(f"[FAIL] 1: auto mode trace fallback: {exc}")

        # ── Test 2: dry-run mode ──
        create_session(sandbox_root, "e2e-dry-run")
        skill_dry = build_minimal_skill(temp_root / "t2", adapter_body=build_success_adapter())
        proc, kv = run_invoke([
            "--session-id", "e2e-dry-run",
            "--skill-path", str(skill_dry),
            "--message", "dry run test",
            "--channel", "telegram",
            "--mode", "dry-run",
            "--sandbox-root", str(sandbox_root),
        ], env)
        try:
            assert_equal(proc.returncode, 0, "dry-run return code")
            assert_equal(kv.get("SELECTED_MODE"), "dry-run", "dry-run selected mode")
            assert_equal(kv.get("EXECUTION_LEVEL"), "dry-run", "dry-run execution level")
            assert_equal(kv.get("REAL_EXECUTED"), "false", "dry-run real executed")
            assert_equal(kv.get("INVOKE_STATUS"), "dry-run-complete", "dry-run status")
            assert_equal(kv.get("ADAPTER_AVAILABLE"), "true", "dry-run adapter available")
            passed += 1
            print("[PASS] 2: dry-run mode")
        except AssertionError as exc:
            failed += 1
            print(f"[FAIL] 2: dry-run mode: {exc}")

        if not bash_available:
            skipped += 6
            print("[SKIP] 3-5,7-9: shim-live integration checks require runnable bash")
        else:
            # ── Test 3: shim-live non-strict (no verifier needed) ──
            create_session(sandbox_root, "e2e-shim-non-strict")
            skill_shim = build_minimal_skill(temp_root / "t3", adapter_body=build_success_adapter())
            proc, kv = run_invoke([
                "--session-id", "e2e-shim-non-strict",
                "--skill-path", str(skill_shim),
                "--message", "shim non strict",
                "--channel", "telegram",
                "--mode", "shim-live",
                "--sandbox-root", str(sandbox_root),
            ], env)
            try:
                assert_equal(proc.returncode, 0, "shim-non-strict return code")
                assert_equal(kv.get("SELECTED_MODE"), "shim-live", "shim-non-strict selected mode")
                assert_equal(kv.get("EXECUTION_LEVEL"), "shim-live", "shim-non-strict execution level")
                assert_equal(kv.get("REAL_EXECUTED"), "true", "shim-non-strict real executed")
                assert_equal(kv.get("INVOKE_STATUS"), "success", "shim-non-strict status")
                assert_equal(kv.get("TELEMETRY_TRUST"), "self-reported", "shim-non-strict telemetry trust")
                assert_equal(kv.get("VERIFICATION_STATUS"), "not-configured", "shim-non-strict verification status")
                output_file = Path(kv["OUTPUT_FILE"])
                assert_contains(read_text(output_file), "Handled: shim non strict", "shim-non-strict output")
                passed += 1
                print("[PASS] 3: shim-live non-strict")
            except AssertionError as exc:
                failed += 1
                print(f"[FAIL] 3: shim-live non-strict: {exc}")

            # ── Test 4: shim-live adapter failure ──
            create_session(sandbox_root, "e2e-adapter-fail")
            skill_fail = build_minimal_skill(temp_root / "t4", adapter_body=build_fail_adapter())
            proc, kv = run_invoke([
                "--session-id", "e2e-adapter-fail",
                "--skill-path", str(skill_fail),
                "--message", "trigger adapter failure",
                "--channel", "telegram",
                "--mode", "shim-live",
                "--sandbox-root", str(sandbox_root),
            ], env)
            try:
                assert_equal(proc.returncode, 2, "adapter-fail return code")
                assert_equal(kv.get("INVOKE_STATUS"), "blocked-invoke-failed", "adapter-fail status")
                assert_contains(
                    kv.get("BLOCKER_REASON", ""),
                    "adapter exited with code 1",
                    "adapter-fail blocker reason",
                )
                passed += 1
                print("[PASS] 4: shim-live adapter failure")
            except AssertionError as exc:
                failed += 1
                print(f"[FAIL] 4: shim-live adapter failure: {exc}")

            # ── Test 5: shim-live with verifier (full strict path) ──
            create_session(sandbox_root, "e2e-with-verifier")
            skill_verified = build_minimal_skill(temp_root / "t5", adapter_body=build_success_adapter())
            verifier_manifest = build_verifier(temp_root / "t5-ext")
            proc, kv = run_invoke([
                "--session-id", "e2e-with-verifier",
                "--skill-path", str(skill_verified),
                "--message", "verify me",
                "--channel", "telegram",
                "--mode", "shim-live",
                "--strict-real",
                "--verification-manifest", str(verifier_manifest),
                "--expect-trigger", "true",
                "--require-tools", "echo_tool",
                "--require-delivery-status", "delivered",
                "--sandbox-root", str(sandbox_root),
            ], env)
            try:
                assert_equal(proc.returncode, 0, "with-verifier return code")
                assert_equal(kv.get("INVOKE_STATUS"), "success", "with-verifier status")
                assert_equal(kv.get("TELEMETRY_TRUST"), "independent", "with-verifier telemetry trust")
                assert_equal(kv.get("VERIFICATION_STATUS"), "passed", "with-verifier verification status")
                assert_equal(kv.get("TRIGGER_MATCHED"), "true", "with-verifier trigger matched")
                assert_equal(kv.get("ASSERTIONS_PASSED"), "true", "with-verifier assertions")
                passed += 1
                print("[PASS] 5: shim-live with verifier (strict)")
            except AssertionError as exc:
                failed += 1
                print(f"[FAIL] 5: shim-live with verifier: {exc}")

        # ── Test 6: strict-real + trace mode → blocked ──
        create_session(sandbox_root, "e2e-strict-trace-blocked")
        skill_no_adapter2 = build_minimal_skill(temp_root / "t6")
        proc, kv = run_invoke([
            "--session-id", "e2e-strict-trace-blocked",
            "--skill-path", str(skill_no_adapter2),
            "--message", "should be blocked",
            "--channel", "telegram",
            "--mode", "trace",
            "--strict-real",
            "--sandbox-root", str(sandbox_root),
        ], env)
        try:
            # --strict-real + trace should be rejected by argparse
            assert_equal(proc.returncode, 2, "strict-trace return code")
            passed += 1
            print("[PASS] 6: strict-real + trace → argparse rejection")
        except AssertionError as exc:
            failed += 1
            print(f"[FAIL] 6: strict-real + trace: {exc}")

        if bash_available:
            # ── Test 7: auto shim-live preference (adapter + verifier, no openclaw) ──
            create_session(sandbox_root, "e2e-auto-shim-prefer")
            skill_auto = build_minimal_skill(temp_root / "t7", adapter_body=build_success_adapter())
            verifier_auto = build_verifier(temp_root / "t7-ext")
            proc, kv = run_invoke([
                "--session-id", "e2e-auto-shim-prefer",
                "--skill-path", str(skill_auto),
                "--message", "auto prefer shim",
                "--channel", "telegram",
                "--mode", "auto",
                "--strict-real",
                "--verification-manifest", str(verifier_auto),
                "--sandbox-root", str(sandbox_root),
            ], env)
            try:
                assert_equal(proc.returncode, 0, "auto-shim-prefer return code")
                assert_equal(kv.get("SELECTED_MODE"), "shim-live", "auto-shim-prefer selected mode")
                assert_equal(kv.get("INVOKE_STATUS"), "success", "auto-shim-prefer status")
                assert_equal(kv.get("TELEMETRY_TRUST"), "independent", "auto-shim-prefer trust")
                passed += 1
                print("[PASS] 7: auto mode prefers shim-live (adapter + verifier)")
            except AssertionError as exc:
                failed += 1
                print(f"[FAIL] 7: auto shim preference: {exc}")

            # ── Test 8: audit log structure verification ──
            try:
                session_dir = sandbox_root / "e2e-with-verifier"
                exit_codes = json.loads(read_text(session_dir / "logs" / "exit-codes.json"))
                assert_equal(len(exit_codes), 1, "audit entry count")
                entry = exit_codes[0]
                assert_equal(entry.get("executionLevel"), "shim-live", "audit execution level")
                assert_equal(entry.get("realExecuted"), True, "audit real executed")
                assert_equal(entry.get("status"), "success", "audit status")
                assert_equal(entry.get("exitCode"), 0, "audit exit code")
                assert "traceFile" in entry, "audit has trace file ref"
                passed += 1
                print("[PASS] 8: audit log structure")
            except (AssertionError, json.JSONDecodeError, IndexError) as exc:
                failed += 1
                print(f"[FAIL] 8: audit log structure: {exc}")

            # ── Test 9: META.json counter increment ──
            try:
                session_dir = sandbox_root / "e2e-with-verifier"
                meta = json.loads(read_text(session_dir / "META.json"))
                assert_equal(meta.get("commandCount"), 1, "meta command count")
                assert meta.get("totalDurationMs", 0) >= 0, "meta duration non-negative"
                passed += 1
                print("[PASS] 9: META.json counter increment")
            except (AssertionError, json.JSONDecodeError) as exc:
                failed += 1
                print(f"[FAIL] 9: META.json counters: {exc}")

        # ── Test 10: included source changes must refresh cached install ──
        create_session(sandbox_root, "e2e-dist-refresh")
        skill_refresh = build_versioned_skill(temp_root / "t10", "v1")
        proc_first, kv_first = run_invoke([
            "--session-id", "e2e-dist-refresh",
            "--skill-path", str(skill_refresh),
            "--channel", "telegram",
            "--mode", "dry-run",
            "--sandbox-root", str(sandbox_root),
        ], env)
        write_text(skill_refresh / "dist" / "version.txt", "v2\n")
        proc_second, kv_second = run_invoke([
            "--session-id", "e2e-dist-refresh",
            "--skill-path", str(skill_refresh),
            "--channel", "telegram",
            "--mode", "dry-run",
            "--sandbox-root", str(sandbox_root),
        ], env)
        try:
            assert_equal(proc_first.returncode, 0, "dist-refresh first return code")
            assert_equal(proc_second.returncode, 0, "dist-refresh second return code")
            assert_equal(kv_first.get("INSTALL_STATUS"), "installed", "dist-refresh first install status")
            assert_equal(kv_second.get("INSTALL_STATUS"), "installed", "dist-refresh second install status")
            skill_targets = sorted((sandbox_root / "e2e-dist-refresh" / "workspace" / "skills").glob("Integration-Test-Skill-*"))
            assert_equal(len(skill_targets), 2, "dist-refresh installed snapshot count")
            copied_versions = sorted(
                (target / "dist" / "version.txt").read_text(encoding="utf-8-sig").strip()
                for target in skill_targets
            )
            assert_equal(copied_versions, ["v1", "v2"], "dist-refresh copied versions")
            passed += 1
            print("[PASS] 10: source snapshot refreshes cached install")
        except AssertionError as exc:
            failed += 1
            print(f"[FAIL] 10: source refresh: {exc}")

        # ── Test 11: symlink / junction escape must be rejected ──
        create_session(sandbox_root, "e2e-unsafe-link")
        skill_link = build_minimal_skill(temp_root / "t11")
        try:
            link_name = create_escape_link(skill_link, temp_root / "t11-outside")
        except RuntimeError as exc:
            skipped += 1
            print(f"[SKIP] 11: unsafe link rejection: {exc}")
        else:
            proc, _ = run_invoke([
                "--session-id", "e2e-unsafe-link",
                "--skill-path", str(skill_link),
                "--mode", "dry-run",
                "--sandbox-root", str(sandbox_root),
            ], env)
            try:
                assert_equal(proc.returncode, 1, "unsafe-link return code")
                assert_contains(proc.stderr, "unsupported link or reparse point", "unsafe-link error")
                assert_contains(proc.stderr, link_name, "unsafe-link path")
                passed += 1
                print("[PASS] 11: unsafe link is rejected before install")
            except AssertionError as exc:
                failed += 1
                print(f"[FAIL] 11: unsafe link rejection: {exc}")

        # ── Summary ──
        total = passed + failed + skipped
        print(f"\n{'='*60}")
        print(f"E2E Integration: {passed} passed, {failed} failed, {skipped} skipped")
        print(f"{'='*60}")

        summary = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if failed == 0 else 1

    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
