#!/usr/bin/env python3
"""Generate Flow A stage-one artifacts from repository facts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from extract_product_fingerprint import extract_product_fingerprint, resolve_target_root
from flow_a_localization import add_output_language_argument
from sandbox_skill_invoke.core import write_text


def text(language: str, zh: str, en: str) -> str:
    return zh if language == "zh-CN" else en


def render_source(source: dict[str, object] | None) -> str:
    if not source:
        return "unknown"
    path = str(source.get("path", "unknown"))
    line = source.get("line")
    key = source.get("key")
    suffix = ""
    if isinstance(line, int):
        suffix += f":{line}"
    if key:
        suffix += f" ({key})"
    return f"`{path}{suffix}`"


def render_sources(sources: list[dict[str, object]]) -> str:
    if not sources:
        return "unknown"
    return ", ".join(render_source(item) for item in sources)


def joined(values: list[object], fallback: str = "unknown") -> str:
    text = ", ".join(str(item) for item in values if str(item).strip())
    return text or fallback


def package_name_source(fingerprint: dict[str, object]) -> str:
    if str(fingerprint.get("packageName", "unknown")) != "unknown":
        return "`package.json (name)`"
    return render_sources(list(fingerprint.get("version", {}).get("sources", [])))


def render_fact_summary(fingerprint: dict[str, object], language: str) -> str:
    version = fingerprint.get("version", {})
    license_info = fingerprint.get("license", {})
    package_name = str(fingerprint.get("packageName", "unknown"))
    product_type = joined(list(fingerprint.get("productType", [])))
    runtime = joined(list(fingerprint.get("runtime", [])))
    return "\n".join(
        [
            text(language, "| 字段 | 值 | 证据 |", "| Field | Value | Evidence |"),
            text(language, "|------|----|------|", "|------|-------|----------|"),
            f"| {text(language, '包名', 'Package name')} | {package_name} | {package_name_source(fingerprint)} |",
            f"| {text(language, '产品类型', 'Product type')} | {product_type} | `PRODUCT-FINGERPRINT.json` |",
            f"| {text(language, '运行时', 'Runtime')} | {runtime} | `PRODUCT-FINGERPRINT.json` |",
            f"| {text(language, '版本', 'Version')} | {version.get('value', 'unknown')} | {render_sources(list(version.get('sources', [])))} |",
            f"| {text(language, '许可证', 'License')} | {license_info.get('value', 'unknown')} | {render_sources(list(license_info.get('sources', [])))} |",
        ]
    )


def render_entry_surfaces(fingerprint: dict[str, object], language: str) -> str:
    surfaces = list(fingerprint.get("entrySurfaces", []))
    if not surfaces:
        return text(language, "_未发现真实入口表面。_", "_No real entry surfaces were discovered._")
    lines = [
        text(language, "| 类型 | 标识 | 证据 |", "| Kind | Identifier | Evidence |"),
        text(language, "|------|------|------|", "|------|------------|----------|"),
    ]
    for surface in surfaces:
        identifier = surface.get("path") or surface.get("name") or surface.get("command") or "unknown"
        lines.append(
            f"| {surface.get('kind', 'unknown')} | {identifier} | {render_source(surface.get('source'))} |"
        )
    return "\n".join(lines)


def render_inventory_summary(capability: dict[str, object], language: str) -> str:
    groups = list(capability.get("scenarioGroups", []))
    if not groups:
        return text(language, "无", "(none)")
    parts: list[str] = []
    for group in groups:
        title = str(group.get("title", "Details"))
        items = list(group.get("items", []))
        parts.append(f"{title} x {len(items)}")
    return ", ".join(parts)


def render_capability_surfaces(fingerprint: dict[str, object], language: str) -> str:
    surfaces = list(fingerprint.get("capabilitySurfaces", []))
    if not surfaces:
        return text(language, "_未发现能力表面。_", "_No capability surfaces were discovered._")
    lines = [
        text(language, "| 名称 | 类型 | Inventory | 证据 |", "| Name | Kind | Inventory | Evidence |"),
        text(language, "|------|------|-----------|------|", "|------|------|-----------|----------|"),
    ]
    for surface in surfaces:
        lines.append(
            f"| {surface.get('name', 'unknown')} | {surface.get('kind', 'unknown')} | {render_inventory_summary(surface, language)} | {render_source(surface.get('source'))} |"
        )
    return "\n".join(lines)


def render_runtime_requirements(fingerprint: dict[str, object], language: str) -> str:
    requirements = list(fingerprint.get("runtimeRequirements", []))
    if not requirements:
        return text(language, "- 未发现显式运行时版本约束。", "- No explicit runtime version constraints were discovered.")
    return "\n".join(
        text(
            language,
            f"- `{item.get('name', 'runtime')}`：`{item.get('value', 'unknown')}`，来源 {render_source(item.get('source'))}",
            f"- `{item.get('name', 'runtime')}`: `{item.get('value', 'unknown')}` from {render_source(item.get('source'))}",
        )
        for item in requirements
    )


def render_test_implications(fingerprint: dict[str, object], language: str) -> str:
    product_types = set(str(item) for item in fingerprint.get("productType", []))
    implications: list[str] = []
    if "skill" in product_types:
        implications.append(
            text(
                language,
                "- 覆盖 SKILL 路由、argument-hint 行为、子命令和交付物发送行为。",
                "- Cover SKILL routing, argument-hint behavior, subcommands, and deliverable-send behavior.",
            )
        )
    if "cli" in product_types:
        implications.append(
            text(
                language,
                "- 将 bin 命令和 package scripts 视为一等测试表面，而不是折叠成单一 skill 用例。",
                "- Treat bin commands and package scripts as first-class surfaces instead of collapsing them into a single skill test.",
            )
        )
    if "plugin" in product_types:
        implications.append(
            text(
                language,
                "- 验证 plugin manifest 完整性、扩展注册和 hook 行为，不得只测文档。",
                "- Validate plugin manifest integrity, extension registration, and hook-facing behavior instead of testing documentation only.",
            )
        )
    if "mcp" in product_types:
        implications.append(
            text(
                language,
                "- 显式建模 MCP/server 行为；没有证据时不得把目标重解释成 HTTP API。",
                "- Model MCP/server behavior explicitly; do not reinterpret the target as an HTTP API without evidence.",
            )
        )
    if "package" in product_types:
        implications.append(
            text(
                language,
                "- 将安装契约、依赖和运行时要求纳入阶段零环境检查。",
                "- Pull installation contract, dependencies, and runtime requirements into the stage-zero environment check.",
            )
        )
    if not implications:
        implications.append(
            text(
                language,
                "- 尚未发现可靠的产品表面；Flow A 应阻塞，直到事实指纹被修正。",
                "- No reliable product surfaces were discovered yet; Flow A should block until the fingerprint is corrected.",
            )
        )
    return "\n".join(implications)


def render_open_questions(fingerprint: dict[str, object], language: str) -> str:
    questions: list[str] = []
    if fingerprint.get("version", {}).get("value") == "unknown":
        questions.append(text(language, "- 版本仍未知；后续报告不得臆造。", "- Version is still unknown; later reports must not invent one."))
    if fingerprint.get("license", {}).get("value") == "unknown":
        questions.append(text(language, "- 许可证仍未知；后续报告不得臆造。", "- License is still unknown; later reports must not invent one."))
    if not fingerprint.get("runtimeRequirements", []):
        questions.append(
            text(
                language,
                "- 未发现显式运行时版本约束；阶段零应确认真实环境。",
                "- No explicit runtime version constraint was found; stage zero should confirm the real environment.",
            )
        )
    if not questions:
        questions.append(text(language, "- 阶段一未发现阻断性待确认项。", "- No blocking open questions were discovered at stage one."))
    return "\n".join(questions)


def build_spec_markdown(target_root: Path, fingerprint: dict[str, object], language: str) -> str:
    title = str(fingerprint.get("packageName", "unknown"))
    if not title or title == "unknown":
        title = target_root.name
    lines = [
        f"# SPEC.md - {title}",
        "",
        text(language, "## 1. 事实摘要", "## 1. Fact Summary"),
        "",
        render_fact_summary(fingerprint, language),
        "",
        text(language, "## 2. 产品表面", "## 2. Product Surfaces"),
        "",
        text(language, "### 2.1 真实入口表面", "### 2.1 Real Entry Surfaces"),
        "",
        render_entry_surfaces(fingerprint, language),
        "",
        text(language, "### 2.2 能力表面", "### 2.2 Capability Surfaces"),
        "",
        render_capability_surfaces(fingerprint, language),
        "",
        text(language, "## 3. 运行时与依赖约束", "## 3. Runtime and Dependency Constraints"),
        "",
        render_runtime_requirements(fingerprint, language),
        "",
        text(language, "## 4. 测试影响", "## 4. Testing Implications"),
        "",
        render_test_implications(fingerprint, language),
        "",
        text(language, "## 5. 待确认项", "## 5. Open Questions"),
        "",
        render_open_questions(fingerprint, language),
        "",
        text(language, "## 6. 约束", "## 6. Constraints"),
        "",
        text(
            language,
            "- `SPEC.md` 只能展开 `PRODUCT-FINGERPRINT.json` 中已存在的事实。",
            "- `SPEC.md` may extend only facts already present in `PRODUCT-FINGERPRINT.json`.",
        ),
        text(
            language,
            "- 任何未出现在事实指纹中的 API、SDK、子命令、路由、Go library 或核心接口都视为未验证。",
            "- Any API, SDK, subcommand, route, Go library, or core interface not present in the fingerprint remains unverified.",
        ),
        "",
    ]
    return "\n".join(lines)


def evaluate_consistency(
    fingerprint: dict[str, object],
    language: str,
) -> tuple[str, list[str], list[str], list[str]]:
    verified: list[str] = []
    gaps: list[str] = []
    blockers: list[str] = []

    product_type = list(fingerprint.get("productType", []))
    if product_type and product_type != ["unknown"]:
        verified.append(
            text(
                language,
                f"已识别产品类型：{joined(product_type)}",
                f"Product type identified: {joined(product_type)}",
            )
        )
    else:
        blockers.append(
            text(language, "未识别出可靠的产品类型。", "No reliable product type was identified.")
        )

    runtime = list(fingerprint.get("runtime", []))
    if runtime and runtime != ["unknown"]:
        verified.append(
            text(language, f"已识别运行时：{joined(runtime)}", f"Runtime identified: {joined(runtime)}")
        )
    else:
        blockers.append(text(language, "未识别出可靠的运行时。", "No reliable runtime was identified."))

    entry_surfaces = list(fingerprint.get("entrySurfaces", []))
    if entry_surfaces:
        verified.append(
            text(
                language,
                f"发现 {len(entry_surfaces)} 个真实入口表面。",
                f"Discovered {len(entry_surfaces)} real entry surfaces.",
            )
        )
    else:
        blockers.append(text(language, "未发现真实入口表面。", "No real entry surfaces were discovered."))

    capabilities = list(fingerprint.get("capabilitySurfaces", []))
    if capabilities:
        verified.append(
            text(
                language,
                f"发现 {len(capabilities)} 个能力表面。",
                f"Discovered {len(capabilities)} capability surfaces.",
            )
        )
    else:
        blockers.append(text(language, "未发现能力表面。", "No capability surfaces were discovered."))

    version = fingerprint.get("version", {})
    if version.get("value") == "unknown":
        gaps.append(text(language, "版本仍未知。", "Version remains unknown."))
    else:
        verified.append(
            text(language, f"已识别版本：{version.get('value')}", f"Version identified: {version.get('value')}")
        )

    license_info = fingerprint.get("license", {})
    if license_info.get("value") == "unknown":
        gaps.append(text(language, "许可证仍未知。", "License remains unknown."))
    else:
        verified.append(
            text(
                language,
                f"已识别许可证：{license_info.get('value')}",
                f"License identified: {license_info.get('value')}",
            )
        )

    status = "passed" if not blockers else "blocked-spec-invalid"
    return status, verified, gaps, blockers


def build_consistency_review(target_root: Path, fingerprint: dict[str, object], language: str) -> str:
    status, verified, gaps, blockers = evaluate_consistency(fingerprint, language)
    title = str(fingerprint.get("packageName", "unknown"))
    if not title or title == "unknown":
        title = target_root.name

    lines = [
        f"# SPEC-CONSISTENCY-REVIEW - {title}",
        "",
        f"- decision: `{status}`",
        "",
        text(language, "## 指纹摘要", "## Fingerprint Summary"),
        "",
        f"- {text(language, 'product-type', 'product-type')}: {joined(list(fingerprint.get('productType', [])))}",
        f"- {text(language, 'runtime', 'runtime')}: {joined(list(fingerprint.get('runtime', [])))}",
        f"- {text(language, 'version', 'version')}: {fingerprint.get('version', {}).get('value', 'unknown')}",
        f"- {text(language, 'license', 'license')}: {fingerprint.get('license', {}).get('value', 'unknown')}",
        "",
        text(language, "## 已验证事实", "## Verified Facts"),
        "",
    ]
    lines.extend(f"- {item}" for item in verified) if verified else lines.append(text(language, "- 无", "- None"))
    lines.extend(["", text(language, "## 非阻断缺口", "## Non-blocking Gaps"), ""])
    lines.extend(f"- {item}" for item in gaps) if gaps else lines.append(text(language, "- 无", "- None"))
    lines.extend(["", text(language, "## 阻断问题", "## Blocking Issues"), ""])
    lines.extend(f"- {item}" for item in blockers) if blockers else lines.append(text(language, "- 无", "- None"))
    lines.extend(["", text(language, "## 门禁结论", "## Gate Decision"), ""])
    if status == "passed":
        lines.append(text(language, "- 允许 Flow A 进入阶段二。", "- Allow Flow A to continue to stage two."))
    else:
        lines.append(
            text(
                language,
                "- 阻塞阶段二，直到事实指纹和 SPEC 被修正。",
                "- Block stage two until the fingerprint and SPEC are corrected.",
            )
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Target repository or SKILL.md path")
    parser.add_argument("--output-dir", required=True, help="Directory for stage-one artifacts")
    add_output_language_argument(parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    target_root = resolve_target_root(args.target)
    if not target_root.exists():
        raise SystemExit(f"ERROR: target does not exist: {args.target}")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    fingerprint = extract_product_fingerprint(target_root)
    write_text(
        output_dir / "PRODUCT-FINGERPRINT.json",
        json.dumps(fingerprint, ensure_ascii=False, indent=2) + "\n",
    )
    write_text(output_dir / "SPEC.md", build_spec_markdown(target_root, fingerprint, args.language) + "\n")
    write_text(
        output_dir / "SPEC-CONSISTENCY-REVIEW.md",
        build_consistency_review(target_root, fingerprint, args.language) + "\n",
    )

    print(f"OUTPUT_DIR={output_dir}")
    print(f"PRODUCT_FINGERPRINT={output_dir / 'PRODUCT-FINGERPRINT.json'}")
    print(f"SPEC_FILE={output_dir / 'SPEC.md'}")
    print(f"CONSISTENCY_REVIEW={output_dir / 'SPEC-CONSISTENCY-REVIEW.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
