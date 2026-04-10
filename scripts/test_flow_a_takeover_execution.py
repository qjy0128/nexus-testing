#!/usr/bin/env python3
"""Smoke tests for Flow A host takeover execution."""

from __future__ import annotations

import json
import shutil
import socketserver
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from test_helpers import assert_equal, make_temp_root, read_text, write_text

PROJECT_DIR = Path(__file__).resolve().parents[1]
TAKEOVER = PROJECT_DIR / "scripts" / "run_flow_a_takeover_execution.py"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = b'{"status":"ok","provider":"local","price":123.45}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class LocalServer:
    def __enter__(self) -> "LocalServer":
        self.server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/price"

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def test_takeover_executes_blocked_http_case() -> None:
    temp_root = make_temp_root("flowa-takeover-")
    try:
        report_dir = temp_root / "reports"
        execution_dir = report_dir / "TEST-EXECUTION"
        execution_dir.mkdir(parents=True, exist_ok=True)
        with LocalServer() as server:
            surface_plan = {
                "surfaces": [
                    {
                        "surfaceId": "SURFACE-01",
                        "kind": "skill",
                        "label": "Skill Entry",
                        "identifier": "crypto-gold-report",
                        "minimumMode": "shim-live",
                        "testCaseIds": ["TC-001"],
                    }
                ]
            }
            case_plan = {
                "cases": [
                    {
                        "caseId": "TC-001",
                        "surfaceId": "SURFACE-01",
                        "surfaceKind": "skill",
                        "title": "Probe local provider",
                        "objective": "Verify the provider can be reached with a real HTTP call.",
                        "steps": [f"Fetch `{server.url}` and record the live payload."],
                        "expected": ["Response contains `local`."],
                        "executionHints": {
                            "message": "case-id=TC-001; surface-id=SURFACE-01",
                            "mode": "shim-live",
                            "verificationPolicy": "assertion-only",
                            "expectedKeywords": ["local"],
                            "hostTakeover": {
                                "enabled": True,
                                "strategy": "http-probe",
                                "strictReal": True,
                                "urls": [server.url],
                                "providerAliases": [],
                                "expectedKeywords": ["local"],
                            },
                        },
                    }
                ]
            }
            coverage = {
                "generatedBy": "test",
                "surfaces": [
                    {
                        "surfaceId": "SURFACE-01",
                        "status": "blocked",
                        "executionLevel": "shim-live",
                        "requiredCaseIds": ["TC-001"],
                        "executedCaseCount": 1,
                        "executedCaseIds": ["TC-001"],
                        "caseResults": [{"caseId": "TC-001", "status": "blocked", "evidence": []}],
                    }
                ],
            }
            write_text(report_dir / "SURFACE-EXECUTION-PLAN.json", json.dumps(surface_plan, ensure_ascii=False, indent=2) + "\n")
            write_text(report_dir / "CASE-EXECUTION-PLAN.json", json.dumps(case_plan, ensure_ascii=False, indent=2) + "\n")
            write_text(execution_dir / "SURFACE-COVERAGE.json", json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")
            write_text(
                execution_dir / "skill-results.md",
                "# TEST-EXECUTION/skill-results\n\n### SURFACE-01 blocked\n- surface-id: `SURFACE-01`\n- execution-level: `shim-live`\n- status: `blocked`\n- evidence: ``\n- notes: `case-coverage=0/1; blocked-cases=TC-001`\n- executed-case-ids: `TC-001`\n",
            )

            proc = subprocess.run(
                [sys.executable, str(TAKEOVER), "--report-dir", str(report_dir)],
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert_equal(proc.returncode, 0, "takeover runner exit code")
            payload = json.loads(proc.stdout)
            assert_equal(payload["status"], "completed", "takeover runner status")

            updated_coverage = json.loads(read_text(execution_dir / "SURFACE-COVERAGE.json"))
            row = updated_coverage["surfaces"][0]["caseResults"][0]
            assert_equal(row["status"], "passed", "blocked case resolved")
            skill_results = read_text(execution_dir / "skill-results.md")
            if "- status: `passed`" not in skill_results:
                raise AssertionError("skill-results should show passed surface after takeover")
        print("  [PASS] test_takeover_executes_blocked_http_case")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Flow A Takeover Smoke Tests")
    print("=" * 40)
    try:
        test_takeover_executes_blocked_http_case()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_takeover_executes_blocked_http_case: {exc}")
        failed += 1
    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
