#!/usr/bin/env python3
"""Smoke tests for dispatch_payload_schema.py."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import json
import shutil
import subprocess
import sys
from pathlib import Path

from test_helpers import assert_contains, assert_equal, make_temp_root

import nexus_testing.dispatch_payload_schema as dispatch_payload_schema

PROJECT_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = PROJECT_DIR / "scripts" / "nexus_stage_executor.py"


def run_json(script: Path, *args: str) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert_equal(proc.returncode, 0, f"command exit code: {script.name} {' '.join(args)}")
    return json.loads(proc.stdout)


def test_real_dispatch_payloads_validate() -> None:
    temp_root = make_temp_root("dispatch-schema-")
    try:
        report_dir = temp_root / "reports"
        run_json(EXECUTOR, "init", "--report-dir", str(report_dir), "--flow", "skill")
        dispatched = run_json(EXECUTOR, "dispatch", "--report-dir", str(report_dir))
        payloads = dispatch_payload_schema.validate_dispatch_payload_list(dispatched["dispatchPayloads"])
        assert_equal(len(payloads), 1, "stage zero dispatch payload count")
        assert_equal(payloads[0]["artifactBaseDir"], str(report_dir.resolve()), "payload artifact base dir")
        assert_equal(payloads[0]["requiredArtifactPaths"], [], "payload required artifact paths")
        assert_equal(payloads[0]["upstreamOutputsVerified"], True, "payload upstream verification")
        bundled = run_json(EXECUTOR, "bundle-dispatch", "--report-dir", str(report_dir))
        manifest = json.loads((report_dir / "DISPATCH" / "stage-0" / "manifest.json").read_text(encoding="utf-8"))
        validated_manifest = dispatch_payload_schema.validate_bundle_manifest(manifest)
        dispatch_payload_schema.validate_bundle_files(Path(str(bundled["bundleDir"])), validated_manifest, payloads)
        print("  [PASS] test_real_dispatch_payloads_validate")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_invalid_dispatch_payload_rejected() -> None:
    invalid_payload = {
        "roleId": "quality-assessor",
        "roleFile": "roles/quality-assessor.md",
        "roleType": "validator",
        "order": 1,
        "stageId": "stage-2",
        "stageLabel": "阶段二",
        "stageName": "质量评估",
        "dispatchMode": "serial",
        "reportDir": "D:/tmp/report",
        "artifactBaseDir": "D:/tmp/report",
        "requiredArtifactPaths": ["D:/tmp/report/SPEC.md"],
        "upstreamOutputsVerified": True,
        "missingDeliverables": ["PRODUCT-QUALITY-REVIEW.md"],
        "inputSources": [],
        "inputs": [],
        "outputs": [],
        "consumers": [],
        "responsibilities": [],
        "executionRules": [],
        "evidenceRequirements": [],
        "antiPatterns": [],
        "hardBoundaries": [],
        "minimumOutput": ["规格完整性"],
        "validateMarkdownStructure": True,
        "minimumOutputAliases": {"缺失标题": "结论"},
        "mainAgentTakeoverPolicy": {},
        "description": "desc",
        "bestFor": [],
        "launchPrompt": "run it",
    }
    try:
        dispatch_payload_schema.validate_dispatch_payload(invalid_payload)
    except ValueError as exc:
        assert_contains(str(exc), "minimumOutputAliases source '缺失标题' must exist in minimumOutput", "invalid alias")
    else:
        raise AssertionError("invalid payload should raise ValueError")
    print("  [PASS] test_invalid_dispatch_payload_rejected")


def test_invalid_bundle_manifest_rejected() -> None:
    invalid_manifest = {
        "stageId": "stage-2",
        "stageLabel": "阶段二",
        "stageName": "质量评估",
        "dispatchMode": "serial",
        "status": "run-stage",
        "generatedAt": "2026-04-10 12:00:00",
        "roles": [
            {"roleId": "quality-assessor", "order": 1, "payloadFile": "01-quality-assessor.payload.json", "promptFile": "01-quality-assessor.prompt.md"},
            {"roleId": "quality-assessor", "order": 2, "payloadFile": "02-quality-assessor.payload.json", "promptFile": "02-quality-assessor.prompt.md"},
        ],
    }
    try:
        dispatch_payload_schema.validate_bundle_manifest(invalid_manifest)
    except ValueError as exc:
        assert_contains(str(exc), "duplicate roleId 'quality-assessor'", "duplicate role id")
    else:
        raise AssertionError("invalid manifest should raise ValueError")
    print("  [PASS] test_invalid_bundle_manifest_rejected")


def test_bundle_manifest_requires_payload_and_prompt_files() -> None:
    temp_root = make_temp_root("dispatch-schema-files-")
    try:
        bundle_dir = temp_root / "DISPATCH" / "stage-2"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        manifest = dispatch_payload_schema.validate_bundle_manifest(
            {
                "stageId": "stage-2",
                "stageLabel": "阶段二",
                "stageName": "质量评估",
                "dispatchMode": "serial",
                "status": "run-stage",
                "generatedAt": "2026-04-10 12:00:00",
                "roles": [
                    {
                        "roleId": "quality-assessor",
                        "order": 1,
                        "payloadFile": "01-quality-assessor.payload.json",
                        "promptFile": "01-quality-assessor.prompt.md",
                    }
                ],
            }
        )
        payloads = dispatch_payload_schema.validate_dispatch_payload_list(
            [
                {
                    "roleId": "quality-assessor",
                    "roleFile": "roles/quality-assessor.md",
                    "roleType": "validator",
                    "order": 1,
                    "stageId": "stage-2",
                    "stageLabel": "阶段二",
                    "stageName": "质量评估",
                    "dispatchMode": "serial",
                    "reportDir": "D:/tmp/report",
                    "artifactBaseDir": "D:/tmp/report",
                    "requiredArtifactPaths": ["D:/tmp/report/SPEC.md"],
                    "upstreamOutputsVerified": True,
                    "missingDeliverables": ["PRODUCT-QUALITY-REVIEW.md"],
                    "inputSources": ["SPEC.md"],
                    "inputs": ["SPEC.md"],
                    "outputs": ["PRODUCT-QUALITY-REVIEW.md"],
                    "consumers": ["test-designer"],
                    "responsibilities": ["评估需求完整性"],
                    "executionRules": [],
                    "evidenceRequirements": [],
                    "antiPatterns": [],
                    "hardBoundaries": [],
                    "minimumOutput": ["规格完整性"],
                    "validateMarkdownStructure": True,
                    "minimumOutputAliases": {},
                    "mainAgentTakeoverPolicy": {},
                    "description": "desc",
                    "bestFor": [],
                    "launchPrompt": "run it",
                }
            ]
        )
        try:
            dispatch_payload_schema.validate_bundle_files(bundle_dir, manifest, payloads)
        except ValueError as exc:
            assert_contains(str(exc), "payloadFile is missing", "missing payload file reported")
        else:
            raise AssertionError("bundle validation should reject missing payload/prompt files")
        print("  [PASS] test_bundle_manifest_requires_payload_and_prompt_files")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_dispatch_payload_requires_artifact_path_contract_fields() -> None:
    payload = {
        "roleId": "quality-assessor",
        "roleFile": "roles/quality-assessor.md",
        "roleType": "validator",
        "order": 1,
        "stageId": "stage-2",
        "stageLabel": "阶段二",
        "stageName": "质量评估",
        "dispatchMode": "serial",
        "reportDir": "D:/tmp/report",
        "artifactBaseDir": "",
        "requiredArtifactPaths": [],
        "upstreamOutputsVerified": True,
        "missingDeliverables": ["PRODUCT-QUALITY-REVIEW.md"],
        "inputSources": [],
        "inputs": [],
        "outputs": [],
        "consumers": [],
        "responsibilities": [],
        "executionRules": [],
        "evidenceRequirements": [],
        "antiPatterns": [],
        "hardBoundaries": [],
        "minimumOutput": ["结论"],
        "validateMarkdownStructure": True,
        "minimumOutputAliases": {},
        "mainAgentTakeoverPolicy": {},
        "description": "desc",
        "bestFor": [],
        "launchPrompt": "run it",
    }
    try:
        dispatch_payload_schema.validate_dispatch_payload(payload)
    except ValueError as exc:
        assert_contains(str(exc), "artifactBaseDir must be a non-empty string", "artifact base dir required")
    else:
        raise AssertionError("payload without artifact base dir should raise ValueError")
    print("  [PASS] test_dispatch_payload_requires_artifact_path_contract_fields")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    print("Dispatch Payload Schema Smoke Tests")
    print("=" * 40)
    for test in (
        test_real_dispatch_payloads_validate,
        test_invalid_dispatch_payload_rejected,
        test_invalid_bundle_manifest_rejected,
        test_bundle_manifest_requires_payload_and_prompt_files,
        test_dispatch_payload_requires_artifact_path_contract_fields,
    ):
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
