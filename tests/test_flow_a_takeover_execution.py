#!/usr/bin/env python3
"""Smoke tests for Flow A host takeover execution."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import json
import os
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
MOCK_BROWSER = PROJECT_DIR / "scripts" / "fixtures" / "mock_browser_dump.py"


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


class _BrowserHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = b"<html><body><main>__INJECT_JS_RESULT__</main></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class BrowserServer:
    def __enter__(self) -> "BrowserServer":
        self.server = socketserver.TCPServer(("127.0.0.1", 0), _BrowserHandler)
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/news"

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class FeedServer:
    def __init__(self, items: list[dict[str, object]]) -> None:
        payload = json.dumps({"articles": items}, ensure_ascii=False).encode("utf-8")
        self.handler = type("FeedHandler", (BaseHTTPRequestHandler,), {})

        def do_get(handler_self) -> None:  # noqa: N802
            handler_self.send_response(200)
            handler_self.send_header("Content-Type", "application/json")
            handler_self.send_header("Content-Length", str(len(payload)))
            handler_self.end_headers()
            handler_self.wfile.write(payload)

        def log_message(handler_self, format: str, *args) -> None:  # noqa: A003
            return

        setattr(self.handler, "do_GET", do_get)
        setattr(self.handler, "log_message", log_message)

    def __enter__(self) -> "FeedServer":
        self.server = socketserver.TCPServer(("127.0.0.1", 0), self.handler)
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/feed"

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


def test_takeover_reports_remaining_incomplete_cases() -> None:
    temp_root = make_temp_root("flowa-takeover-incomplete-")
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
                        "testCaseIds": ["TC-001", "TC-002"],
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
                            "mode": "shim-live",
                            "verificationPolicy": "assertion-only",
                            "expectedKeywords": ["local"],
                            "hostTakeover": {"enabled": True, "urls": [server.url], "providerAliases": [], "expectedKeywords": ["local"]},
                        },
                    },
                    {
                        "caseId": "TC-002",
                        "surfaceId": "SURFACE-01",
                        "surfaceKind": "skill",
                        "title": "Negative review case",
                        "objective": "Requires manual negative review.",
                        "steps": [f"Fetch `{server.url}` and review negative behavior."],
                        "expected": ["Must stay incomplete under host takeover."],
                        "executionHints": {
                            "mode": "shim-live",
                            "verificationPolicy": "manual-negative-review",
                            "hostTakeover": {"enabled": True, "urls": [server.url], "providerAliases": [], "expectedKeywords": []},
                        },
                    },
                ]
            }
            coverage = {
                "generatedBy": "test",
                "surfaces": [
                    {
                        "surfaceId": "SURFACE-01",
                        "status": "blocked",
                        "executionLevel": "shim-live",
                        "requiredCaseIds": ["TC-001", "TC-002"],
                        "executedCaseCount": 2,
                        "executedCaseIds": ["TC-001", "TC-002"],
                        "caseResults": [
                            {"caseId": "TC-001", "status": "blocked", "evidence": []},
                            {"caseId": "TC-002", "status": "blocked", "evidence": []},
                        ],
                    }
                ],
            }
            write_text(report_dir / "SURFACE-EXECUTION-PLAN.json", json.dumps(surface_plan, ensure_ascii=False, indent=2) + "\n")
            write_text(report_dir / "CASE-EXECUTION-PLAN.json", json.dumps(case_plan, ensure_ascii=False, indent=2) + "\n")
            write_text(execution_dir / "SURFACE-COVERAGE.json", json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")
            write_text(execution_dir / "skill-results.md", "# TEST-EXECUTION/skill-results\n")

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
            assert_equal(payload["status"], "partial", "takeover runner should stay partial when incomplete cases remain")
            assert_equal(payload["remainingIncompleteCases"], ["TC-002"], "remaining incomplete case list")
            remaining_cases = json.loads(read_text(execution_dir / "REMAINING-CASES.json"))
            assert_equal(remaining_cases["remainingIncompleteCases"], ["TC-002"], "remaining cases file sync")
        print("  [PASS] test_takeover_reports_remaining_incomplete_cases")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_takeover_executes_fault_injection_case() -> None:
    temp_root = make_temp_root("flowa-takeover-fault-")
    try:
        report_dir = temp_root / "reports"
        execution_dir = report_dir / "TEST-EXECUTION"
        execution_dir.mkdir(parents=True, exist_ok=True)
        surface_plan = {
            "surfaces": [
                {
                    "surfaceId": "SURFACE-01",
                    "kind": "skill",
                    "label": "Skill Entry",
                    "identifier": "crypto-gold-report",
                    "minimumMode": "shim-live",
                    "testCaseIds": ["TC-003"],
                }
            ]
        }
        case_plan = {
            "cases": [
                {
                    "caseId": "TC-003",
                    "surfaceId": "SURFACE-01",
                    "surfaceKind": "skill",
                    "title": "Missing field response",
                    "objective": "Verify missing-field upstream fixture can be produced.",
                    "steps": ["Construct a response with missing price fields."],
                    "expected": ["Synthetic upstream fixture is available."],
                    "executionHints": {
                        "mode": "shim-live",
                        "verificationPolicy": "fixture-only",
                        "faultInjection": {
                            "enabled": True,
                            "profile": "missing-fields",
                            "responseType": "json",
                        },
                        "hostTakeover": {
                            "enabled": True,
                            "strategy": "fault-injection",
                            "strictReal": False,
                            "urls": [],
                            "providerAliases": [],
                            "expectedKeywords": [],
                            "faultInjection": {
                                "enabled": True,
                                "profile": "missing-fields",
                                "responseType": "json",
                            },
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
                    "requiredCaseIds": ["TC-003"],
                    "executedCaseCount": 1,
                    "executedCaseIds": ["TC-003"],
                    "caseResults": [{"caseId": "TC-003", "status": "blocked", "evidence": []}],
                }
            ],
        }
        write_text(report_dir / "SURFACE-EXECUTION-PLAN.json", json.dumps(surface_plan, ensure_ascii=False, indent=2) + "\n")
        write_text(report_dir / "CASE-EXECUTION-PLAN.json", json.dumps(case_plan, ensure_ascii=False, indent=2) + "\n")
        write_text(execution_dir / "SURFACE-COVERAGE.json", json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")
        write_text(execution_dir / "skill-results.md", "# TEST-EXECUTION/skill-results\n")

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
        assert_equal(payload["status"], "completed", "fault fixture should resolve blocked case")
        updated_coverage = json.loads(read_text(execution_dir / "SURFACE-COVERAGE.json"))
        row = updated_coverage["surfaces"][0]["caseResults"][0]
        assert_equal(row["status"], "passed", "fault fixture case resolved")
        evidence_payload = json.loads(read_text(Path(row["evidence"][0])))
        assert_equal(evidence_payload["observed"], True, "missing-fields fault observation recorded")
        print("  [PASS] test_takeover_executes_fault_injection_case")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_takeover_executes_http_500_fault_injection_case() -> None:
    temp_root = make_temp_root("flowa-takeover-http500-")
    try:
        report_dir = temp_root / "reports"
        execution_dir = report_dir / "TEST-EXECUTION"
        execution_dir.mkdir(parents=True, exist_ok=True)
        surface_plan = {
            "surfaces": [
                {
                    "surfaceId": "SURFACE-01",
                    "kind": "skill",
                    "label": "Skill Entry",
                    "identifier": "crypto-gold-report",
                    "minimumMode": "shim-live",
                    "testCaseIds": ["TC-003B"],
                }
            ]
        }
        case_plan = {
            "cases": [
                {
                    "caseId": "TC-003B",
                    "surfaceId": "SURFACE-01",
                    "surfaceKind": "skill",
                    "title": "Upstream HTTP 500 fault",
                    "objective": "Verify HTTP 500 fault injection is observed.",
                    "steps": ["Construct an upstream HTTP 500 response fixture."],
                    "expected": ["HTTP 500 is observed during takeover."],
                    "executionHints": {
                        "mode": "shim-live",
                        "verificationPolicy": "fixture-only",
                        "faultInjection": {"enabled": True, "profile": "http-500", "responseType": "json"},
                        "hostTakeover": {
                            "enabled": True,
                            "strategy": "fault-injection",
                            "strictReal": False,
                            "urls": [],
                            "providerAliases": ["binance"],
                            "expectedKeywords": [],
                            "faultInjection": {"enabled": True, "profile": "http-500", "responseType": "json"},
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
                    "requiredCaseIds": ["TC-003B"],
                    "executedCaseCount": 1,
                    "executedCaseIds": ["TC-003B"],
                    "caseResults": [{"caseId": "TC-003B", "status": "blocked", "evidence": []}],
                }
            ],
        }
        write_text(report_dir / "SURFACE-EXECUTION-PLAN.json", json.dumps(surface_plan, ensure_ascii=False, indent=2) + "\n")
        write_text(report_dir / "CASE-EXECUTION-PLAN.json", json.dumps(case_plan, ensure_ascii=False, indent=2) + "\n")
        write_text(execution_dir / "SURFACE-COVERAGE.json", json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")
        write_text(execution_dir / "skill-results.md", "# TEST-EXECUTION/skill-results\n")

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
        assert_equal(payload["status"], "completed", "http-500 fault fixture should resolve blocked case")
        updated_coverage = json.loads(read_text(execution_dir / "SURFACE-COVERAGE.json"))
        row = updated_coverage["surfaces"][0]["caseResults"][0]
        evidence_payload = json.loads(read_text(Path(row["evidence"][0])))
        assert_equal(evidence_payload["observed"], True, "http-500 observation recorded")
        assert_equal(evidence_payload["statusCode"], 500, "http-500 status code recorded")
        print("  [PASS] test_takeover_executes_http_500_fault_injection_case")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_takeover_executes_browser_case() -> None:
    temp_root = make_temp_root("flowa-takeover-browser-")
    try:
        report_dir = temp_root / "reports"
        execution_dir = report_dir / "TEST-EXECUTION"
        execution_dir.mkdir(parents=True, exist_ok=True)
        with BrowserServer() as server:
            surface_plan = {
                "surfaces": [
                    {
                        "surfaceId": "SURFACE-01",
                        "kind": "skill",
                        "label": "Skill Entry",
                        "identifier": "crypto-gold-report",
                        "minimumMode": "shim-live",
                        "testCaseIds": ["TC-004"],
                    }
                ]
            }
            case_plan = {
                "cases": [
                    {
                        "caseId": "TC-004",
                        "surfaceId": "SURFACE-01",
                        "surfaceKind": "skill",
                        "title": "Rendered news page",
                        "objective": "Verify a browser-rendered page can be collected.",
                        "steps": [f"Open `{server.url}` in a browser."],
                        "expected": ["Rendered DOM contains `bridge-browser`."],
                        "executionHints": {
                            "mode": "shim-live",
                            "verificationPolicy": "assertion-only",
                            "browserRequired": True,
                            "expectedKeywords": ["bridge-browser"],
                            "hostTakeover": {
                                "enabled": True,
                                "strategy": "browser-probe",
                                "strictReal": True,
                                "urls": [server.url],
                                "providerAliases": ["jin10"],
                                "expectedKeywords": ["bridge-browser"],
                                "browserRequired": True,
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
                        "requiredCaseIds": ["TC-004"],
                        "executedCaseCount": 1,
                        "executedCaseIds": ["TC-004"],
                        "caseResults": [{"caseId": "TC-004", "status": "blocked", "evidence": []}],
                    }
                ],
            }
            write_text(report_dir / "SURFACE-EXECUTION-PLAN.json", json.dumps(surface_plan, ensure_ascii=False, indent=2) + "\n")
            write_text(report_dir / "CASE-EXECUTION-PLAN.json", json.dumps(case_plan, ensure_ascii=False, indent=2) + "\n")
            write_text(execution_dir / "SURFACE-COVERAGE.json", json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")
            write_text(execution_dir / "skill-results.md", "# TEST-EXECUTION/skill-results\n")
            env = dict(os.environ)
            env["NEXUS_BROWSER_DUMP_COMMAND"] = json.dumps([sys.executable, str(MOCK_BROWSER)], ensure_ascii=False)
            proc = subprocess.run(
                [sys.executable, str(TAKEOVER), "--report-dir", str(report_dir)],
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            assert_equal(proc.returncode, 0, "takeover runner exit code")
            payload = json.loads(proc.stdout)
            assert_equal(payload["status"], "completed", "browser case should resolve")
            updated_coverage = json.loads(read_text(execution_dir / "SURFACE-COVERAGE.json"))
            row = updated_coverage["surfaces"][0]["caseResults"][0]
            assert_equal(row["status"], "passed", "browser case resolved")
        print("  [PASS] test_takeover_executes_browser_case")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_takeover_executes_multi_source_case() -> None:
    temp_root = make_temp_root("flowa-takeover-multi-")
    try:
        report_dir = temp_root / "reports"
        execution_dir = report_dir / "TEST-EXECUTION"
        execution_dir.mkdir(parents=True, exist_ok=True)
        items_a = [{"title": "News A", "url": "https://a/1"}, {"title": "News B", "url": "https://a/2"}]
        items_b = [{"title": "News B", "url": "https://b/2"}, {"title": "News C", "url": "https://b/3"}]
        with FeedServer(items_a) as server_a, FeedServer(items_b) as server_b:
            surface_plan = {
                "surfaces": [
                    {
                        "surfaceId": "SURFACE-01",
                        "kind": "skill",
                        "label": "Skill Entry",
                        "identifier": "crypto-gold-report",
                        "minimumMode": "shim-live",
                        "testCaseIds": ["TC-005"],
                    }
                ]
            }
            case_plan = {
                "cases": [
                    {
                        "caseId": "TC-005",
                        "surfaceId": "SURFACE-01",
                        "surfaceKind": "skill",
                        "title": "Aggregate multi-source news",
                        "objective": "Verify multi-source aggregation and dedupe.",
                        "steps": [f"Fetch `{server_a.url}` and `{server_b.url}` and dedupe by title."],
                        "expected": ["Three deduped articles are preserved."],
                        "executionHints": {
                            "mode": "shim-live",
                            "verificationPolicy": "assertion-only",
                            "multiSource": {
                                "enabled": True,
                                "minSourcesRequired": 2,
                                "dedupeKey": "title",
                                "aggregationRule": "merge-dedupe",
                            },
                            "hostTakeover": {
                                "enabled": True,
                                "strategy": "multi-source",
                                "strictReal": True,
                                "urls": [server_a.url, server_b.url],
                                "providerAliases": [],
                                "expectedKeywords": [],
                                "multiSource": {
                                    "enabled": True,
                                    "minSourcesRequired": 2,
                                    "dedupeKey": "title",
                                    "aggregationRule": "merge-dedupe",
                                },
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
                        "requiredCaseIds": ["TC-005"],
                        "executedCaseCount": 1,
                        "executedCaseIds": ["TC-005"],
                        "caseResults": [{"caseId": "TC-005", "status": "blocked", "evidence": []}],
                    }
                ],
            }
            write_text(report_dir / "SURFACE-EXECUTION-PLAN.json", json.dumps(surface_plan, ensure_ascii=False, indent=2) + "\n")
            write_text(report_dir / "CASE-EXECUTION-PLAN.json", json.dumps(case_plan, ensure_ascii=False, indent=2) + "\n")
            write_text(execution_dir / "SURFACE-COVERAGE.json", json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")
            write_text(execution_dir / "skill-results.md", "# TEST-EXECUTION/skill-results\n")
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
            assert_equal(payload["status"], "completed", "multi-source case should resolve")
            updated_coverage = json.loads(read_text(execution_dir / "SURFACE-COVERAGE.json"))
            row = updated_coverage["surfaces"][0]["caseResults"][0]
            assert_equal(row["status"], "passed", "multi-source case resolved")
        print("  [PASS] test_takeover_executes_multi_source_case")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_takeover_executes_synthetic_dataset_case() -> None:
    temp_root = make_temp_root("flowa-takeover-synth-")
    try:
        report_dir = temp_root / "reports"
        execution_dir = report_dir / "TEST-EXECUTION"
        execution_dir.mkdir(parents=True, exist_ok=True)
        surface_plan = {
            "surfaces": [
                {
                    "surfaceId": "SURFACE-01",
                    "kind": "skill",
                    "label": "Skill Entry",
                    "identifier": "crypto-gold-report",
                    "minimumMode": "shim-live",
                    "testCaseIds": ["TC-006"],
                }
            ]
        }
        case_plan = {
            "cases": [
                {
                    "caseId": "TC-006",
                    "surfaceId": "SURFACE-01",
                    "surfaceKind": "skill",
                    "title": "Generate 110 synthetic news items",
                    "objective": "Verify large dataset boundary generation.",
                    "steps": ["Generate a synthetic 110-item news feed for boundary validation."],
                    "expected": ["Synthetic dataset contains 110 records."],
                    "executionHints": {
                        "mode": "shim-live",
                        "verificationPolicy": "synthetic-dataset",
                        "syntheticDataset": {
                            "enabled": True,
                            "kind": "news-feed",
                            "recordCount": 110,
                            "duplicateRatio": 0.1,
                            "languages": ["zh-CN", "en"],
                            "missingFields": [],
                        },
                        "hostTakeover": {
                            "enabled": True,
                            "strategy": "synthetic-dataset",
                            "strictReal": False,
                            "urls": [],
                            "providerAliases": [],
                            "expectedKeywords": [],
                            "syntheticDataset": {
                                "enabled": True,
                                "kind": "news-feed",
                                "recordCount": 110,
                                "duplicateRatio": 0.1,
                                "languages": ["zh-CN", "en"],
                                "missingFields": [],
                            },
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
                    "requiredCaseIds": ["TC-006"],
                    "executedCaseCount": 1,
                    "executedCaseIds": ["TC-006"],
                    "caseResults": [{"caseId": "TC-006", "status": "blocked", "evidence": []}],
                }
            ],
        }
        write_text(report_dir / "SURFACE-EXECUTION-PLAN.json", json.dumps(surface_plan, ensure_ascii=False, indent=2) + "\n")
        write_text(report_dir / "CASE-EXECUTION-PLAN.json", json.dumps(case_plan, ensure_ascii=False, indent=2) + "\n")
        write_text(execution_dir / "SURFACE-COVERAGE.json", json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")
        write_text(execution_dir / "skill-results.md", "# TEST-EXECUTION/skill-results\n")
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
        assert_equal(payload["status"], "completed", "synthetic dataset case should resolve")
        updated_coverage = json.loads(read_text(execution_dir / "SURFACE-COVERAGE.json"))
        row = updated_coverage["surfaces"][0]["caseResults"][0]
        assert_equal(row["status"], "passed", "synthetic dataset case resolved")
        print("  [PASS] test_takeover_executes_synthetic_dataset_case")
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
    try:
        test_takeover_reports_remaining_incomplete_cases()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_takeover_reports_remaining_incomplete_cases: {exc}")
        failed += 1
    try:
        test_takeover_executes_fault_injection_case()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_takeover_executes_fault_injection_case: {exc}")
        failed += 1
    try:
        test_takeover_executes_http_500_fault_injection_case()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_takeover_executes_http_500_fault_injection_case: {exc}")
        failed += 1
    try:
        test_takeover_executes_browser_case()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_takeover_executes_browser_case: {exc}")
        failed += 1
    try:
        test_takeover_executes_multi_source_case()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_takeover_executes_multi_source_case: {exc}")
        failed += 1
    try:
        test_takeover_executes_synthetic_dataset_case()
        passed += 1
    except AssertionError as exc:
        print(f"  [FAIL] test_takeover_executes_synthetic_dataset_case: {exc}")
        failed += 1
    print("=" * 40)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
