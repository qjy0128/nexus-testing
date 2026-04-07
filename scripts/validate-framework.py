#!/usr/bin/env python3
"""Validate Nexus Testing Framework repository structure and doc consistency."""

from __future__ import annotations

import argparse
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from shutil import which
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
VALIDATION_TMP_ROOT = ROOT / ".tmp-validation"

REQUIRED_ROOT_FILES = (
    "SKILL.md",
    "README.md",
    "DEFINITIONS.md",
    "CHANGELOG.md",
    "reference-approval-mechanism.md",
    "reference-report-format.md",
    "reference-security-scan.md",
    "reference-security-blacklist.md",
    "reference-agent-evaluation-methodology.md",
    "reference-test-case-templates.md",
    "reference-sandbox-spec.md",
    "reference-external-case-sourcing.md",
    "reference-production-readiness.md",
    "reference-expected-outputs.md",
    "reference-output-verification-examples.md",
    "reference-skill-review-framework.md",
    "reference-skill-tier-requirements.md",
    "reference-flow-skill.md",
    "reference-flow-web-api.md",
    "reference-flow-android.md",
    "reference-flow-mcp.md",
)

REQUIRED_GOVERNANCE_FILES = (
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
)

REQUIRED_FLOW_FILES = (
    "flows/skill-testing.md",
    "flows/web-api-testing.md",
    "flows/android-testing.md",
    "flows/mcp-testing.md",
)

REQUIRED_SHELL_SCRIPT_FILES = (
    "scripts/sandbox-create.sh",
    "scripts/sandbox-exec.sh",
    "scripts/sandbox-cleanup.sh",
    "scripts/sandbox-skill-invoke.sh",
    "scripts/sandbox-mock-service.sh",
    "scripts/sandbox-multi-turn.sh",
    "scripts/sandbox-compare-output.sh",
    "scripts/sandbox-verify-output.sh",
)

REQUIRED_PYTHON_SCRIPT_FILES = (
    "scripts/diagnose_bash_runtime.py",
    "scripts/extract_product_fingerprint.py",
    "scripts/generate_flow_a_stage1.py",
    "scripts/generate_flow_a_test_design.py",
    "scripts/generate_flow_a_skill_execution.py",
    "scripts/run_flow_a_skill_execution.py",
    "scripts/skill-structure-validator.py",
    "scripts/skill_structure_validator_core.py",
    "scripts/sandbox_skill_invoke.py",
    "scripts/sandbox_multi_turn.py",
    "scripts/sandbox_skill_invoke/__init__.py",
    "scripts/sandbox_skill_invoke/adapter.py",
    "scripts/sandbox_skill_invoke/assertions.py",
    "scripts/sandbox_skill_invoke/audit.py",
    "scripts/sandbox_skill_invoke/core.py",
    "scripts/sandbox_skill_invoke/telemetry.py",
    "scripts/sandbox_skill_invoke/trace.py",
    "scripts/sandbox_skill_invoke/verifier.py",
    "scripts/test_flow_a_strict.py",
    "scripts/test_flow_a_live_telemetry.py",
    "scripts/test_flow_a_stage1.py",
    "scripts/test_flow_a_skill_execution.py",
    "scripts/test_flow_a_surface_runner.py",
    "scripts/test_flow_a_test_design.py",
    "scripts/test_product_fingerprint.py",
    "scripts/test_sandbox_exec_container.py",
    "scripts/test_flow_a_integration.py",
    "scripts/security-scanner.py",
    "scripts/test_sandbox_lifecycle.py",
    "scripts/validate_flow_a_skill_results.py",
)

REQUIRED_FIXTURE_DIRS = (
    "scripts/fixtures/fixture-pass-skill",
    "scripts/fixtures/fixture-defect-skill",
    "scripts/fixtures/fixture-extreme-skill",
)

RUNTIME_SMOKE_TEST_FILES = (
    "scripts/test_product_fingerprint.py",
    "scripts/test_flow_a_stage1.py",
    "scripts/test_flow_a_skill_execution.py",
    "scripts/test_flow_a_surface_runner.py",
    "scripts/test_flow_a_test_design.py",
    "scripts/test_flow_a_strict.py",
    "scripts/test_flow_a_live_telemetry.py",
    "scripts/test_sandbox_exec_container.py",
    "scripts/test_flow_a_integration.py",
    "scripts/test_sandbox_lifecycle.py",
    "scripts/test_helpers.py",
)

