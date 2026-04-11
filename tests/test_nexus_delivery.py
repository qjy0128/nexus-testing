#!/usr/bin/env python3
"""Smoke tests for delivery relay, send, and confirmation."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from test_helpers import assert_equal, read_text, write_text

from nexus_testing.runtime.policy import resolve_execution_policy

PROJECT_DIR = Path(__file__).resolve().parents[1]
DELIVERY = PROJECT_DIR / "scripts" / "nexus_delivery.py"


def run_json(*args: str) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, str(DELIVERY), *args],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise AssertionError(f"delivery command failed: {args!r}; stdout={proc.stdout!r}; stderr={proc.stderr!r}")
    return json.loads(proc.stdout)


def test_delivery_send_and_confirm() -> None:
    stamp = f"2099-01-01-delivery-cli-{time.time_ns()}"
    report_file = PROJECT_DIR / "memory" / "nexus-reports" / stamp / "FINAL-TEST-REPORT.md"
    relay_dir = PROJECT_DIR / "files" / "nexus-reports" / stamp
    sender_script = PROJECT_DIR / ".tmp" / f"mock-sender-{time.time_ns()}.py"
    try:
        write_text(report_file, "# Final\n")
        write_text(
            sender_script,
            "\n".join(
                [
                    "import json, sys",
                    "payload = {",
                    "  'status': 'sent',",
                    "  'receiptId': 'receipt-001',",
                    "  'evidence': [sys.argv[1]],",
                    "}",
                    "print(json.dumps(payload))",
                ]
            )
            + "\n",
        )
        sent = run_json(
            "send",
            "--report-file",
            str(report_file),
            "--backend",
            "command",
            "--channel",
            "telegram",
            "--caption",
            "please review",
            "--command",
            sys.executable,
            str(sender_script),
            "{abs_relay_path}",
        )
        receipt = sent["receipt"]
        assert_equal(receipt["status"], "sent", "delivery send status")
        assert_equal(receipt["receipt_id"], "receipt-001", "delivery receipt id")
        mirrored = relay_dir / "FINAL-TEST-REPORT.md"
        assert mirrored.exists(), f"mirrored report missing: {mirrored}"
        assert_equal(read_text(mirrored), "# Final\n", "mirrored report content")

        confirmed = run_json(
            "confirm",
            "--report-file",
            str(report_file),
            "--status",
            "accepted",
            "--note",
            "looks good",
            "--confirmed-by",
            "tester",
        )
        assert_equal(confirmed["status"], "accepted", "confirmation status")

        status = run_json("status", "--report-file", str(report_file))
        assert_equal(status["delivery"]["receipt"]["receipt_id"], "receipt-001", "status delivery receipt id")
        assert_equal(status["confirmation"]["status"], "accepted", "status confirmation")
        print("  [PASS] test_delivery_send_and_confirm")
    finally:
        shutil.rmtree(report_file.parent, ignore_errors=True)
        shutil.rmtree(relay_dir, ignore_errors=True)
        sender_script.unlink(missing_ok=True)


def test_execution_policy_defaults() -> None:
    internal = resolve_execution_policy("internal-fast")
    balanced = resolve_execution_policy("balanced")
    strict = resolve_execution_policy("strict")
    assert_equal(internal.run_security_scan, False, "internal-fast security scan")
    assert_equal(internal.strict_real, False, "internal-fast strict real")
    assert_equal(balanced.prefer_host_execution, True, "balanced host preference")
    assert_equal(strict.strict_real, True, "strict profile strict real")
    print("  [PASS] test_execution_policy_defaults")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    passed = 0
    failed = 0
    print("Delivery Smoke Tests")
    print("=" * 40)
    for test in (test_delivery_send_and_confirm, test_execution_policy_defaults):
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
