#!/usr/bin/env python3
"""Extract a structured product fingerprint from a target repository."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


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


def resolve_target_root(raw_path: str) -> Path:
    target = Path(raw_path).expanduser().resolve()
    if target.is_file():
        if target.name.upper() == "SKILL.MD":
            return target.parent
        return target.parent
    return target


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


def discover_skill_files(root: Path) -> list[Path]:
    skill_files: list[Path] = []
    for path in root.rglob("SKILL.md"):
        if any(part in {".git", "node_modules", "__pycache__", ".tmp", ".tmp-test-runs", ".tmp-validation"} for part in path.parts):
            continue
        skill_files.append(path)
    return sorted(skill_files)


def extract_capabilities_from_skill(skill_path: Path, root: Path) -> list[dict[str, object]]:
    text = read_text(skill_path)
    capabilities: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    for match in re.finditer(r"##\s+Subcommand:\s+([A-Za-z0-9_-]+)", text):
        name = match.group(1)
        entry = (name, relative_to_root(skill_path, root))
        if entry in seen:
            continue
        seen.add(entry)
        capabilities.append(
            {
                "name": name,
                "kind": "subcommand",
                "source": {
                    "path": relative_to_root(skill_path, root),
                    "line": text[: match.start()].count("\n") + 1,
                    "key": "subcommand",
                },
            }
        )

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- **`") and "`**" in stripped:
            name = stripped.split("`", 2)[1]
        elif stripped.startswith("- **") and "**" in stripped[4:]:
            name = stripped[4:].split("**", 1)[0]
        else:
            continue
        name = name.strip()
        if not name:
            continue
        entry = (name, relative_to_root(skill_path, root))
        if entry in seen:
            continue
        seen.add(entry)
        capabilities.append(
            {
                "name": name,
                "kind": "declared-capability",
                "source": make_text_evidence(skill_path, root, stripped, "capability-bullet"),
            }
        )

    frontmatter = parse_frontmatter(text)
    argument_hint = frontmatter.get("argument-hint")
    if isinstance(argument_hint, str) and argument_hint:
        capabilities.append(
            {
                "name": "argument-hint",
                "kind": "routing-contract",
                "value": argument_hint,
                "source": make_text_evidence(skill_path, root, "argument-hint:", "argument-hint"),
            }
        )

    return capabilities


def extract_product_fingerprint(root: Path) -> dict[str, object]:
    package_json = root / "package.json"
    plugin_json = root / "openclaw.plugin.json"
    skill_files = discover_skill_files(root)

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
        "targetPath": str(root),
        "packageName": package_name if package_json.exists() and isinstance(package_name, str) else "unknown",
        "productType": deduped_types,
        "runtime": runtime,
        "version": version,
        "license": license_info,
        "runtimeRequirements": runtime_requirements,
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
    root = resolve_target_root(args.target)
    if not root.exists():
        raise SystemExit(f"ERROR: target does not exist: {args.target}")

    payload = extract_product_fingerprint(root)
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