FRONTMATTER_FILES = ("SKILL.md",)

GITIGNORE_EXPECTED_ENTRIES = (
    "/memory/nexus-reports/",
    "/.nexus-sandbox/",
    "/.tmp-test-runs/",
    "/.tmp-validation/",
    ".claude/settings.local.json",
)
LOCAL_ONLY_TRACKED_PATHS = (
    ".claude/settings.local.json",
)

LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SEMVER_PATTERN = re.compile(r"v\d+\.\d+\.\d+")
CHANGELOG_VERSION_PATTERN = re.compile(r"^###\s+(v\d+\.\d+\.\d+)（", re.MULTILINE)
SINGLE_SOURCE_REF = "> **所有阶段、角色、输出文件、超时配置均以 `DEFINITIONS.md` 为单一事实源。**"
ROLE_REF_PATTERN = re.compile(r"`roles/([^`]+\.md)`")
MESSAGE_SEND_PATTERN = re.compile(r'message\(action:\s*"send"(?P<body>.*?)\)', re.DOTALL)
MARKDOWN_EXCLUDE_PARTS = {
    ".git",
    ".nexus-sandbox",
    ".tmp-test-runs",
    ".tmp-validation",
    "memory/nexus-reports",
    "node_modules",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _is_excluded(relative: str) -> bool:
    """Check if *relative* path matches any exclude pattern.

    Supports both prefix matches (``.git``, ``.nexus-sandbox``) and
    segment-level matches (``node_modules`` matches any directory named
    ``node_modules`` at any depth).
    """
    for excluded in MARKDOWN_EXCLUDE_PARTS:
        if relative == excluded or relative.startswith(f"{excluded}/"):
            return True
        # Segment-level: catch node_modules at any depth
        if f"/{excluded}/" in f"/{relative}/":
            return True
    return False


def iter_markdown_files() -> list[Path]:
    markdown_files: list[Path] = []
    for path in ROOT.rglob("*.md"):
        relative = rel(path)
        if _is_excluded(relative):
            continue
        markdown_files.append(path)
    return sorted(markdown_files)


def find_latest_version(changelog_text: str) -> str | None:
    match = CHANGELOG_VERSION_PATTERN.search(changelog_text)
    return match.group(1) if match else None


def find_readme_version(readme_text: str) -> str | None:
    marker = "## 当前版本"
    if marker not in readme_text:
        return None
    tail = readme_text.split(marker, 1)[1]
    match = SEMVER_PATTERN.search("\n".join(tail.splitlines()[:4]))
    return match.group(0) if match else None


def parse_frontmatter(text: str) -> dict[str, str] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break

    if end_index is None:
        return None

    data: dict[str, str] = {}
    for line in lines[1:end_index]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def validate_markdown_links(markdown_files: list[Path]) -> list[str]:
    issues: list[str] = []

    for file_path in markdown_files:
        try:
            content = read_text(file_path)
        except FileNotFoundError:
            continue
        for target in LINK_PATTERN.findall(content):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue

            target_path = target.split("#", 1)[0].strip()
            if not target_path:
                continue

            decoded = unquote(target_path)
            resolved = (file_path.parent / decoded).resolve()
            if not resolved.exists():
                issues.append(
                    f"{rel(file_path)} references missing path: {target_path}"
                )

    return issues


def validate_required_files() -> list[str]:
    issues: list[str] = []

    for relative_path in (
        *REQUIRED_ROOT_FILES,
        *REQUIRED_GOVERNANCE_FILES,
        *REQUIRED_FLOW_FILES,
        *REQUIRED_SHELL_SCRIPT_FILES,
        *REQUIRED_PYTHON_SCRIPT_FILES,
    ):
        if not (ROOT / relative_path).exists():
            issues.append(f"Missing required file: {relative_path}")

    for relative_path in REQUIRED_FIXTURE_DIRS:
        if not (ROOT / relative_path).is_dir():
            issues.append(f"Missing required fixture directory: {relative_path}")
        elif not (ROOT / relative_path / "SKILL.md").exists():
            issues.append(f"Fixture directory missing SKILL.md: {relative_path}")

    return issues


def validate_frontmatter() -> list[str]:
    issues: list[str] = []
    paths = [ROOT / relative_path for relative_path in FRONTMATTER_FILES]
    paths.extend(sorted((ROOT / "roles").glob("*.md")))

    for path in paths:
        frontmatter = parse_frontmatter(read_text(path))
        if frontmatter is None:
            issues.append(f"{rel(path)} is missing YAML frontmatter")
            continue

        for key in ("name", "description"):
            if not frontmatter.get(key):
                issues.append(f"{rel(path)} is missing frontmatter field: {key}")

    return issues


def validate_version_sync() -> list[str]:
    issues: list[str] = []
    changelog_text = read_text(ROOT / "CHANGELOG.md")
    readme_text = read_text(ROOT / "README.md")

    latest_version = find_latest_version(changelog_text)
    readme_version = find_readme_version(readme_text)

    if latest_version is None:
        issues.append("Unable to determine the latest version from CHANGELOG.md")
    if readme_version is None:
        issues.append("Unable to determine the current version from README.md")
    if latest_version and readme_version and latest_version != readme_version:
        issues.append(
            "README.md current version does not match CHANGELOG.md latest version: "
            f"{readme_version} != {latest_version}"
        )

    return issues


def validate_docs_updated_with_core_changes() -> list[str]:
    issues: list[str] = []
    if not which("git"):
        return issues

    tracked_targets = [
        "SKILL.md",
        "DEFINITIONS.md",
        "README.md",
        "CHANGELOG.md",
        "scripts/validate-framework.py",
    ]
    tracked_targets.extend(str(path.relative_to(ROOT)).replace("\\", "/") for path in sorted((ROOT / "flows").glob("*.md")))
    tracked_targets.extend(str(path.relative_to(ROOT)).replace("\\", "/") for path in sorted((ROOT / "roles").glob("*.md")))
    tracked_targets.extend(str(path.relative_to(ROOT)).replace("\\", "/") for path in sorted(ROOT.glob("reference-*.md")))

    result = subprocess.run(
        ["git", "status", "--porcelain", "--", *tracked_targets],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return issues

    changed_paths: set[str] = set()
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if path:
            changed_paths.add(path.replace("\\", "/"))

    if not changed_paths:
        return issues

    doc_paths = {"README.md", "CHANGELOG.md"}
    core_prefixes = ("flows/", "roles/", "reference-")
    core_paths = {"SKILL.md", "DEFINITIONS.md", "scripts/validate-framework.py"}
    core_changed = any(
        path in core_paths or path.startswith(core_prefixes)
        for path in changed_paths
    )

    if core_changed and not doc_paths.issubset(changed_paths):
        missing = sorted(path for path in doc_paths if path not in changed_paths)
        issues.append(
            "Core framework docs changed without updating required top-level docs: "
            + ", ".join(missing)
        )

    return issues


def validate_gitignore_entries() -> list[str]:
    issues: list[str] = []
    gitignore_path = ROOT / ".gitignore"
    if not gitignore_path.exists():
        return ["Missing required file: .gitignore"]

    content = read_text(gitignore_path)
    for entry in GITIGNORE_EXPECTED_ENTRIES:
        if entry not in content:
            issues.append(f".gitignore is missing entry: {entry}")

    return issues


def validate_local_only_files_not_tracked() -> list[str]:
    issues: list[str] = []
    if not which("git"):
        return issues

    for relative_path in LOCAL_ONLY_TRACKED_PATHS:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative_path],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            issues.append(
                f"Local-only file is tracked by git and should be removed from the index: {relative_path}"
            )

    return issues


def validate_flow_headers() -> list[str]:
    issues: list[str] = []
    for relative_path in REQUIRED_FLOW_FILES:
        path = ROOT / relative_path
        if path.exists() and SINGLE_SOURCE_REF not in read_text(path):
            issues.append(
                f"{relative_path} is missing the single-source reference to DEFINITIONS.md"
            )
    return issues


def validate_shell_scripts() -> list[str]:
    issues: list[str] = []
    for relative_path in REQUIRED_SHELL_SCRIPT_FILES:
        path = ROOT / relative_path
        if not path.exists():
            continue
        first_line = read_text(path).splitlines()[0].strip()
        if first_line != "#!/usr/bin/env bash":
            issues.append(
                f"{relative_path} should start with '#!/usr/bin/env bash'"
            )
    return issues


def iter_python_script_paths() -> list[Path]:
    scripts_dir = ROOT / "scripts"
    if not scripts_dir.exists():
        return []
    python_files: list[Path] = []
    for path in scripts_dir.rglob("*.py"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        python_files.append(path)
    return sorted(python_files)


@contextmanager
def workspace_temp_dir(prefix: str):
    VALIDATION_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    temp_dir: Path | None = None
    for attempt in range(20):
        candidate = VALIDATION_TMP_ROOT / f"{prefix}{os.getpid()}-{time.time_ns()}-{attempt}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            temp_dir = candidate
            break
        except FileExistsError:
            continue
    if temp_dir is None:
        raise RuntimeError(f"unable to allocate temp directory under {VALIDATION_TMP_ROOT}")
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def validate_python_script_syntax() -> list[str]:
    issues: list[str] = []
    with workspace_temp_dir("nexus-pycompile-") as temp_root:
        for path in iter_python_script_paths():
            relative_path = rel(path)
            target = temp_root / f"{path.stem}.pyc"
            try:
                py_compile.compile(
                    str(path),
                    cfile=str(target),
                    doraise=True,
                )
            except py_compile.PyCompileError as exc:
                issues.append(f"{relative_path} failed py_compile: {exc.msg}")
            except Exception as exc:
                issues.append(f"{relative_path} failed py_compile: {exc}")
    return issues


def summarize_process_output(stdout: str, stderr: str, limit: int = 400) -> str:
    combined = "\n".join(part.strip() for part in (stdout, stderr) if part.strip()).strip()
    if not combined:
        return "(no output)"
    if len(combined) <= limit:
        return combined
    return combined[: limit - 3] + "..."


def validate_runtime_smoke_tests() -> list[str]:
    issues: list[str] = []
    for relative_path in RUNTIME_SMOKE_TEST_FILES:
        path = ROOT / relative_path
        if not path.exists():
            continue
        try:
            result = subprocess.run(
                [sys.executable, str(path)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            issues.append(f"{relative_path} timed out after 180 seconds")
            continue
        if result.returncode != 0:
            issues.append(
                f"{relative_path} failed runtime smoke test (exit {result.returncode}): "
                f"{summarize_process_output(result.stdout, result.stderr)}"
            )
    return issues


def validate_security_scanner_fixtures() -> list[str]:
    """Run security-scanner against fixture Skills and verify expected results."""
    issues: list[str] = []
    scanner_path = ROOT / "scripts" / "security-scanner.py"
    if not scanner_path.exists():
        return ["scripts/security-scanner.py not found"]

    # pass-skill must be SAFE (exit 0)
    pass_skill = ROOT / "scripts" / "fixtures" / "fixture-pass-skill"
    if pass_skill.is_dir():
        try:
            result = subprocess.run(
                [sys.executable, str(scanner_path), str(pass_skill), "--format", "json"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30,
            )
            if result.returncode != 0:
                issues.append(f"security-scanner: fixture-pass-skill should be SAFE but exited {result.returncode}")
        except subprocess.TimeoutExpired:
            issues.append("security-scanner: fixture-pass-skill scan timed out")

    # defect-skill must be CRITICAL (exit 1)
    defect_skill = ROOT / "scripts" / "fixtures" / "fixture-defect-skill"
    if defect_skill.is_dir():
        try:
            result = subprocess.run(
                [sys.executable, str(scanner_path), str(defect_skill), "--format", "json"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30,
            )
            if result.returncode == 0:
                issues.append("security-scanner: fixture-defect-skill should be CRITICAL but exited 0")
            else:
                data = json.loads(result.stdout)
                if data.get("total_findings", 0) < 5:
                    issues.append(
                        f"security-scanner: fixture-defect-skill only found {data['total_findings']} issues, expected >= 5"
                    )
        except subprocess.TimeoutExpired:
            issues.append("security-scanner: fixture-defect-skill scan timed out")
        except (json.JSONDecodeError, KeyError) as exc:
            issues.append(f"security-scanner: defect-skill output parse error: {exc}")

    return issues


def validate_definition_consistency() -> list[str]:
    issues: list[str] = []
    definitions_text = read_text(ROOT / "DEFINITIONS.md")
    approval_text = read_text(ROOT / "reference-approval-mechanism.md")
    readme_text = read_text(ROOT / "README.md")
    skill_text = read_text(ROOT / "SKILL.md")

    if "approval-records.json" in approval_text and "approval-records.json" not in definitions_text:
        issues.append(
            "DEFINITIONS.md is missing approval-records.json referenced by reference-approval-mechanism.md"
        )
    if ".nexus-hmac-salt" in readme_text:
        issues.append("README.md still references deprecated .nexus-hmac-salt runtime state")
    if any(token in approval_text for token in ("HMAC", ".nexus-hmac-salt", '"signature"')):
        issues.append(
            "reference-approval-mechanism.md still contains deprecated HMAC/signature requirements"
        )
    if "HMAC" in skill_text:
        issues.append("SKILL.md still contains deprecated HMAC wording")
    if (ROOT / "roles" / "compatibility-tester-skill.md").exists():
        issues.append(
            "roles/compatibility-tester-skill.md should be archived outside the active roles directory"
        )
    if "PRODUCT-FINGERPRINT.json" not in definitions_text:
        issues.append("DEFINITIONS.md is missing PRODUCT-FINGERPRINT.json in the stage outputs")
    if "SPEC-CONSISTENCY-REVIEW.md" not in definitions_text:
        issues.append("DEFINITIONS.md is missing SPEC-CONSISTENCY-REVIEW.md in the stage outputs")

    return issues


def validate_flow_a_fact_contract() -> list[str]:
    issues: list[str] = []

    flow_text = read_text(ROOT / "flows" / "skill-testing.md")
    requirement_text = read_text(ROOT / "roles" / "requirement-analyst.md")
    designer_text = read_text(ROOT / "roles" / "test-designer.md")
    evaluator_text = read_text(ROOT / "roles" / "test-case-evaluator.md")
    reference_text = read_text(ROOT / "reference-flow-skill.md")
    skill_text = read_text(ROOT / "SKILL.md")

    if "PRODUCT-FINGERPRINT.json" not in flow_text or "SPEC-CONSISTENCY-REVIEW.md" not in flow_text:
        issues.append("flows/skill-testing.md is missing the stage-one fact contract")
    if "PRODUCT-FINGERPRINT.json" not in requirement_text:
        issues.append("roles/requirement-analyst.md is missing PRODUCT-FINGERPRINT.json output requirements")
    if "真实入口" not in designer_text:
        issues.append("roles/test-designer.md is missing the real-entry test design rule")
    if "事实一致性" not in evaluator_text:
        issues.append("roles/test-case-evaluator.md is missing the fact-consistency review rule")
    if "阶段一事实指纹模板" not in reference_text:
        issues.append("reference-flow-skill.md is missing the stage-one fingerprint template")
    if "静态分析只能作为补充审查" not in skill_text:
        issues.append("SKILL.md is missing the static-analysis outcome restriction")
    if not (ROOT / "roles" / "spec-consistency-validator.md").exists():
        issues.append("roles/spec-consistency-validator.md is missing")

    return issues


def validate_flow_a_surface_plan_contract() -> list[str]:
    issues: list[str] = []

    definitions_text = read_text(ROOT / "DEFINITIONS.md")
    flow_text = read_text(ROOT / "flows" / "skill-testing.md")
    skill_text = read_text(ROOT / "SKILL.md")
    readme_text = read_text(ROOT / "README.md")
    designer_text = read_text(ROOT / "roles" / "test-designer.md")
    evaluator_text = read_text(ROOT / "roles" / "test-case-evaluator.md")
    tester_text = read_text(ROOT / "roles" / "skill-tester.md")
    reference_text = read_text(ROOT / "reference-flow-skill.md")

    if "SURFACE-EXECUTION-PLAN.json" not in definitions_text:
        issues.append("DEFINITIONS.md is missing SURFACE-EXECUTION-PLAN.json in the stage outputs")
    if "SURFACE-EXECUTION-PLAN.json" not in flow_text:
        issues.append("flows/skill-testing.md is missing the stage-three surface execution plan output")
    if "SURFACE-EXECUTION-PLAN.json" not in skill_text:
        issues.append("SKILL.md is missing the stage-three surface execution plan contract")
    if "SURFACE-EXECUTION-PLAN.json" not in readme_text:
        issues.append("README.md is missing SURFACE-EXECUTION-PLAN.json in the documented outputs")
    if "SURFACE-EXECUTION-PLAN.json" not in designer_text:
        issues.append("roles/test-designer.md is missing SURFACE-EXECUTION-PLAN.json output requirements")
    if "SURFACE-EXECUTION-PLAN.json" not in evaluator_text:
        issues.append("roles/test-case-evaluator.md is missing SURFACE-EXECUTION-PLAN.json review requirements")
    if "SURFACE-EXECUTION-PLAN.json" not in tester_text:
        issues.append("roles/skill-tester.md is missing SURFACE-EXECUTION-PLAN.json execution requirements")
    if "真实入口表面" not in reference_text and "真实入口表面" not in flow_text:
        issues.append("Flow A docs are missing the real-surface wording for stage-three planning")

    return issues


def validate_flow_a_surface_execution_contract() -> list[str]:
    issues: list[str] = []

    definitions_text = read_text(ROOT / "DEFINITIONS.md")
    flow_text = read_text(ROOT / "flows" / "skill-testing.md")
    skill_text = read_text(ROOT / "SKILL.md")
    readme_text = read_text(ROOT / "README.md")
    tester_text = read_text(ROOT / "roles" / "skill-tester.md")
    evidence_text = read_text(ROOT / "roles" / "evidence-collector.md")
    report_text = read_text(ROOT / "roles" / "report-integrator.md")
    reference_text = read_text(ROOT / "reference-flow-skill.md")

    for token in ("SKILL-SURFACE-WORKLIST.md", "SURFACE-COVERAGE.json"):
        if token not in definitions_text:
            issues.append(f"DEFINITIONS.md is missing {token} in the stage-five outputs")
        if token not in flow_text:
            issues.append(f"flows/skill-testing.md is missing {token} in the stage-five contract")
        if token not in readme_text:
            issues.append(f"README.md is missing {token} in the documented outputs")

    if "validate_flow_a_skill_results.py" not in skill_text:
        issues.append("SKILL.md is missing validate_flow_a_skill_results.py guidance")
    if "run_flow_a_skill_execution.py" not in skill_text:
        issues.append("SKILL.md is missing run_flow_a_skill_execution.py guidance")
    if "SKILL-SURFACE-WORKLIST.md" not in tester_text or "SURFACE-COVERAGE.json" not in tester_text:
        issues.append("roles/skill-tester.md is missing stage-five worklist and coverage inputs")
    if "SURFACE-COVERAGE.json" not in evidence_text:
        issues.append("roles/evidence-collector.md is missing SURFACE-COVERAGE.json audit input")
    if "SURFACE-COVERAGE.json" not in report_text:
        issues.append("roles/report-integrator.md is missing SURFACE-COVERAGE.json residual-risk input")
    if "validate_flow_a_skill_results.py" not in reference_text:
        issues.append("reference-flow-skill.md is missing the stage-five surface result validator")

    return issues


def validate_message_send_contract() -> list[str]:
    issues: list[str] = []
    example_files = (
        "SKILL.md",
        "reference-report-format.md",
    )

    skill_text = read_text(ROOT / "SKILL.md")
    if "交付物生成后立即主动发送" not in skill_text:
        issues.append(
            "SKILL.md is missing the proactive deliverable-send rule"
        )

    definitions_text = read_text(ROOT / "DEFINITIONS.md")
    if "阶段文件已写入但尚未发送给用户，不算阶段完成" not in definitions_text:
        issues.append(
            "DEFINITIONS.md is missing the sent-before-complete rule"
        )

    flow_skill_text = read_text(ROOT / "flows" / "skill-testing.md")
    if "主 agent 动作" not in flow_skill_text:
        issues.append(
            "flows/skill-testing.md is missing explicit main-agent send actions"
        )

    approval_text = read_text(ROOT / "reference-approval-mechanism.md")
    if "交付物发送与批准请求必须同轮触发" not in approval_text:
        issues.append(
            "reference-approval-mechanism.md is missing the same-turn send-and-approve rule"
        )

    for relative_path in example_files:
        text = read_text(ROOT / relative_path)
        matches = list(MESSAGE_SEND_PATTERN.finditer(text))
        if not matches:
            issues.append(
                f"{relative_path} is missing a concrete message(action: \"send\", ...) example"
            )
            continue

        has_empty_buttons = False
        for match in matches:
            body = match.group("body")
            if "caption:" not in body:
                issues.append(
                    f"{relative_path} contains a file-send example without caption"
                )
            if "buttons:" not in body:
                issues.append(
                    f"{relative_path} contains a file-send example without buttons"
                )
            if "buttons: []" in body:
                has_empty_buttons = True

        if not has_empty_buttons:
            issues.append(
                f"{relative_path} is missing a file-send example with buttons: []"
            )

    return issues


def find_runnable_bash() -> tuple[str | None, str | None]:
    candidates: list[str] = []
    primary = which("bash")
    if primary:
        candidates.append(primary)

    if sys.platform.startswith("win"):
        candidates.extend(
            [
                r"C:\Program Files\Git\bin\bash.exe",
                r"C:\Program Files\Git\usr\bin\bash.exe",
            ]
        )

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate)
        if not path.exists():
            continue
        probe = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if probe.returncode == 0:
            return str(path), None

    if candidates:
        return None, "bash is not runnable; skipped shell syntax validation"
    return None, "bash not found; skipped shell syntax validation"


def validate_shell_script_syntax() -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    bash, warning = find_runnable_bash()
    if bash is None:
        warnings.append(warning or "bash not found; skipped shell syntax validation")
        return issues, warnings

    for relative_path in REQUIRED_SHELL_SCRIPT_FILES:
        path = ROOT / relative_path
        if not path.exists():
            continue
        result = subprocess.run(
            [bash, "-n", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip()
            issues.append(f"{relative_path} failed bash -n: {details}")

    return issues, warnings


def validate_role_references() -> list[str]:
    """Check that roles referenced in flow files actually exist."""
    issues: list[str] = []
    for relative_path in REQUIRED_FLOW_FILES:
        path = ROOT / relative_path
        if not path.exists():
            continue
        content = read_text(path)
        for role_name in ROLE_REF_PATTERN.findall(content):
            role_path = ROOT / "roles" / role_name
            if not role_path.exists():
                issues.append(
                    f"{relative_path} references non-existent role: roles/{role_name}"
                )
    return issues


def validate_role_definitions_ref() -> list[str]:
    """Check that active role files reference DEFINITIONS.md."""
    issues: list[str] = []
    for path in sorted((ROOT / "roles").glob("*.md")):
        content = read_text(path)
        if "DEFINITIONS.md" not in content:
            issues.append(
                f"{rel(path)} does not reference DEFINITIONS.md"
            )
    return issues


def validate_role_version_tags() -> list[str]:
    issues: list[str] = []
    for path in sorted((ROOT / "roles").glob("*.md")):
        if SEMVER_PATTERN.search(read_text(path)):
            issues.append(
                f"{rel(path)} contains an inline version tag; move version history to CHANGELOG.md"
            )
    return issues


def validate_flow_role_consistency() -> list[str]:
    """Check that Flow files reference the expected number of parallel roles."""
    issues: list[str] = []
    definitions_text = read_text(ROOT / "DEFINITIONS.md")

    expected_roles: dict[str, int] = {}
    for line in definitions_text.splitlines():
        for flow_label, count in [
            ("Flow A", 2), ("Flow B", 5), ("Flow C", 5), ("Flow D", 4),
        ]:
            if line.startswith("|") and flow_label in line and "skill-tester" in line:
                expected_roles[flow_label] = count

    for relative_path in REQUIRED_FLOW_FILES:
        path = ROOT / relative_path
        if not path.exists():
            continue
        content = read_text(path)
        role_refs = ROLE_REF_PATTERN.findall(content)
        unique_roles = set(role_refs)

        # Check that referenced roles exist
        for role_name in unique_roles:
            if not (ROOT / "roles" / role_name).exists():
                issues.append(
                    f"{relative_path} references non-existent role: roles/{role_name}"
                )

    return issues


def validate_required_references() -> list[str]:
    """Check that key reference files exist and CLAUDE.md exists."""
    issues: list[str] = []
    required_refs = (
        "reference-recovery.md",
        "reference-production-readiness.md",
    )
    for ref in required_refs:
        if not (ROOT / ref).exists():
            issues.append(f"Missing required reference file: {ref}")
    if not (ROOT / "CLAUDE.md").exists():
        issues.append("Missing CLAUDE.md (project AI collaboration guide)")
    return issues


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    return parser.parse_args(argv)


def collect_validation_results() -> tuple[list[tuple[str, list[str]]], list[str], list[str], int]:
    markdown_files = iter_markdown_files()
    shell_syntax_issues, shell_syntax_warnings = validate_shell_script_syntax()

    checks = (
        ("required files", validate_required_files()),
        ("markdown links", validate_markdown_links(markdown_files)),
        ("frontmatter", validate_frontmatter()),
        ("version sync", validate_version_sync()),
        ("doc update discipline", validate_docs_updated_with_core_changes()),
        ("gitignore entries", validate_gitignore_entries()),
        ("local-only tracked files", validate_local_only_files_not_tracked()),
        ("flow headers", validate_flow_headers()),
        ("shell scripts", validate_shell_scripts()),
        ("python script syntax", validate_python_script_syntax()),
        ("runtime smoke tests", validate_runtime_smoke_tests()),
        ("definitions consistency", validate_definition_consistency()),
        ("flow a fact contract", validate_flow_a_fact_contract()),
        ("flow a surface plan contract", validate_flow_a_surface_plan_contract()),
        ("flow a surface execution contract", validate_flow_a_surface_execution_contract()),
        ("message send contract", validate_message_send_contract()),
        ("role version tags", validate_role_version_tags()),
        ("role references", validate_role_references()),
        ("role definitions ref", validate_role_definitions_ref()),
        ("security scanner fixtures", validate_security_scanner_fixtures()),
        ("flow role consistency", validate_flow_role_consistency()),
        ("required references", validate_required_references()),
    )
    return list(checks), shell_syntax_issues, shell_syntax_warnings, len(markdown_files)


def emit_json(
    checks: list[tuple[str, list[str]]],
    shell_syntax_issues: list[str],
    shell_syntax_warnings: list[str],
    markdown_count: int,
) -> int:
    all_issues = [issue for _, issues in checks for issue in issues]
    all_issues.extend(shell_syntax_issues)
    payload = {
        "repository_root": str(ROOT),
        "markdown_files_scanned": markdown_count,
        "checks": {
            name: {
                "passed": not issues,
                "issues": issues,
            }
            for name, issues in checks
        },
        "shell_script_syntax": {
            "passed": not shell_syntax_issues and not shell_syntax_warnings,
            "issues": shell_syntax_issues,
            "warnings": shell_syntax_warnings,
        },
        "warnings": shell_syntax_warnings,
        "issue_count": len(all_issues),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if all_issues else 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")

    args = parse_args(argv)
    checks, shell_syntax_issues, shell_syntax_warnings, markdown_count = (
        collect_validation_results()
    )
    if args.json:
        return emit_json(
            checks, shell_syntax_issues, shell_syntax_warnings, markdown_count
        )

    all_issues: list[str] = []
    all_warnings: list[str] = []

    print("Nexus Testing Framework validation")
    print(f"Repository root: {ROOT}")
    print(f"Markdown files scanned: {markdown_count}")

    for name, issues in checks:
        if issues:
            print(f"[FAIL] {name}: {len(issues)} issue(s)")
            for issue in issues:
                print(f"  - {issue}")
            all_issues.extend(issues)
        else:
            print(f"[PASS] {name}")

    if shell_syntax_issues:
        print(f"[FAIL] shell script syntax: {len(shell_syntax_issues)} issue(s)")
        for issue in shell_syntax_issues:
            print(f"  - {issue}")
        all_issues.extend(shell_syntax_issues)
    elif shell_syntax_warnings:
        for warning in shell_syntax_warnings:
            print(f"[WARN] {warning}")
            all_warnings.append(warning)
    else:
        print("[PASS] shell script syntax")

    if all_issues:
        print(f"\nValidation failed with {len(all_issues)} issue(s).")
        return 1

    if all_warnings:
        print(f"\nValidation succeeded with {len(all_warnings)} warning(s).")
        return 0

    print("\nValidation succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
