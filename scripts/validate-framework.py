#!/usr/bin/env python3
"""Validate Nexus Testing Framework repository structure and doc consistency."""

from __future__ import annotations

import re
import sys
from pathlib import Path
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

REQUIRED_SCRIPT_FILES = (
    "scripts/sandbox-create.sh",
    "scripts/sandbox-exec.sh",
    "scripts/sandbox-cleanup.sh",
)

FRONTMATTER_FILES = ("SKILL.md",)

GITIGNORE_EXPECTED_ENTRIES = (
    "/memory/nexus-reports/",
    "/.nexus-sandbox/",
    "/.nexus-hmac-salt",
)

ALLOWED_ROLE_VERSION_FILES = {"compatibility-tester-skill.md"}

LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SEMVER_PATTERN = re.compile(r"v\d+\.\d+\.\d+")
CHANGELOG_VERSION_PATTERN = re.compile(r"^###\s+(v\d+\.\d+\.\d+)（", re.MULTILINE)
SINGLE_SOURCE_REF = "> **所有阶段、角色、输出文件、超时配置均以 `DEFINITIONS.md` 为单一事实源。**"
ROLE_REF_PATTERN = re.compile(r"`roles/([^`]+\.md)`")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


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
        *REQUIRED_SCRIPT_FILES,
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
    for relative_path in REQUIRED_SCRIPT_FILES:
        path = ROOT / relative_path
        if not path.exists():
            continue
        first_line = read_text(path).splitlines()[0].strip()
        if first_line != "#!/usr/bin/env bash":
            issues.append(
                f"{relative_path} should start with '#!/usr/bin/env bash'"
            )
    return issues


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
        if path.name in ALLOWED_ROLE_VERSION_FILES:
            continue
        content = read_text(path)
        if "DEFINITIONS.md" not in content:
            issues.append(
                f"{rel(path)} does not reference DEFINITIONS.md"
            )
    return issues


def validate_role_version_tags() -> list[str]:
    issues: list[str] = []
    for path in sorted((ROOT / "roles").glob("*.md")):
        if path.name in ALLOWED_ROLE_VERSION_FILES:
            continue
        if SEMVER_PATTERN.search(read_text(path)):
            issues.append(
                f"{rel(path)} contains an inline version tag; move version history to CHANGELOG.md"
            )
    return issues


def main() -> int:
    markdown_files = sorted(ROOT.rglob("*.md"))
    all_issues: list[str] = []

    checks = (
        ("required files", validate_required_files()),
        ("markdown links", validate_markdown_links(markdown_files)),
        ("frontmatter", validate_frontmatter()),
        ("version sync", validate_version_sync()),
        ("gitignore entries", validate_gitignore_entries()),
        ("flow headers", validate_flow_headers()),
        ("shell scripts", validate_shell_scripts()),
        ("role version tags", validate_role_version_tags()),
        ("role references", validate_role_references()),
        ("role definitions ref", validate_role_definitions_ref()),
    )

    print("Nexus Testing Framework validation")
    print(f"Repository root: {ROOT}")
    print(f"Markdown files scanned: {len(markdown_files)}")

    for name, issues in checks:
        if issues:
            print(f"[FAIL] {name}: {len(issues)} issue(s)")
            for issue in issues:
                print(f"  - {issue}")
            all_issues.extend(issues)
        else:
            print(f"[PASS] {name}")

    if all_issues:
        print(f"\nValidation failed with {len(all_issues)} issue(s).")
        return 1

    print("\nValidation succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
