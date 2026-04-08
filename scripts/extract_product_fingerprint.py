#!/usr/bin/env python3
"""Extract a structured product fingerprint from a target repository."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from sandbox_skill_invoke.core import read_text

IGNORED_PATH_PARTS = {".git", "node_modules", "__pycache__", ".tmp", ".tmp-test-runs", ".tmp-validation"}
REPO_ROOT_MARKERS = (
    "package.json",
    "openclaw.plugin.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    ".git",
)
INVENTORY_FILE_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".toml", ".ts", ".js", ".tsx", ".jsx", ".py"}
DECISION_TOKENS = ("ALLOW", "DENY", "CONFIRM")
IGNORED_UPPER_TOKENS = {
    "HIGH",
    "MEDIUM",
    "LOW",
    "CRITICAL",
    "ALLOW",
    "DENY",
    "CONFIRM",
    "POST",
    "PUT",
    "GET",
    "PATCH",
    "DELETE",
    "HEAD",
    "JSON",
    "HTTP",
    "HTTPS",
    "API",
    "PATH",
    "CLI",
    "URL",
    "ALL",
}


def parse_frontmatter(text: str) -> dict[str, object]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}

    data: dict[str, object] = {}
    current_key: str | None = None
    for raw_line in lines[1:end_index]:
        if not raw_line.strip():
            continue
        if raw_line.startswith((" ", "\t")) and current_key:
            previous = data.get(current_key, "")
            data[current_key] = f"{previous}\n{raw_line.strip()}".strip()
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        current_key = key.strip()
        data[current_key] = value.strip().strip('"')
    return data


def parse_json(path: Path) -> dict[str, object]:
    return json.loads(read_text(path))


def relative_to_root(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def locate_line(text: str, needle: str) -> int | None:
    for index, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return index
    return None


def make_text_evidence(path: Path, root: Path, needle: str, key: str) -> dict[str, object]:
    text = read_text(path)
    line = locate_line(text, needle)
    evidence: dict[str, object] = {
        "path": relative_to_root(path, root),
        "key": key,
    }
    if line is not None:
        evidence["line"] = line
    return evidence


def make_key_evidence(path: Path, root: Path, key: str) -> dict[str, object]:
    evidence = {
        "path": relative_to_root(path, root),
        "key": key,
    }
    text = read_text(path)
    line = locate_line(text, f'"{key}"')
    if line is not None:
        evidence["line"] = line
    return evidence


def merge_capability_entry(
    capabilities: dict[tuple[str, str], dict[str, object]],
    *,
    root: Path,
    skill_path: Path,
    name: str,
    kind: str,
    source: dict[str, object],
    scenario_groups: list[dict[str, object]] | None = None,
    value: str | None = None,
    command: str | None = None,
) -> None:
    entry_key = (name, relative_to_root(skill_path, root))
    current = capabilities.get(entry_key)
    if current is None:
        current = {
            "name": name,
            "kind": kind,
            "source": source,
        }
        capabilities[entry_key] = current
    else:
        current.setdefault("source", source)
        existing_kind = str(current.get("kind", "")).strip()
        if existing_kind in {"declared-capability", "unknown"} and kind != existing_kind:
            current["kind"] = kind

    if value and not current.get("value"):
        current["value"] = value
    if command and not current.get("command"):
        current["command"] = command
    if scenario_groups:
        existing_groups = list(current.get("scenarioGroups", []))
        seen_groups = {
            json.dumps(group, sort_keys=True, ensure_ascii=False)
            for group in existing_groups
            if isinstance(group, dict)
        }
        for group in scenario_groups:
            key = json.dumps(group, sort_keys=True, ensure_ascii=False)
            if key in seen_groups:
                continue
            seen_groups.add(key)
            existing_groups.append(group)
        current["scenarioGroups"] = existing_groups


def clean_list_item(raw_line: str) -> str | None:
    stripped = raw_line.strip()
    if not stripped:
        return None

    bullet_match = re.match(r"^(?:[-*+]|\d+[.)])\s+(.*)$", stripped)
    if not bullet_match:
        return None

    body = bullet_match.group(1).strip()
    if not body:
        return None
    if body.startswith("**`") and "`**" in body:
        return body.split("`", 2)[1].strip()
    if body.startswith("`") and "`" in body[1:]:
        return body.split("`", 2)[1].strip()
    if body.startswith("**") and "**" in body[2:]:
        return body[2:].split("**", 1)[0].strip()

    normalized = re.split(r"\s+[—–:-]\s+", body, maxsplit=1)[0].strip()
    normalized = normalized.strip("`*_ ")
    return normalized or None


def classify_scenario_group(title: str, capability_name: str) -> str:
    probe = f"{title} {capability_name}".lower()
    if any(token in probe for token in ("decision", "path", "allow", "deny", "confirm")):
        return "decision"
    if any(token in probe for token in ("rule", "policy", "signature", "detector", "detect")):
        return "rule"
    if any(token in probe for token in ("check", "patrol", "monitor", "guardrail", "guardrail")):
        return "check"
    return "scenario"


def is_ignored_path(path: Path) -> bool:
    return any(part in IGNORED_PATH_PARTS for part in path.parts)


def extract_scenario_groups(block_text: str, capability_name: str) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    current_title = "Details"
    current_items: list[str] = []

    def flush_group() -> None:
        nonlocal current_items, current_title
        deduped_items: list[str] = []
        seen: set[str] = set()
        for item in current_items:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped_items.append(normalized)
        if deduped_items:
            groups.append(
                {
                    "title": current_title,
                    "kind": classify_scenario_group(current_title, capability_name),
                    "items": deduped_items,
                }
            )
        current_items = []

    for raw_line in block_text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("### "):
            flush_group()
            current_title = line[4:].strip() or "Details"
            continue
        item = clean_list_item(line)
        if item:
            current_items.append(item)
    flush_group()
    return groups


def normalize_inventory_item(value: str) -> str | None:
    item = re.sub(r"\s+", " ", value.strip().strip("`*_ "))
    item = re.sub(r"\s*\([^)]*\)\s*$", "", item).strip()
    item = item.rstrip(":").strip()
    return item or None


def dedupe_inventory_items(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for raw_item in items:
        normalized = normalize_inventory_item(raw_item)
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def finalize_inventory_group(
    groups: list[dict[str, object]],
    *,
    title: str,
    kind: str,
    items: list[str],
) -> None:
    deduped_items = dedupe_inventory_items(items)
    if not deduped_items:
        return
    groups.append({"title": title, "kind": kind, "items": deduped_items})


def extract_markdown_references(block_text: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(
        r"(?P<ref>[A-Za-z0-9_./-]+\.(?:md|json|ya?ml|toml|ts|js|tsx|jsx|py))",
        block_text,
        re.IGNORECASE,
    ):
        ref = match.group("ref").strip("`")
        if ref.lower().startswith(("http://", "https://")):
            continue
        if ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
    return refs


def ensure_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_inventory_reference(reference: str, base_dir: Path, root: Path) -> Path | None:
    candidate = (base_dir / reference).resolve()
    if candidate.exists() and candidate.is_file() and ensure_within_root(candidate, root):
        return candidate
    alt = (root / reference).resolve()
    if alt.exists() and alt.is_file() and ensure_within_root(alt, root):
        return alt
    return None


def iter_inventory_search_roots(root: Path, skill_path: Path) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in (
        skill_path.parent,
        root / "src",
        root / "scripts",
        root / "lib",
        root,
    ):
        if not candidate.exists():
            continue
        key = str(candidate.resolve())
        if key in seen:
            continue
        seen.add(key)
        roots.append(candidate.resolve())
    return roots


def inventory_keyword_tokens(capability_name: str) -> list[str]:
    lowered = capability_name.lower()
    tokens = {lowered}
    if lowered == "scan":
        tokens.update({"scanner", "scan", "rule", "rules", "detector", "detectors"})
    if lowered == "action":
        tokens.update({"action", "policy", "policies", "decision", "decide"})
    if lowered == "patrol":
        tokens.update({"patrol", "check", "checks", "checkup", "monitor"})
    if lowered == "trust":
        tokens.update({"trust", "registry", "preset", "capability"})
    if lowered == "report":
        tokens.update({"report", "audit", "log"})
    if lowered == "config":
        tokens.update({"config", "policy", "preset"})
    return sorted(tokens)


def source_group_matches_capability(label: str, capability_name: str) -> bool:
    label_probe = label.lower()
    token_groups = {
        "scan": ("scan", "scanner", "rule", "rules", "detector", "detectors"),
        "action": ("action", "policy", "policies", "decision", "decide"),
        "patrol": ("patrol", "check", "checks", "monitor"),
        "trust": ("trust", "registry", "preset", "capability"),
        "report": ("report", "audit", "log"),
        "config": ("config", "preset", "policy"),
    }
    tokens = token_groups.get(capability_name.lower(), (capability_name.lower(),))
    return any(token in label_probe for token in tokens)


def candidate_inventory_paths(
    root: Path,
    skill_path: Path,
    capability_name: str,
    block_text: str,
) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()

    for reference in extract_markdown_references(block_text):
        resolved = resolve_inventory_reference(reference, skill_path.parent, root)
        if resolved is None or is_ignored_path(resolved):
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(resolved)

    keyword_tokens = inventory_keyword_tokens(capability_name)
    for search_root in iter_inventory_search_roots(root, skill_path):
        for path in search_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in INVENTORY_FILE_SUFFIXES:
                continue
            if is_ignored_path(path):
                continue
            probe = path.name.lower()
            if not any(token in probe for token in keyword_tokens):
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            candidates.append(path.resolve())
    return candidates


def extract_named_heading_items(text: str, heading_pattern: str, title: str, kind: str) -> list[dict[str, object]]:
    items = []
    for match in re.finditer(heading_pattern, text, re.MULTILINE):
        item = normalize_inventory_item(match.group(1))
        if item:
            items.append(item)
    groups: list[dict[str, object]] = []
    finalize_inventory_group(groups, title=title, kind=kind, items=items)
    return groups


def extract_decision_logic_groups(text: str, capability_name: str) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    section_pattern = re.compile(
        r"^###\s+(?P<title>[^\n]*Decision[^\n]*)\n(?P<body>.*?)(?=^##\s+|^###\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for match in section_pattern.finditer(text):
        title = match.group("title").strip()
        items: list[str] = []
        for raw_line in match.group("body").splitlines():
            stripped = raw_line.strip()
            number_match = re.match(r"^\d+[.)]\s+(.*)$", stripped)
            if not number_match:
                continue
            body = number_match.group(1).strip()
            if not any(token in body.upper() for token in DECISION_TOKENS):
                continue
            items.append(body)
        finalize_inventory_group(groups, title=title, kind="decision", items=items)
    if groups:
        return groups

    tokens: list[str] = []
    for line in text.splitlines():
        upper_line = line.upper()
        if "DECISION" not in upper_line and "POLICY" not in upper_line:
            continue
        for token in DECISION_TOKENS:
            if token in upper_line:
                tokens.append(token)
    finalize_inventory_group(groups, title=f"{capability_name} decisions", kind="decision", items=tokens)
    return groups


def extract_source_groups(text: str, capability_name: str) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    assignment_pattern = re.compile(
        r"(?is)(?P<label>[A-Za-z_][A-Za-z0-9_]*(?:rules?|checks?|polic(?:y|ies)|detectors?))\s*[:=]\s*(?P<body>[\[{].*?[\]}])"
    )
    for match in assignment_pattern.finditer(text):
        label = match.group("label")
        if not source_group_matches_capability(label, capability_name):
            continue
        kind = classify_scenario_group(label, capability_name)
        body = match.group("body")
        quoted = [item for item in re.findall(r"['\"`]{1}([^'\"`\n]+)['\"`]{1}", body) if item.strip()]
        upper = [
            token
            for token in re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", body)
            if token not in IGNORED_UPPER_TOKENS
        ]
        items = quoted if quoted else upper
        finalize_inventory_group(groups, title=label, kind=kind, items=items)

    if capability_name.lower() == "action":
        decision_tokens = []
        for token in DECISION_TOKENS:
            if re.search(rf"\b{token}\b", text):
                decision_tokens.append(token)
        finalize_inventory_group(groups, title="action decisions", kind="decision", items=decision_tokens)

    return groups


def extract_inventory_from_file(path: Path, root: Path, capability_name: str) -> list[dict[str, object]]:
    if not path.exists() or not path.is_file():
        return []
    text = read_text(path)
    if path.suffix.lower() == ".md":
        groups: list[dict[str, object]] = []
        groups.extend(extract_named_heading_items(text, r"^##\s+Rule\s+\d+\s*:\s*([^\n(]+)", "Rules", "rule"))
        groups.extend(extract_named_heading_items(text, r"^##\s+Check\s+\d+\s*:\s*([^\n]+)", "Checks", "check"))
        groups.extend(extract_decision_logic_groups(text, capability_name))
        return groups
    return extract_source_groups(text, capability_name)


def _target_directory(target: Path) -> Path:
    return target.parent if target.is_file() else target


def has_repo_root_markers(path: Path) -> bool:
    for marker in REPO_ROOT_MARKERS:
        if (path / marker).exists():
            return True
    return False


def resolve_target_context(raw_path: str) -> dict[str, Path | None]:
    target = Path(raw_path).expanduser().resolve()
    requested_dir = _target_directory(target)
    scan_root = requested_dir
    if not has_repo_root_markers(scan_root):
        for candidate in requested_dir.parents:
            if has_repo_root_markers(candidate):
                scan_root = candidate
                break

    skill_scope: Path | None = None
    if target.is_file() and target.name.upper() == "SKILL.MD":
        skill_scope = target.parent
    elif target.is_dir() and (target / "SKILL.md").exists():
        skill_scope = target
    else:
        for candidate in (requested_dir, *requested_dir.parents):
            if candidate == scan_root.parent:
                break
            if (candidate / "SKILL.md").exists():
                skill_scope = candidate
                break

    return {
        "requested_path": target,
        "scan_root": scan_root,
        "skill_scope": skill_scope,
    }


def resolve_target_root(raw_path: str) -> Path:
    context = resolve_target_context(raw_path)
    root = context.get("scan_root")
    if isinstance(root, Path):
        return root
    return Path(raw_path).expanduser().resolve()


def detect_runtime(root: Path) -> tuple[list[str], list[dict[str, object]]]:
    runtimes: list[str] = []
    evidence: list[dict[str, object]] = []

    if (root / "package.json").exists():
        runtimes.append("node")
        evidence.append(make_key_evidence(root / "package.json", root, "name"))
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        runtimes.append("python")
        path = root / "pyproject.toml" if (root / "pyproject.toml").exists() else root / "requirements.txt"
        evidence.append({"path": relative_to_root(path, root), "key": "runtime"})
    if (root / "go.mod").exists():
        runtimes.append("go")
        evidence.append({"path": "go.mod", "key": "module"})
    if (root / "Cargo.toml").exists():
        runtimes.append("rust")
        evidence.append({"path": "Cargo.toml", "key": "package"})

    if not runtimes:
        runtimes.append("unknown")

    return sorted(dict.fromkeys(runtimes)), evidence


def extract_version_and_license(root: Path) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    version = {"value": "unknown", "sources": []}
    license_info = {"value": "unknown", "sources": []}
    runtime_requirements: list[dict[str, object]] = []

    package_json = root / "package.json"
    if package_json.exists():
        data = parse_json(package_json)
        if isinstance(data.get("version"), str):
            version = {
                "value": data["version"],
                "sources": [make_key_evidence(package_json, root, "version")],
            }
        if isinstance(data.get("license"), str):
            license_info = {
                "value": data["license"],
                "sources": [make_key_evidence(package_json, root, "license")],
            }
        engines = data.get("engines")
        if isinstance(engines, dict):
            for name, value in engines.items():
                runtime_requirements.append(
                    {
                        "name": name,
                        "value": str(value),
                        "source": make_key_evidence(package_json, root, "engines"),
                    }
                )

    readme = root / "README.md"
    if version["value"] == "unknown" and readme.exists():
        text = read_text(readme)
        match = re.search(r"\bv\d+\.\d+\.\d+\b", text)
        if match:
            version = {
                "value": match.group(0),
                "sources": [make_text_evidence(readme, root, match.group(0), "version-text")],
            }

    return version, license_info, runtime_requirements


def discover_skill_files(root: Path, *, skill_scope: Path | None = None) -> list[Path]:
    skill_files: list[Path] = []
    search_root = skill_scope if skill_scope is not None else root
    if not search_root.exists():
        return skill_files
    for path in search_root.rglob("SKILL.md"):
        if is_ignored_path(path):
            continue
        skill_files.append(path)
    return sorted(skill_files)


def extract_capabilities_from_skill(skill_path: Path, root: Path) -> list[dict[str, object]]:
    text = read_text(skill_path)
    capabilities: dict[tuple[str, str], dict[str, object]] = {}

    section_matches = list(re.finditer(r"^##\s+Subcommand:\s+([A-Za-z0-9_-]+)\s*$", text, re.MULTILINE))
    for index, match in enumerate(section_matches):
        name = match.group(1).strip()
        block_start = match.end()
        block_end = section_matches[index + 1].start() if index + 1 < len(section_matches) else len(text)
        block_text = text[block_start:block_end]
        scenario_groups = extract_scenario_groups(block_text, name)
        for inventory_path in candidate_inventory_paths(root, skill_path, name, block_text):
            for group in extract_inventory_from_file(inventory_path, root, name):
                scenario_groups.append(group)
        merge_capability_entry(
            capabilities,
            root=root,
            skill_path=skill_path,
            name=name,
            kind="subcommand",
            source={
                "path": relative_to_root(skill_path, root),
                "line": text[: match.start()].count("\n") + 1,
                "key": "subcommand",
            },
            scenario_groups=scenario_groups,
        )

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- **`") and "`**" in stripped:
            name = stripped.split("`", 2)[1]
        elif stripped.startswith("- **") and "**" in stripped[4:]:
            name = stripped[4:].split("**", 1)[0]
        else:
            continue
        name = re.split(r"\s+|<", name.strip(), maxsplit=1)[0]
        if not name:
            continue
        merge_capability_entry(
            capabilities,
            root=root,
            skill_path=skill_path,
            name=name,
            kind="declared-capability",
            source=make_text_evidence(skill_path, root, stripped, "capability-bullet"),
        )

    frontmatter = parse_frontmatter(text)
    argument_hint = frontmatter.get("argument-hint")
    if isinstance(argument_hint, str) and argument_hint:
        merge_capability_entry(
            capabilities,
            root=root,
            skill_path=skill_path,
            name="argument-hint",
            kind="routing-contract",
            value=argument_hint,
            source=make_text_evidence(skill_path, root, "argument-hint:", "argument-hint"),
        )

    return list(capabilities.values())


def extract_product_fingerprint(
    root: Path,
    *,
    requested_path: Path | None = None,
    skill_scope: Path | None = None,
) -> dict[str, object]:
    package_json = root / "package.json"
    plugin_json = root / "openclaw.plugin.json"
    skill_files = discover_skill_files(root, skill_scope=skill_scope)

    product_type: list[str] = []
    entry_surfaces: list[dict[str, object]] = []
    capability_surfaces: list[dict[str, object]] = []
    evidence: list[dict[str, object]] = []

    if skill_files:
        product_type.append("skill")
        for skill_path in skill_files:
            rel = relative_to_root(skill_path, root)
            frontmatter = parse_frontmatter(read_text(skill_path))
            name = frontmatter.get("name") if isinstance(frontmatter.get("name"), str) else skill_path.parent.name
            entry_surfaces.append(
                {
                    "kind": "skill",
                    "path": rel,
                    "name": name,
                    "source": make_text_evidence(skill_path, root, "name:", "frontmatter.name"),
                }
            )
            capability_surfaces.extend(extract_capabilities_from_skill(skill_path, root))
            evidence.append({"path": rel, "key": "skill-entry"})

    if package_json.exists():
        package_data = parse_json(package_json)
        product_type.append("package")
        evidence.append(make_key_evidence(package_json, root, "name"))
        package_name = package_data.get("name")
        package_scripts = package_data.get("scripts")

        bin_data = package_data.get("bin")
        if isinstance(bin_data, dict):
            product_type.append("cli")
            for name, command in sorted(bin_data.items()):
                entry_surfaces.append(
                    {
                        "kind": "bin",
                        "name": name,
                        "command": str(command),
                        "source": make_key_evidence(package_json, root, "bin"),
                    }
                )
                capability_surfaces.append(
                    {
                        "name": name,
                        "kind": "cli-command",
                        "source": make_key_evidence(package_json, root, "bin"),
                    }
                )

        if isinstance(package_scripts, dict):
            for name, command in sorted(package_scripts.items()):
                capability_surfaces.append(
                    {
                        "name": name,
                        "kind": "package-script",
                        "command": str(command),
                        "source": make_key_evidence(package_json, root, "scripts"),
                    }
                )

        openclaw_config = package_data.get("openclaw")
        if isinstance(openclaw_config, dict):
            product_type.append("plugin")
            extensions = openclaw_config.get("extensions")
            if isinstance(extensions, list):
                for extension in extensions:
                    entry_surfaces.append(
                        {
                            "kind": "openclaw-extension",
                            "path": str(extension),
                            "source": make_key_evidence(package_json, root, "openclaw"),
                        }
                    )

        dependencies = package_data.get("dependencies")
        if isinstance(dependencies, dict) and "@modelcontextprotocol/sdk" in dependencies:
            product_type.append("mcp")
            capability_surfaces.append(
                {
                    "name": "mcp-sdk",
                    "kind": "runtime-surface",
                    "source": make_key_evidence(package_json, root, "dependencies"),
                }
            )

    if plugin_json.exists():
        product_type.append("plugin")
        entry_surfaces.append(
            {
                "kind": "plugin-manifest",
                "path": relative_to_root(plugin_json, root),
                "source": {"path": relative_to_root(plugin_json, root), "key": "manifest"},
            }
        )
        evidence.append({"path": relative_to_root(plugin_json, root), "key": "manifest"})

    runtime, runtime_evidence = detect_runtime(root)
    evidence.extend(runtime_evidence)
    version, license_info, runtime_requirements = extract_version_and_license(root)

    deduped_types = sorted(dict.fromkeys(product_type)) or ["unknown"]
    deduped_entry_surfaces: list[dict[str, object]] = []
    seen_surfaces: set[str] = set()
    for surface in entry_surfaces:
        key = json.dumps(surface, sort_keys=True, ensure_ascii=False)
        if key in seen_surfaces:
            continue
        seen_surfaces.add(key)
        deduped_entry_surfaces.append(surface)

    deduped_capabilities: list[dict[str, object]] = []
    seen_capabilities: set[str] = set()
    for capability in capability_surfaces:
        key = json.dumps(capability, sort_keys=True, ensure_ascii=False)
        if key in seen_capabilities:
            continue
        seen_capabilities.add(key)
        deduped_capabilities.append(capability)

    deduped_evidence: list[dict[str, object]] = []
    seen_evidence: set[str] = set()
    for item in evidence:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key in seen_evidence:
            continue
        seen_evidence.add(key)
        deduped_evidence.append(item)

    return {
        "targetPath": str(requested_path or root),
        "resolvedRootPath": str(root),
        "packageName": package_name if package_json.exists() and isinstance(package_name, str) else "unknown",
        "productType": deduped_types,
        "runtime": runtime,
        "version": version,
        "license": license_info,
        "runtimeRequirements": runtime_requirements,
        "targetSkillPath": relative_to_root(skill_scope, root) if skill_scope is not None else None,
        "entrySurfaces": deduped_entry_surfaces,
        "capabilitySurfaces": deduped_capabilities,
        "evidence": deduped_evidence,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="Target repository, directory, or SKILL.md path")
    parser.add_argument(
        "--output",
        help="Optional output path for PRODUCT-FINGERPRINT.json",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    context = resolve_target_context(args.target)
    root = Path(context["scan_root"]) if isinstance(context.get("scan_root"), Path) else resolve_target_root(args.target)
    if not root.exists():
        raise SystemExit(f"ERROR: target does not exist: {args.target}")

    payload = extract_product_fingerprint(
        root,
        requested_path=Path(context["requested_path"]) if isinstance(context.get("requested_path"), Path) else root,
        skill_scope=Path(context["skill_scope"]) if isinstance(context.get("skill_scope"), Path) else None,
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
