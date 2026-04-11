#!/usr/bin/env python3
"""Host-side Flow A takeover executor for blocked/pending real-call cases."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from run_flow_a_browser_execution import run_browser_probe
from run_flow_a_multi_source_execution import run_multi_source_probe

from nexus_testing.flow_a_synthetic_data import build_dataset
from nexus_testing.json_utils import load_json
from nexus_testing.sandbox_skill_invoke.core import write_text

URL_PATTERN = re.compile(r"https?://[^\s`)>]+", re.IGNORECASE)
HTTP_PROVIDER_ALIASES: dict[str, list[str]] = {
    "binance": ["https://api.binance.com/api/v3/ping"],
    "coingecko": ["https://api.coingecko.com/api/v3/ping"],
    "coinpaprika": ["https://api.coinpaprika.com/v1/global"],
    "tradingeconomics": ["https://tradingeconomics.com/commodity/gold"],
    "chinagoldgroup": ["http://www.chinagoldgroup.com/"],
    "boc": ["https://www.boc.cn/"],
    "jin10": ["https://www.jin10.com/"],
    "coindesk": ["https://www.coindesk.com/"],
}


def case_text_blob(case: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ("title", "objective", "identifier", "surfaceLabel"):
        value = str(case.get(key, "")).strip()
        if value:
            parts.append(value)
    for key in ("steps", "expected"):
        value = case.get(key, [])
        if isinstance(value, list):
            parts.extend(str(item).strip() for item in value if str(item).strip())
    hints = case.get("executionHints", {})
    if isinstance(hints, dict):
        message = str(hints.get("message", "")).strip()
        if message:
            parts.append(message)
    return "\n".join(parts)


def default_coverage_entry(surface: dict[str, object]) -> dict[str, object]:
    required_case_ids = [str(item) for item in surface.get("testCaseIds", []) if str(item).strip()]
    return {
        "surfaceId": surface.get("surfaceId"),
        "status": "pending",
        "executionLevel": str(surface.get("minimumMode", "shim-live")),
        "requiredCaseIds": required_case_ids,
        "executedCaseCount": 0,
        "executedCaseIds": [],
        "caseResults": [{"caseId": case_id, "status": "pending", "evidence": []} for case_id in required_case_ids],
    }


def coverage_case_map(entry: dict[str, object]) -> dict[str, dict[str, object]]:
    mapping: dict[str, dict[str, object]] = {}
    rows = entry.get("caseResults", [])
    if not isinstance(rows, list):
        rows = []
        entry["caseResults"] = rows
    for row in rows:
        if not isinstance(row, dict):
            continue
        case_id = str(row.get("caseId", "")).strip()
        if case_id:
            mapping[case_id] = row
    return mapping


def ensure_coverage(plan: dict[str, object], coverage: dict[str, object]) -> dict[str, dict[str, object]]:
    surfaces = coverage.get("surfaces", [])
    if not isinstance(surfaces, list):
        surfaces = []
        coverage["surfaces"] = surfaces
    mapping: dict[str, dict[str, object]] = {}
    for item in surfaces:
        if not isinstance(item, dict):
            continue
        surface_id = str(item.get("surfaceId", "")).strip()
        if surface_id:
            mapping[surface_id] = item

    for surface in plan.get("surfaces", []):
        if not isinstance(surface, dict):
            continue
        surface_id = str(surface.get("surfaceId", "")).strip()
        if not surface_id:
            continue
        if surface_id not in mapping:
            entry = default_coverage_entry(surface)
            surfaces.append(entry)
            mapping[surface_id] = entry
        else:
            entry = mapping[surface_id]
            entry.setdefault("requiredCaseIds", [str(item) for item in surface.get("testCaseIds", []) if str(item).strip()])
            entry.setdefault("executionLevel", str(surface.get("minimumMode", "shim-live")))
            entry.setdefault("caseResults", [])
            existing_rows = coverage_case_map(entry)
            for case_id in entry.get("requiredCaseIds", []):
                if case_id not in existing_rows:
                    row = {"caseId": case_id, "status": "pending", "evidence": []}
                    entry["caseResults"].append(row)
                    existing_rows[case_id] = row
    return mapping


def extract_probe_urls(case: dict[str, object]) -> list[str]:
    hints = case.get("executionHints", {})
    urls: list[str] = []
    aliases: list[str] = []
    if isinstance(hints, dict):
        host_takeover = hints.get("hostTakeover", {})
        if isinstance(host_takeover, dict):
            urls.extend(str(item).strip() for item in host_takeover.get("urls", []) if str(item).strip())
            aliases.extend(str(item).strip().lower() for item in host_takeover.get("providerAliases", []) if str(item).strip())
    if not urls:
        urls.extend(match.group(0) for match in URL_PATTERN.finditer(case_text_blob(case)))
    if not aliases:
        blob = case_text_blob(case).lower()
        aliases.extend(name for name in HTTP_PROVIDER_ALIASES if name in blob)
    for alias in aliases:
        urls.extend(HTTP_PROVIDER_ALIASES.get(alias, []))
    return list(dict.fromkeys(urls))


def expected_keywords(case: dict[str, object]) -> list[str]:
    hints = case.get("executionHints", {})
    if not isinstance(hints, dict):
        return []
    host_takeover = hints.get("hostTakeover", {})
    if isinstance(host_takeover, dict):
        values = [str(item).strip() for item in host_takeover.get("expectedKeywords", []) if str(item).strip()]
        if values:
            return values
    return [str(item).strip() for item in hints.get("expectedKeywords", []) if str(item).strip()]


def fetch_url(url: str, timeout: float) -> tuple[bool, int | None, str, bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "nexus-testing-takeover/0.9.41",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = int(getattr(response, "status", 200))
            body = response.read(8192)
            return True, status_code, str(response.headers.get("Content-Type", "")), body
    except urllib.error.HTTPError as exc:
        body = exc.read(2048) if hasattr(exc, "read") else b""
        return False, int(exc.code), str(exc.headers.get("Content-Type", "")) if exc.headers else "", body
    except Exception as exc:  # noqa: BLE001
        return False, None, str(exc), b""


def write_evidence(evidence_dir: Path, case_id: str, payload: dict[str, object], body: bytes) -> list[str]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stem = case_id.lower()
    json_path = evidence_dir / f"{stem}.json"
    body_path = evidence_dir / f"{stem}.body.txt"
    write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    if body:
        body_path.write_bytes(body)
        return [str(json_path), str(body_path)]
    return [str(json_path)]


def execute_http_case(case: dict[str, object], evidence_dir: Path) -> dict[str, object]:
    urls = extract_probe_urls(case)
    if not urls:
        return {
            "caseId": str(case.get("caseId", "unknown")),
            "status": "blocked",
            "executionLevel": "shim-live",
            "evidence": [],
            "notes": "host-takeover-unsupported=true; reason=no-http-probe-targets",
        }

    timeout = 8.0
    keywords = [item.lower() for item in expected_keywords(case)]
    verification_policy = str(case.get("executionHints", {}).get("verificationPolicy", "assertion-only")) if isinstance(case.get("executionHints"), dict) else "assertion-only"
    if verification_policy == "manual-negative-review":
        return {
            "caseId": str(case.get("caseId", "unknown")),
            "status": "incomplete",
            "executionLevel": "shim-live",
            "evidence": [],
            "notes": "host-takeover-supported=true; negative-case-manual-review=true",
        }

    attempts: list[str] = []
    for url in urls:
        ok, status_code, content_type, body = fetch_url(url, timeout)
        text_body = body.decode("utf-8", errors="replace")
        keyword_hits = [item for item in keywords if item in text_body.lower()]
        payload = {
            "url": url,
            "ok": ok,
            "statusCode": status_code,
            "contentType": content_type,
            "keywordHits": keyword_hits,
            "bodyPreview": text_body[:400],
        }
        evidence = write_evidence(evidence_dir, str(case.get("caseId", "unknown")), payload, body)
        if ok and (not keywords or keyword_hits):
            return {
                "caseId": str(case.get("caseId", "unknown")),
                "status": "passed",
                "executionLevel": "shim-live",
                "evidence": evidence,
                "notes": f"host-takeover=true; probe-url={url}; http-status={status_code}; content-type={content_type or 'unknown'}",
            }
        attempts.append(f"{url}:{status_code if status_code is not None else 'error'}")

    return {
        "caseId": str(case.get("caseId", "unknown")),
        "status": "blocked",
        "executionLevel": "shim-live",
        "evidence": evidence if 'evidence' in locals() else [],
        "notes": f"host-takeover=true; http-probe-failed={','.join(attempts)}",
    }


class _FaultHandler(BaseHTTPRequestHandler):
    payload: bytes = b"{}"
    content_type = "application/json"
    status_code = 200
    delay_seconds = 0.0

    def do_GET(self) -> None:  # noqa: N802
        if float(self.delay_seconds) > 0:
            import time

            time.sleep(float(self.delay_seconds))
        self.send_response(int(self.status_code))
        self.send_header("Content-Type", str(self.content_type))
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


@contextmanager
def local_fault_server(profile: dict[str, object]):
    profile_name = str(profile.get("profile", "empty-json"))
    response_type = str(profile.get("responseType", "json"))
    status_code = 500 if profile_name == "http-500" else 200
    delay_seconds = 0.0
    if profile_name == "missing-fields":
        payload = b'{"status":"ok","currency":"USD"}'
    elif profile_name == "empty-html":
        payload = b""
    elif profile_name == "timeout":
        payload = b'{"status":"late"}'
        delay_seconds = 2.5
    else:
        payload = b"{}" if response_type == "json" else b"<html><body></body></html>"
    content_type = "text/html" if response_type == "html" else "application/json"

    handler = type(
        "LocalFaultHandler",
        (_FaultHandler,),
        {
            "payload": payload,
            "content_type": content_type,
            "status_code": status_code,
            "delay_seconds": delay_seconds,
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/fixture"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def validate_fault_injection_observed(
    profile: dict[str, object],
    ok: bool,
    status_code: int | None,
    content_type: str,
    body: bytes,
) -> tuple[bool, str]:
    profile_name = str(profile.get("profile", ""))
    body_text = body.decode("utf-8", errors="replace")
    parsed_json: object | None = None
    try:
        parsed_json = json.loads(body_text) if body_text else None
    except json.JSONDecodeError:
        parsed_json = None

    if profile_name == "missing-fields":
        required_missing = [str(item).strip() for item in profile.get("requiredMissingFields", []) if str(item).strip()]
        if not isinstance(parsed_json, dict):
            return False, "missing-fields fixture did not return JSON object"
        missing = [field for field in required_missing if field not in parsed_json]
        return (len(missing) == len(required_missing), f"missing fields observed: {', '.join(missing) or '(none)'}")
    if profile_name == "empty-json":
        return (body_text.strip() in {"{}", "[]"}, f"empty-json body={body_text.strip()!r}")
    if profile_name == "empty-html":
        return (body_text.strip() == "", f"empty-html length={len(body_text.strip())}")
    if profile_name == "timeout":
        return (not ok and status_code is None, f"timeout observed ok={ok} status={status_code}")
    if profile_name == "dns-failure":
        return (not ok and status_code is None, f"dns failure observed ok={ok} status={status_code} note={content_type}")
    if profile_name == "http-500":
        return (not ok and status_code == 500, f"http-500 observed status={status_code}")
    return False, f"unsupported fault profile: {profile_name}"


def execute_browser_case(case: dict[str, object], evidence_dir: Path) -> dict[str, object]:
    urls = extract_probe_urls(case)
    if not urls:
        return {
            "caseId": str(case.get("caseId", "unknown")),
            "status": "blocked",
            "executionLevel": "browser-live",
            "evidence": [],
            "notes": "browser-takeover-unsupported=true; reason=no-browser-targets",
        }
    result = run_browser_probe(urls[0], expected_keywords(case))
    if str(result.get("status")) == "unsupported":
        return {
            "caseId": str(case.get("caseId", "unknown")),
            "status": "blocked",
            "executionLevel": "browser-live",
            "evidence": [],
            "notes": f"browser-takeover-unsupported=true; reason={result.get('note')}",
        }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    case_id = str(case.get("caseId", "unknown")).lower()
    dom_path = evidence_dir / f"{case_id}.browser.dom.html"
    json_path = evidence_dir / f"{case_id}.browser.json"
    write_text(dom_path, str(result.get("dom", "")))
    write_text(
        json_path,
        json.dumps(
            {
                "url": urls[0],
                "status": result.get("status"),
                "note": result.get("note"),
                "keywordHits": result.get("keywordHits", []),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return {
        "caseId": str(case.get("caseId", "unknown")),
        "status": "passed" if str(result.get("status")) == "passed" else "blocked",
        "executionLevel": "browser-live",
        "evidence": [str(json_path), str(dom_path)],
        "notes": f"host-takeover=true; browser-probe={urls[0]}; note={result.get('note')}",
    }


def execute_fault_injection_case(case: dict[str, object], evidence_dir: Path) -> dict[str, object]:
    hints = case.get("executionHints", {})
    fault = hints.get("faultInjection", {}) if isinstance(hints, dict) else {}
    if not isinstance(fault, dict) or not bool(fault.get("enabled")):
        return {
            "caseId": str(case.get("caseId", "unknown")),
            "status": "blocked",
            "executionLevel": "fixture",
            "evidence": [],
            "notes": "fault-injection-disabled=true",
        }
    if str(fault.get("profile")) == "dns-failure":
        url = "http://nonexistent.invalid/"
        ok, status_code, content_type, body = fetch_url(url, 2.0)
    else:
        timeout_seconds = 1.0 if str(fault.get("profile")) == "timeout" else 5.0
        with local_fault_server(fault) as url:
            ok, status_code, content_type, body = fetch_url(url, timeout_seconds)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    case_id = str(case.get("caseId", "unknown")).lower()
    json_path = evidence_dir / f"{case_id}.fault.json"
    payload = {
        "profile": fault.get("profile"),
        "responseType": fault.get("responseType"),
        "fixtureUrl": url,
        "statusCode": status_code,
        "contentType": content_type,
        "bodyPreview": body.decode("utf-8", errors="replace")[:400],
        "ok": ok,
    }
    observed, observation_note = validate_fault_injection_observed(fault, ok, status_code, content_type, body)
    payload["observed"] = observed
    payload["observationNote"] = observation_note
    write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    status = "passed" if observed else "blocked"
    return {
        "caseId": str(case.get("caseId", "unknown")),
        "status": status,
        "executionLevel": "fixture",
        "evidence": [str(json_path)],
        "notes": (
            f"synthetic-fixture=true; profile={fault.get('profile')}; "
            f"verification={hints.get('verificationPolicy', 'unknown')}; observed={observed}; note={observation_note}"
        ),
    }


def execute_multi_source_case(case: dict[str, object], evidence_dir: Path) -> dict[str, object]:
    hints = case.get("executionHints", {})
    host_takeover = hints.get("hostTakeover", {}) if isinstance(hints, dict) else {}
    plan = host_takeover.get("multiSource", {}) if isinstance(host_takeover, dict) else {}
    urls = extract_probe_urls(case)
    if not urls:
        return {
            "caseId": str(case.get("caseId", "unknown")),
            "status": "blocked",
            "executionLevel": "shim-live",
            "evidence": [],
            "notes": "multi-source-unsupported=true; reason=no-source-urls",
        }
    result = run_multi_source_probe(
        urls,
        min_sources_required=int(plan.get("minSourcesRequired", 2)),
        dedupe_key=str(plan.get("dedupeKey", "title")),
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    case_id = str(case.get("caseId", "unknown")).lower()
    json_path = evidence_dir / f"{case_id}.multi-source.json"
    write_text(json_path, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return {
        "caseId": str(case.get("caseId", "unknown")),
        "status": "passed" if str(result.get("status")) == "passed" else "blocked",
        "executionLevel": "shim-live",
        "evidence": [str(json_path)],
        "notes": (
            f"multi-source=true; success-sources={result.get('successSourceCount', 0)}/{result.get('sourceCount', 0)}; "
            f"deduped-items={result.get('dedupedItemCount', 0)}"
        ),
    }


def execute_synthetic_dataset_case(case: dict[str, object], evidence_dir: Path) -> dict[str, object]:
    hints = case.get("executionHints", {})
    host_takeover = hints.get("hostTakeover", {}) if isinstance(hints, dict) else {}
    spec = host_takeover.get("syntheticDataset", {}) if isinstance(host_takeover, dict) else {}
    if not isinstance(spec, dict) or not bool(spec.get("enabled")):
        return {
            "caseId": str(case.get("caseId", "unknown")),
            "status": "blocked",
            "executionLevel": "fixture",
            "evidence": [],
            "notes": "synthetic-dataset-disabled=true",
        }
    dataset = build_dataset(spec)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    case_id = str(case.get("caseId", "unknown")).lower()
    json_path = evidence_dir / f"{case_id}.synthetic-dataset.json"
    write_text(json_path, json.dumps(dataset, ensure_ascii=False, indent=2) + "\n")
    return {
        "caseId": str(case.get("caseId", "unknown")),
        "status": "passed",
        "executionLevel": "fixture",
        "evidence": [str(json_path)],
        "notes": (
            f"synthetic-dataset=true; kind={dataset.get('kind')}; record-count={dataset.get('recordCount', 0)}; "
            f"duplicate-count={dataset.get('duplicateCount', 0)}"
        ),
    }


def recompute_surface_entry(entry: dict[str, object], surface: dict[str, object]) -> dict[str, object]:
    case_rows = coverage_case_map(entry)
    required_case_ids = [str(item) for item in surface.get("testCaseIds", []) if str(item).strip()]
    executed_case_ids: list[str] = []
    blocked_case_ids: list[str] = []
    incomplete_case_ids: list[str] = []
    for case_id in required_case_ids:
        row = case_rows.get(case_id)
        if row is None:
            blocked_case_ids.append(case_id)
            continue
        status = str(row.get("status", "pending"))
        if status != "pending":
            executed_case_ids.append(case_id)
        if status == "blocked":
            blocked_case_ids.append(case_id)
        elif status in {"pending", "incomplete"}:
            incomplete_case_ids.append(case_id)

    if blocked_case_ids:
        status = "blocked"
    elif incomplete_case_ids:
        status = "incomplete"
    else:
        status = "passed"

    entry["status"] = status
    entry["executionLevel"] = "shim-live"
    entry["requiredCaseIds"] = required_case_ids
    entry["executedCaseIds"] = executed_case_ids
    entry["executedCaseCount"] = len(executed_case_ids)
    return entry


def render_skill_results(plan: dict[str, object], coverage_map: dict[str, dict[str, object]]) -> str:
    lines = ["# TEST-EXECUTION/skill-results", ""]
    for index, surface in enumerate(plan.get("surfaces", []), start=1):
        if not isinstance(surface, dict):
            continue
        surface_id = str(surface.get("surfaceId", f"SURFACE-{index:02d}"))
        entry = coverage_map.get(surface_id, default_coverage_entry(surface))
        notes = [
            f"case-coverage={int(entry.get('executedCaseCount', 0))}/{len(entry.get('requiredCaseIds', []))}",
            f"executed-case-count={int(entry.get('executedCaseCount', 0))}",
        ]
        blocked_case_ids = [
            str(item.get("caseId", "")).strip()
            for item in entry.get("caseResults", [])
            if isinstance(item, dict) and str(item.get("status", "")) == "blocked"
        ]
        if blocked_case_ids:
            notes.append(f"blocked-cases={','.join(blocked_case_ids)}")
        lines.extend(
            [
                f"### {surface_id} takeover result",
                f"- surface-id: `{surface_id}`",
                "- execution-level: `shim-live`",
                f"- status: `{entry.get('status', 'pending')}`",
                f"- evidence: `{(entry.get('caseResults', [{}])[0].get('evidence', [''])[0] if entry.get('caseResults') else '')}`",
                f"- notes: `{' ; '.join(notes).replace(' ; ', '; ')}`",
                f"- executed-case-ids: `{', '.join(entry.get('executedCaseIds', [])) if entry.get('executedCaseIds') else ''}`",
                "",
            ]
        )
    return "\n".join(lines)


def remaining_case_lists(coverage: dict[str, object]) -> tuple[list[str], list[str]]:
    blocked: list[str] = []
    incomplete: list[str] = []
    surfaces = coverage.get("surfaces", [])
    if not isinstance(surfaces, list):
        return blocked, incomplete
    for surface in surfaces:
        if not isinstance(surface, dict):
            continue
        for row in surface.get("caseResults", []):
            if not isinstance(row, dict):
                continue
            case_id = str(row.get("caseId", "")).strip()
            if not case_id:
                continue
            status = str(row.get("status", "pending"))
            if status == "blocked":
                blocked.append(case_id)
            elif status in {"pending", "incomplete"}:
                incomplete.append(case_id)
    return blocked, incomplete


def write_remaining_case_reports(execution_dir: Path, blocked: list[str], incomplete: list[str]) -> tuple[str, str]:
    json_path = execution_dir / "REMAINING-CASES.json"
    md_path = execution_dir / "REMAINING-CASES.md"
    payload = {
        "remainingBlockedCases": blocked,
        "remainingIncompleteCases": incomplete,
        "totalRemainingCount": len(blocked) + len(incomplete),
    }
    write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# TEST-EXECUTION/remaining-cases",
        "",
        f"- remaining-blocked-count: `{len(blocked)}`",
        f"- remaining-incomplete-count: `{len(incomplete)}`",
        "",
        "## Remaining Blocked Cases",
        "",
    ]
    lines.extend([f"- `{case_id}`" for case_id in blocked] or ["- (none)"])
    lines.extend(["", "## Remaining Incomplete Cases", ""])
    lines.extend([f"- `{case_id}`" for case_id in incomplete] or ["- (none)"])
    write_text(md_path, "\n".join(lines) + "\n")
    return str(json_path), str(md_path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--takeover-file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    report_dir = Path(args.report_dir).expanduser().resolve()
    surface_plan_path = report_dir / "SURFACE-EXECUTION-PLAN.json"
    case_plan_path = report_dir / "CASE-EXECUTION-PLAN.json"
    if not surface_plan_path.exists():
        raise SystemExit(f"ERROR: surface plan does not exist: {surface_plan_path}")
    if not case_plan_path.exists():
        raise SystemExit(f"ERROR: case execution plan does not exist: {case_plan_path}")

    plan = load_json(surface_plan_path)
    case_plan = load_json(case_plan_path)
    execution_dir = report_dir / "TEST-EXECUTION"
    execution_dir.mkdir(parents=True, exist_ok=True)
    coverage_path = execution_dir / "SURFACE-COVERAGE.json"
    skill_results_path = execution_dir / "skill-results.md"
    coverage = load_json(coverage_path, {"generatedBy": "flow-a-host-takeover", "surfaces": []}) if coverage_path.exists() else {
        "generatedBy": "flow-a-host-takeover",
        "surfaces": [],
    }
    coverage_map = ensure_coverage(plan, coverage)
    surface_map = {
        str(surface.get("surfaceId", "")): surface for surface in plan.get("surfaces", []) if isinstance(surface, dict)
    }
    case_by_id = {
        str(case.get("caseId", "")): case for case in case_plan.get("cases", []) if isinstance(case, dict)
    }
    evidence_dir = execution_dir / "takeover-evidence"

    attempted = 0
    resolved = 0
    for surface_id, surface in surface_map.items():
        entry = coverage_map[surface_id]
        row_map = coverage_case_map(entry)
        for case_id in [str(item) for item in surface.get("testCaseIds", []) if str(item).strip()]:
            row = row_map.get(case_id)
            if row is None:
                row = {"caseId": case_id, "status": "pending", "evidence": []}
                entry["caseResults"].append(row)
                row_map[case_id] = row
            current_status = str(row.get("status", "pending"))
            if current_status not in {"pending", "blocked"}:
                continue
            case = case_by_id.get(case_id)
            if not isinstance(case, dict):
                continue
            attempted += 1
            hints = case.get("executionHints", {})
            host_takeover = hints.get("hostTakeover", {}) if isinstance(hints, dict) else {}
            strategy = str(host_takeover.get("strategy", "http-probe")) if isinstance(host_takeover, dict) else "http-probe"
            if strategy == "synthetic-dataset" or bool(hints.get("syntheticDataset", {}).get("enabled", False)):
                outcome = execute_synthetic_dataset_case(case, evidence_dir)
            elif strategy == "multi-source" or bool(hints.get("multiSource", {}).get("enabled", False)):
                outcome = execute_multi_source_case(case, evidence_dir)
            elif strategy == "browser-probe" or bool(hints.get("browserRequired", False)):
                outcome = execute_browser_case(case, evidence_dir)
            elif strategy == "fault-injection" or bool(hints.get("faultInjection", {}).get("enabled", False)):
                outcome = execute_fault_injection_case(case, evidence_dir)
            else:
                outcome = execute_http_case(case, evidence_dir)
            row["status"] = outcome["status"]
            row["evidence"] = list(outcome.get("evidence", []))
            row["notes"] = outcome.get("notes", "")
            if outcome["status"] != "blocked":
                resolved += 1
        recompute_surface_entry(entry, surface)

    write_text(coverage_path, json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")
    write_text(skill_results_path, render_skill_results(plan, coverage_map))
    remaining_blocked, remaining_incomplete = remaining_case_lists(coverage)
    remaining_json_path, remaining_md_path = write_remaining_case_reports(
        execution_dir,
        remaining_blocked,
        remaining_incomplete,
    )

    status = (
        "completed"
        if attempted > 0 and not remaining_blocked and not remaining_incomplete
        else ("partial" if attempted > 0 else "unsupported")
    )
    result = {
        "status": status,
        "attemptedCaseCount": attempted,
        "resolvedCaseCount": resolved,
        "remainingBlockedCases": remaining_blocked,
        "remainingIncompleteCases": remaining_incomplete,
        "resultFile": str(skill_results_path),
        "surfaceCoverageFile": str(coverage_path),
        "remainingCasesFile": remaining_json_path,
        "remainingCasesMarkdown": remaining_md_path,
        "note": (
            f"host takeover attempted {attempted} cases; resolved {resolved}; "
            f"remaining blocked={len(remaining_blocked)}; remaining incomplete={len(remaining_incomplete)}"
        ),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
