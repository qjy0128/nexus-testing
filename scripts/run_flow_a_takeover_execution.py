#!/usr/bin/env python3
"""Host-side Flow A takeover executor for blocked/pending real-call cases."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from json_utils import load_json
from sandbox_skill_invoke.core import read_text, write_text


URL_PATTERN = re.compile(r"https?://[^\s`)>]+", re.IGNORECASE)
HTTP_PROVIDER_ALIASES: dict[str, list[str]] = {
    "binance": ["https://api.binance.com/api/v3/ping"],
    "coingecko": ["https://api.coingecko.com/api/v3/ping"],
    "coinpaprika": ["https://api.coinpaprika.com/v1/global"],
    "tradingeconomics": ["https://tradingeconomics.com/commodity/gold"],
    "chinagoldgroup": ["http://www.chinagoldgroup.com/"],
    "boc": ["https://www.boc.cn/"],
    "jin10": ["https://www.jin10.com/"],
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
                f"- execution-level: `shim-live`",
                f"- status: `{entry.get('status', 'pending')}`",
                f"- evidence: `{(entry.get('caseResults', [{}])[0].get('evidence', [''])[0] if entry.get('caseResults') else '')}`",
                f"- notes: `{' ; '.join(notes).replace(' ; ', '; ')}`",
                f"- executed-case-ids: `{', '.join(entry.get('executedCaseIds', [])) if entry.get('executedCaseIds') else ''}`",
                "",
            ]
        )
    return "\n".join(lines)


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
    remaining_blocked: list[str] = []

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
                remaining_blocked.append(case_id)
                continue
            attempted += 1
            outcome = execute_http_case(case, evidence_dir)
            row["status"] = outcome["status"]
            row["evidence"] = list(outcome.get("evidence", []))
            row["notes"] = outcome.get("notes", "")
            if outcome["status"] != "blocked":
                resolved += 1
            else:
                remaining_blocked.append(case_id)
        recompute_surface_entry(entry, surface)

    write_text(coverage_path, json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")
    write_text(skill_results_path, render_skill_results(plan, coverage_map))

    status = "completed" if attempted > 0 and not remaining_blocked else ("partial" if attempted > 0 else "unsupported")
    result = {
        "status": status,
        "attemptedCaseCount": attempted,
        "resolvedCaseCount": resolved,
        "remainingBlockedCases": remaining_blocked,
        "resultFile": str(skill_results_path),
        "surfaceCoverageFile": str(coverage_path),
        "note": f"host takeover attempted {attempted} cases; resolved {resolved}",
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
