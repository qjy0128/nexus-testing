#!/usr/bin/env python3
"""Validate Nexus Testing Framework repository structure and doc consistency."""

from __future__ import annotations

import argparse
import json
import py_compile
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from shutil import which
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

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
    "scripts/validate-framework.py",
    "scripts/skill-structure-validator.py",
    "scripts/skill_structure_validator_core.py",
    "scripts/sandbox_skill_invoke.py",
    "scripts/sandbox_multi_turn.py",
    "scripts/test_flow_a_strict.py",
    "scripts/test_flow_a_live_telemetry.py",
    "scripts/test_sandbox_exec_container.py",
    "scripts/test_flow_a_integration.py",
)

RUNTIME_SMOKE_TEST_FILES = (
    "scripts/test_flow_a_strict.py",
    "scripts/test_flow_a_live_telemetry.py",
    "scripts/test_sandbox_exec_container.py",
    "scripts/test_flow_a_integration.py",
)

FRONTMATTER_FILES = ("SKILL.md",)

GITIGNORE_EXPECTED_ENTRIES = (
    "/memory/nexus-reports/",
    "/.nexus-sandbox/",
)

LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SEMVER_PATTERN = re.compile(r"v\d+\.\d+\.\d+")
CHANGELOG_VERSION_PATTERN = re.compile(r"^###\s+(v\d+\.\d+\.\d+)（", re.MULTILINE)
SINGLE_SOURCE_REF = "> **所有阶段、角色、输出文件、超时配置均以 `DEFINITIONS.md` 为单一事实源。**"
ROLE_REF_PATTERN = re.compile(r"`roles/([^`]+\.md)`")
MARKDOWN_EXCLUDE_PARTS = {
    ".git",
    ".nexus-sandbox",
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
        content = read_text(file_path)
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
    return sorted(path for path in scripts_dir.glob("*.py") if path.is_file())


def validate_python_script_syntax() -> list[str]:
    issues: list[str] = []
    with tempfile.TemporaryDirectory(prefix="nexus-pycompile-") as temp_dir:
        temp_root = Path(temp_dir)
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
        ("gitignore entries", validate_gitignore_entries()),
        ("flow headers", validate_flow_headers()),
        ("shell scripts", validate_shell_scripts()),
        ("python script syntax", validate_python_script_syntax()),
        ("runtime smoke tests", validate_runtime_smoke_tests()),
        ("definitions consistency", validate_definition_consistency()),
        ("role version tags", validate_role_version_tags()),
        ("role references", validate_role_references()),
        ("role definitions ref", validate_role_definitions_ref()),
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
