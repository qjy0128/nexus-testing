#!/usr/bin/env python3
"""Validate Nexus Testing Framework repository structure and doc consistency."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

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

from nexus_testing.frontmatter_utils import parse_frontmatter
from nexus_testing.role_metadata import (
    validate_frontmatter_schema as validate_role_frontmatter_schema,
)
from nexus_testing.sandbox_skill_invoke.core import (
    find_bash_executable as _core_find_bash_executable,
)
from nexus_testing.sandbox_skill_invoke.core import (
    read_text as _core_read_text,
)
from nexus_testing.validate_contracts import (
    validate_claude_runtime_contract,
    validate_definition_consistency,
    validate_dispatch_runner_contract,
    validate_flow_a_case_depth_contract,
    validate_flow_a_fact_contract,
    validate_flow_a_runtime_harness_contract,
    validate_flow_a_surface_execution_contract,
    validate_flow_a_surface_plan_contract,
    validate_message_send_contract,
    validate_openclaw_demo_contract,
    validate_openclaw_runtime_contract,
    validate_output_language_contract,
    validate_product_type_normalization,
    validate_required_references,
    validate_role_definitions_ref,
    validate_role_version_tags,
    validate_runtime_bridge_contract,
    validate_stage_executor_contract,
    validate_stage_subagent_plan_contract,
)
from nexus_testing.validate_contracts import (
    validate_flow_role_consistency as _validate_flow_role_consistency,
)
from nexus_testing.validate_contracts import (
    validate_role_references as _validate_role_references,
)

ROOT = Path(__file__).resolve().parents[1]
VALIDATION_TMP_ROOT = ROOT / ".tmp-validation"
VALIDATION_MANIFEST_FILE = ROOT / "validation-manifest.json"


def _string_list(payload: object, field: str) -> tuple[str, ...]:
    if not isinstance(payload, list):
        raise SystemExit(f"ERROR: validation manifest {field} must be a list")
    values = tuple(str(item).strip() for item in payload if str(item).strip())
    if len(values) != len(payload):
        raise SystemExit(f"ERROR: validation manifest {field} contains empty entries")
    return values


def load_validation_manifest() -> dict[str, tuple[str, ...]]:
    if not VALIDATION_MANIFEST_FILE.exists():
        raise SystemExit(f"ERROR: validation manifest is missing: {VALIDATION_MANIFEST_FILE}")
    try:
        payload = json.loads(VALIDATION_MANIFEST_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: invalid JSON in validation manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("ERROR: validation manifest must be a JSON object")
    fields = (
        "requiredRootFiles",
        "requiredReferenceFiles",
        "requiredGovernanceFiles",
        "requiredFlowFiles",
        "requiredShellScriptFiles",
        "requiredPythonScriptFiles",
        "requiredSrcPackageFiles",
        "requiredTestFiles",
        "requiredFixtureDirs",
        "criticalRuntimeSmokeTests",
    )
    return {field: _string_list(payload.get(field, []), field) for field in fields}


VALIDATION_MANIFEST = load_validation_manifest()
REQUIRED_ROOT_FILES = VALIDATION_MANIFEST["requiredRootFiles"]
REQUIRED_REFERENCE_FILES = VALIDATION_MANIFEST["requiredReferenceFiles"]
REQUIRED_GOVERNANCE_FILES = VALIDATION_MANIFEST["requiredGovernanceFiles"]
REQUIRED_FLOW_FILES = VALIDATION_MANIFEST["requiredFlowFiles"]
REQUIRED_SHELL_SCRIPT_FILES = VALIDATION_MANIFEST["requiredShellScriptFiles"]
REQUIRED_PYTHON_SCRIPT_FILES = VALIDATION_MANIFEST["requiredPythonScriptFiles"]
REQUIRED_SRC_PACKAGE_FILES = VALIDATION_MANIFEST["requiredSrcPackageFiles"]
REQUIRED_TEST_FILES = VALIDATION_MANIFEST["requiredTestFiles"]
REQUIRED_FIXTURE_DIRS = VALIDATION_MANIFEST["requiredFixtureDirs"]
CRITICAL_RUNTIME_SMOKE_TESTS = VALIDATION_MANIFEST["criticalRuntimeSmokeTests"]

RUNTIME_SMOKE_TEST_TIMEOUTS = {
    "tests/test_flow_a_surface_runner.py": 300,
}

FRONTMATTER_FILES = ("SKILL.md",)

GITIGNORE_EXPECTED_ENTRIES = (
    "/memory/nexus-reports/",
    "!/memory/nexus-reports/.gitkeep",
    "/files/",
    "!/files/.gitkeep",
    "/.nexus-sandbox/",
    "/.tmp/",
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
MARKDOWN_EXCLUDE_PARTS = {
    ".git",
    ".nexus-sandbox",
    ".tmp-test-runs",
    ".tmp-validation",
    "memory/nexus-reports",
    "node_modules",
}


read_text = _core_read_text


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
    matches = CHANGELOG_VERSION_PATTERN.findall(changelog_text)
    if not matches:
        return None

    def semver_key(version: str) -> tuple[int, int, int]:
        major, minor, patch = version.lstrip("v").split(".")
        return int(major), int(minor), int(patch)

    return max(matches, key=semver_key)


def find_readme_version(readme_text: str) -> str | None:
    marker = "## 当前版本"
    if marker not in readme_text:
        return None
    tail = readme_text.split(marker, 1)[1]
    match = SEMVER_PATTERN.search("\n".join(tail.splitlines()[:4]))
    return match.group(0) if match else None


def find_pyproject_version(pyproject_text: str) -> str | None:
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE)
    return match.group(1) if match else None


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
        *REQUIRED_REFERENCE_FILES,
        *REQUIRED_GOVERNANCE_FILES,
        *REQUIRED_FLOW_FILES,
        *REQUIRED_SHELL_SCRIPT_FILES,
        *REQUIRED_PYTHON_SCRIPT_FILES,
        *REQUIRED_SRC_PACKAGE_FILES,
        *REQUIRED_TEST_FILES,
    ):
        if not (ROOT / relative_path).exists():
            issues.append(f"Missing required file: {relative_path}")

    for relative_path in REQUIRED_FIXTURE_DIRS:
        if not (ROOT / relative_path).is_dir():
            issues.append(f"Missing required fixture directory: {relative_path}")
        elif not (ROOT / relative_path / "SKILL.md").exists():
            issues.append(f"Fixture directory missing SKILL.md: {relative_path}")

    return issues


def iter_runtime_smoke_test_paths() -> list[Path]:
    tests_dir = ROOT / "tests"
    if not tests_dir.exists():
        return []
    test_files: list[Path] = []
    for path in tests_dir.glob("test_*.py"):
        if not path.is_file() or path.name == "test_helpers.py":
            continue
        test_files.append(path)
    return sorted(test_files)


def validate_frontmatter() -> list[str]:
    issues: list[str] = []
    paths = [ROOT / relative_path for relative_path in FRONTMATTER_FILES]
    paths.extend(sorted((ROOT / "roles").glob("*.md")))

    for path in paths:
        frontmatter = parse_frontmatter(read_text(path))
        if frontmatter is None:
            issues.append(f"{rel(path)} is missing YAML frontmatter")
            continue

        if path.parent.name == "roles":
            try:
                validate_role_frontmatter_schema(path, frontmatter)
            except ValueError as exc:
                issues.append(str(exc))
            continue

        for key in ("name", "description"):
            value = frontmatter.get(key)
            if not isinstance(value, str) or not value.strip():
                issues.append(f"{rel(path)} is missing frontmatter field: {key}")

    return issues


def validate_version_sync() -> list[str]:
    issues: list[str] = []
    changelog_text = read_text(ROOT / "CHANGELOG.md")
    readme_text = read_text(ROOT / "README.md")
    pyproject_text = read_text(ROOT / "pyproject.toml")

    latest_version = find_latest_version(changelog_text)
    readme_version = find_readme_version(readme_text)
    pyproject_version = find_pyproject_version(pyproject_text)

    if latest_version is None:
        issues.append("Unable to determine the latest version from CHANGELOG.md")
    if readme_version is None:
        issues.append("Unable to determine the current version from README.md")
    if latest_version and readme_version and latest_version != readme_version:
        issues.append(
            "README.md current version does not match CHANGELOG.md latest version: "
            f"{readme_version} != {latest_version}"
        )
    if pyproject_version is None:
        issues.append("Unable to determine the project version from pyproject.toml")
    elif latest_version and latest_version.lstrip("v") != pyproject_version:
        issues.append(
            "pyproject.toml version does not match CHANGELOG.md latest version: "
            f"{pyproject_version} != {latest_version.lstrip('v')}"
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
    tracked_targets.extend(
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in sorted((ROOT / "docs" / "references").glob("reference-*.md"))
    )

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
    core_prefixes = ("flows/", "roles/", "docs/references/")
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


def iter_repo_package_json_paths() -> list[Path]:
    package_files: list[Path] = []
    for path in ROOT.rglob("package.json"):
        relative = rel(path)
        if _is_excluded(relative):
            continue
        package_files.append(path)
    return sorted(package_files)


def validate_embedded_js_lockfiles() -> list[str]:
    issues: list[str] = []
    git_available = bool(which("git"))

    for package_path in iter_repo_package_json_paths():
        relative_package = rel(package_path)
        lockfile_path = package_path.with_name("package-lock.json")
        relative_lockfile = rel(lockfile_path)

        if not lockfile_path.exists():
            issues.append(
                f"{relative_package} is missing sibling package-lock.json for reproducible helper installs"
            )
            continue

        if not git_available:
            continue

        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "--", relative_lockfile],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if ignored.returncode == 0:
            issues.append(
                f"{relative_lockfile} is ignored by git; helper lockfiles must stay trackable"
            )

    return issues


def check_unregistered_scripts() -> list[str]:
    """扫描 scripts/ 目录，返回未在 validation-manifest.json 中注册的 .py 和 .sh 文件的警告列表。"""
    registered: set[str] = set(REQUIRED_PYTHON_SCRIPT_FILES) | set(REQUIRED_SHELL_SCRIPT_FILES)
    scripts_dir = ROOT / "scripts"
    if not scripts_dir.exists():
        return []
    warnings: list[str] = []
    for f in sorted(scripts_dir.iterdir()):
        if not f.is_file():
            continue
        if f.suffix not in (".py", ".sh"):
            continue
        if f.name.startswith("_"):
            continue
        rel_path = f"scripts/{f.name}"
        if rel_path not in registered:
            warnings.append(
                f"WARNING: 未注册脚本文件 {rel_path}（请添加到 validation-manifest.json）"
            )
    return warnings


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
    python_files: list[Path] = []
    for base_dir in (ROOT / "scripts", ROOT / "src", ROOT / "tests"):
        if not base_dir.exists():
            continue
        for path in base_dir.rglob("*.py"):
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
    test_paths = iter_runtime_smoke_test_paths()
    if not test_paths:
        return ["No runtime smoke tests discovered under tests/"]
    discovered = {rel(path) for path in test_paths}
    for relative_path in CRITICAL_RUNTIME_SMOKE_TESTS:
        if relative_path not in discovered:
            issues.append(f"Missing required runtime smoke test: {relative_path}")
    for path in test_paths:
        relative_path = rel(path)
        timeout_seconds = RUNTIME_SMOKE_TEST_TIMEOUTS.get(relative_path, 180)
        try:
            result = subprocess.run(
                [sys.executable, str(path)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            issues.append(f"{relative_path} timed out after {timeout_seconds} seconds")
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


def find_runnable_bash() -> tuple[str | None, str | None]:
    selected = _core_find_bash_executable()
    if selected:
        return selected, None
    detected = which("bash")
    if detected:
        return None, "bash is visible on PATH but no supported Git Bash runtime was found; skipped shell syntax validation"
    return None, "bash not found; skipped shell syntax validation"


def bash_visible_path(path: Path) -> str:
    if not sys.platform.startswith("win"):
        return str(path)
    drive = path.drive.rstrip(":")
    if drive:
        suffix = path.as_posix()[2:].lstrip("/")
        return f"/{drive.lower()}/{suffix}"
    return path.as_posix()


def bash_probe_paths(path: Path) -> list[str]:
    if not sys.platform.startswith("win"):
        return [str(path)]
    drive = path.drive.rstrip(":").lower()
    suffix = path.as_posix()[2:].lstrip("/")
    candidates = [str(path), bash_visible_path(path)]
    if drive:
        candidates.append(f"/mnt/{drive}/{suffix}")
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def resolve_bash_script_path(bash: str, path: Path) -> str | None:
    for candidate in bash_probe_paths(path):
        probe = subprocess.run(
            [bash, "-c", 'test -f "$1"', "bash", candidate],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if probe.returncode == 0:
            return candidate
    return None


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
        bash_path = resolve_bash_script_path(bash, path)
        if bash_path is None:
            warnings.append(
                "bash is present but cannot access workspace shell scripts; skipped shell syntax validation"
            )
            return issues, warnings
        result = subprocess.run(
            [bash, "-n", bash_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip()
            issues.append(f"{relative_path} failed bash -n: {details}")

    return issues, warnings


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
    shell_syntax_warnings.extend(check_unregistered_scripts())

    checks = (
        ("required files", validate_required_files()),
        ("markdown links", validate_markdown_links(markdown_files)),
        ("frontmatter", validate_frontmatter()),
        ("version sync", validate_version_sync()),
        ("doc update discipline", validate_docs_updated_with_core_changes()),
        ("gitignore entries", validate_gitignore_entries()),
        ("local-only tracked files", validate_local_only_files_not_tracked()),
        ("embedded js lockfiles", validate_embedded_js_lockfiles()),
        ("flow headers", validate_flow_headers()),
        ("shell scripts", validate_shell_scripts()),
        ("python script syntax", validate_python_script_syntax()),
        ("runtime smoke tests", validate_runtime_smoke_tests()),
        ("definitions consistency", validate_definition_consistency()),
        ("stage subagent plan contract", validate_stage_subagent_plan_contract()),
        ("stage executor contract", validate_stage_executor_contract()),
        ("dispatch runner contract", validate_dispatch_runner_contract()),
        ("runtime bridge contract", validate_runtime_bridge_contract()),
        ("claude runtime contract", validate_claude_runtime_contract()),
        ("openclaw runtime contract", validate_openclaw_runtime_contract()),
        ("openclaw demo contract", validate_openclaw_demo_contract()),
        ("flow a fact contract", validate_flow_a_fact_contract()),
        ("flow a surface plan contract", validate_flow_a_surface_plan_contract()),
        ("flow a surface execution contract", validate_flow_a_surface_execution_contract()),
        ("flow a case-depth contract", validate_flow_a_case_depth_contract()),
        ("flow a runtime-harness contract", validate_flow_a_runtime_harness_contract()),
        ("message send contract", validate_message_send_contract()),
        ("output language contract", validate_output_language_contract()),
        ("role version tags", validate_role_version_tags()),
        ("role references", _validate_role_references(REQUIRED_FLOW_FILES)),
        ("role definitions ref", validate_role_definitions_ref()),
        ("security scanner fixtures", validate_security_scanner_fixtures()),
        ("flow role consistency", _validate_flow_role_consistency(REQUIRED_FLOW_FILES)),
        ("required references", validate_required_references()),
        ("product type normalization", validate_product_type_normalization()),
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
