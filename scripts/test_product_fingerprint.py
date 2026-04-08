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


def build_rule_dense_fixture(base_dir: Path) -> Path:
    repo_dir = base_dir / "rule-dense-target"
    (repo_dir / "skills" / "agentguard").mkdir(parents=True, exist_ok=True)
    write_text(
        repo_dir / "package.json",
        json.dumps(
            {
                "name": "@example/agentguard-probe",
                "version": "2.4.0",
                "license": "Apache-2.0",
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
    )
    write_text(
        repo_dir / "skills" / "agentguard" / "SKILL.md",
        "\n".join(
            [
                "---",
                "name: agentguard-probe",
                "description: Rule-dense security skill fixture.",
                "argument-hint: \"[scan|action|patrol] [args...]\"",
                "---",
                "",
                "# AgentGuard Probe",
                "",
                "- **`scan <path>`** — inspect a target",
                "- **`action <request>`** — decide whether to allow a risky request",
                "- **`patrol`** — verify runtime health",
                "",
                "## Subcommand: scan",
                "",
                "### Rules",
                "- prompt-injection",
                "- credential-leak",
                "- command-injection",
                "- obfuscated-payload",
                "",
                "## Subcommand: action",
                "",
                "### Decision Paths",
                "- DENY",
                "- CONFIRM",
                "",
                "## Subcommand: patrol",
                "",
                "### Checks",
                "- runtime-hook-installed",
                "- policy-loaded",
                "- telemetry-emits",
                "",
            ]
        )
        + "\n",
    )
    return repo_dir


def build_companion_inventory_fixture(base_dir: Path) -> Path:
    repo_dir = base_dir / "companion-inventory-target"
    skill_dir = repo_dir / "skills" / "agentguard"
    src_dir = repo_dir / "src"
    skill_dir.mkdir(parents=True, exist_ok=True)
    src_dir.mkdir(parents=True, exist_ok=True)

    write_text(
        repo_dir / "package.json",
        json.dumps(
            {
                "name": "@example/agentguard-companion",
                "version": "3.1.0",
                "license": "MIT",
                "openclaw": {"extensions": ["./dist/index.js"]},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    write_text(
        skill_dir / "SKILL.md",
        "\n".join(
            [
                "---",
                "name: agentguard-companion",
                "description: Companion-doc inventory extraction fixture.",
                "argument-hint: \"[scan|action|patrol] [args...]\"",
                "---",
                "",
                "# AgentGuard Companion Fixture",
                "",
                "- **`scan <path>`** inspect a target path",
                "- **`action <request>`** decide whether to allow a risky request",
                "- **`patrol`** verify runtime health",
                "",
                "## Subcommand: scan",
                "",
                "Use all detection rules. See `scan-rules.md`.",
                "",
                "## Subcommand: action",
                "",
                "See `action-policies.md` for detector rules and decision logic.",
                "",
                "## Subcommand: patrol",
                "",
                "Run all patrol checks described in `patrol-checks.md`.",
                "",
            ]
        )
        + "\n",
    )
    write_text(
        skill_dir / "scan-rules.md",
        "\n".join(
            [
                "# Scan Rules",
                "",
                *[
                    f"## Rule {index}: RULE_{index:02d} (HIGH)"
                    for index in range(1, 25)
                ],
                "",
            ]
        ),
    )
    write_text(
        skill_dir / "action-policies.md",
        "\n".join(
            [
                "# Action Policies",
                "",
                "## Network Request Detector",
                "",
                "### Network Decision Logic",
                "1. Invalid URL -> DENY (high)",
                "2. Webhook domain -> DENY (high)",
                "3. High-risk TLD -> CONFIRM (medium)",
                "4. Allowlisted domain -> ALLOW (low)",
                "",
                "## Command Execution Detector",
                "",
                "### Exec Decision Logic",
                "1. Dangerous command -> DENY (critical)",
                "2. Safe command -> ALLOW (low)",
                "3. Sensitive data access -> CONFIRM (high)",
                "",
            ]
        )
        + "\n",
    )
    write_text(
        skill_dir / "patrol-checks.md",
        "\n".join(
            [
                "# Patrol Checks",
                "",
                *[
                    f"## Check {index}: Patrol Check {index}"
                    for index in range(1, 9)
                ],
                "",
            ]
        ),
    )
    write_text(
        src_dir / "scanner.ts",
        "\n".join(
            [
                "export const fallbackRules = ['FALLBACK_RULE_A', 'FALLBACK_RULE_B'];",
                "export const actionDecisions = ['ALLOW', 'DENY', 'CONFIRM'];",
                "export const patrolChecks = ['fallback-check-1', 'fallback-check-2'];",
            ]
        )
        + "\n",
    )
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


def test_nested_skill_target_keeps_repo_surfaces() -> None:
    temp_root = make_temp_root("fingerprint-nested-skill-")
    try:
        repo_dir = build_mixed_fixture(temp_root)
        nested_target = repo_dir / "skills" / "agentguard"
        payload = run_extractor(nested_target)

        assert_equal(payload.get("targetPath"), str(nested_target.resolve()), "nested target path")
        assert_equal(payload.get("resolvedRootPath"), str(repo_dir.resolve()), "resolved root path")
        assert_equal(payload.get("targetSkillPath"), "skills/agentguard", "target skill scope")

        product_type = payload.get("productType", [])
        for expected in ("skill", "package", "plugin", "cli", "mcp"):
            assert expected in product_type, f"missing nested target product type {expected}: {product_type}"

        entry_surfaces = json.dumps(payload.get("entrySurfaces", []), ensure_ascii=False)
        assert_contains(entry_surfaces, "skills/agentguard/SKILL.md", "nested skill entry surface")
        assert_contains(entry_surfaces, "agentguard-lite", "nested target bin entry surface")
        print("  [PASS] test_nested_skill_target_keeps_repo_surfaces")
    finally:
        import shutil

        shutil.rmtree(temp_root, ignore_errors=True)


def test_rule_dense_inventory_extraction() -> None:
    temp_root = make_temp_root("fingerprint-rule-dense-")
    try:
        repo_dir = build_rule_dense_fixture(temp_root)
        payload = run_extractor(repo_dir)
        capabilities = {
            str(item.get("name")): item for item in payload.get("capabilitySurfaces", [])
        }
        scan_groups = capabilities["scan"].get("scenarioGroups", [])
        action_groups = capabilities["action"].get("scenarioGroups", [])
        patrol_groups = capabilities["patrol"].get("scenarioGroups", [])

        assert_equal(len(scan_groups), 1, "scan scenario-group count")
        assert_equal(scan_groups[0].get("kind"), "rule", "scan scenario-group kind")
        assert_equal(len(scan_groups[0].get("items", [])), 4, "scan rule count")

        assert_equal(len(action_groups), 1, "action scenario-group count")
        assert_equal(action_groups[0].get("kind"), "decision", "action scenario-group kind")
        assert_equal(len(action_groups[0].get("items", [])), 2, "action decision count")

        assert_equal(len(patrol_groups), 1, "patrol scenario-group count")
        assert_equal(patrol_groups[0].get("kind"), "check", "patrol scenario-group kind")
        assert_equal(len(patrol_groups[0].get("items", [])), 3, "patrol check count")
        print("  [PASS] test_rule_dense_inventory_extraction")
    finally:
        import shutil

        shutil.rmtree(temp_root, ignore_errors=True)


def test_companion_inventory_extraction() -> None:
    temp_root = make_temp_root("fingerprint-companion-")
    try:
        repo_dir = build_companion_inventory_fixture(temp_root)
        payload = run_extractor(repo_dir)
        capabilities = {
            str(item.get("name")): item for item in payload.get("capabilitySurfaces", [])
        }
        scan_groups = capabilities["scan"].get("scenarioGroups", [])
        action_groups = capabilities["action"].get("scenarioGroups", [])
        patrol_groups = capabilities["patrol"].get("scenarioGroups", [])

        scan_rule_counts = [len(group.get("items", [])) for group in scan_groups if group.get("kind") == "rule"]
        assert 24 in scan_rule_counts, f"expected a 24-rule inventory, got {scan_rule_counts}"

        decision_items = [
            item
            for group in action_groups
            if group.get("kind") == "decision"
            for item in group.get("items", [])
        ]
        assert any("DENY" in str(item) for item in decision_items), f"missing DENY decision path: {decision_items}"
        assert any("CONFIRM" in str(item) for item in decision_items), f"missing CONFIRM decision path: {decision_items}"
        assert any("ALLOW" in str(item) for item in decision_items), f"missing ALLOW decision path: {decision_items}"

        patrol_check_counts = [len(group.get("items", [])) for group in patrol_groups if group.get("kind") == "check"]
        assert 8 in patrol_check_counts, f"expected an 8-check inventory, got {patrol_check_counts}"
        print("  [PASS] test_companion_inventory_extraction")
    finally:
        import shutil

        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    tests = [
        test_mixed_target,
        test_nested_skill_target_keeps_repo_surfaces,
        test_rule_dense_inventory_extraction,
        test_companion_inventory_extraction,
    ]
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
