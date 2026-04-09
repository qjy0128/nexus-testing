#!/usr/bin/env python3
"""Mock external runtime for nexus_runtime_bridge.py smoke tests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROLE_OUTPUTS = {
    "environment-checker": ["RUNS/{stage_id}/environment-readiness.md"],
    "requirement-analyst": ["PRODUCT-FINGERPRINT.json", "SPEC.md"],
    "spec-consistency-validator": ["SPEC-CONSISTENCY-REVIEW.md"],
    "quality-assessor": ["PRODUCT-QUALITY-REVIEW.md"],
    "test-designer": ["TEST-DESIGN.md", "SURFACE-EXECUTION-PLAN.json"],
    "test-case-evaluator": ["TEST-CASE-REVIEW.md"],
    "skill-tester": [
        "TEST-EXECUTION/skill-results.md",
        "TEST-EXECUTION/SKILL-SURFACE-WORKLIST.md",
        "TEST-EXECUTION/SURFACE-COVERAGE.json",
    ],
    "security-tester": ["TEST-EXECUTION/security-results.md"],
    "functional-tester": ["TEST-EXECUTION/functional-results.md"],
    "compatibility-tester": ["TEST-EXECUTION/compatibility-results.md"],
    "performance-tester": ["TEST-EXECUTION/performance-results.md"],
    "accessibility-auditor": ["TEST-EXECUTION/accessibility-results.md"],
    "reality-checker": ["TEST-EXECUTION/reality-results.md"],
    "mcp-tester": ["TEST-EXECUTION/mcp-results.md"],
    "evidence-collector": ["DEFECTS/evidence-collection.md"],
    "defect-analyst": ["DEFECTS/DEFECT-REPORT.md"],
    "report-integrator": ["FINAL-TEST-REPORT.md"],
    "experience-tester-a": [
        "EXPERIENCE/experience-report-a.md",
        "EXPERIENCE/cross-check-b-by-a.md",
    ],
    "experience-tester-b": [
        "EXPERIENCE/experience-report-b.md",
        "EXPERIENCE/cross-check-a-by-b.md",
    ],
}


def write_role_output(path: Path, role_id: str, stage_id: str) -> None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = {"generatedBy": role_id, "stageId": stage_id, "status": "mock"}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    path.write_text(f"# Mock Output\n\nrole={role_id}\nstage={stage_id}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-file", required=True)
    parser.add_argument("--prompt-file")
    parser.add_argument("--fail-role")
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    role_id = str(payload["roleId"])
    stage_id = str(payload["stageId"])
    report_dir = Path(str(payload["reportDir"]))

    if args.fail_role and args.fail_role == role_id:
        print(f"mock failure for {role_id}", file=sys.stderr)
        return 7

    outputs = ROLE_OUTPUTS.get(role_id, [])
    created: list[str] = []
    for relative in outputs:
        resolved = report_dir / relative.format(stage_id=stage_id)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        write_role_output(resolved, role_id, stage_id)
        created.append(str(resolved))

    result = {
        "resultFile": created[0] if created else None,
        "note": f"mock runtime completed for {role_id}",
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
