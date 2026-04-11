#!/usr/bin/env python3
"""Role metadata parsing helpers shared by orchestration/runtime code."""

from __future__ import annotations

import re
from pathlib import Path

from nexus_testing.frontmatter_utils import parse_boolean_text, parse_frontmatter
from nexus_testing.sandbox_skill_invoke.core import read_text

ANY_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

SECTION_MINIMUM_OUTPUT = "\u6700\u4f4e\u8f93\u51fa\u7ed3\u6784"
SECTION_OUTPUT_FORMAT = "\u8f93\u51fa\u683c\u5f0f"
SECTION_OUTPUT_VALIDATION = "\u8f93\u51fa\u7ed3\u6784\u6821\u9a8c"
SECTION_OUTPUT_VALIDATION_ALIASES = "\u8f93\u51fa\u7ed3\u6784\u6821\u9a8c\u522b\u540d"
SECTION_TAKEOVER_POLICY = "\u4e3bAgent\u63a5\u7ba1\u7b56\u7565"
SECTION_INPUT_SOURCES = "\u8f93\u5165\u6765\u6e90"
SECTION_INPUTS = "\u8f93\u5165"
SECTION_OUTPUTS = "\u8f93\u51fa"
SECTION_CONSUMERS = "\u4e0b\u6e38\u6d88\u8d39\u8005"
SECTION_RESPONSIBILITIES = "\u804c\u8d23"
SECTION_EXECUTION_RULES = "\u6267\u884c\u89c4\u5219"
SECTION_EVIDENCE_REQUIREMENTS = "\u6267\u884c\u8bc1\u660e\u8981\u6c42"
SECTION_ANTI_PATTERNS = "\u8fb9\u754c\u4e0e\u53cd\u6a21\u5f0f"
SECTION_HARD_BOUNDARIES = "\u5f3a\u5236\u8fb9\u754c"
SECTION_SUMMARY_RULES = "\u6c47\u603b\u89c4\u5219"

ALLOWED_ROLE_TYPES = {"executor", "validator"}
ALLOWED_OUTPUT_VALIDATION_RULES = {"markdown-headings"}
ALLOWED_FRONTMATTER_KEYS = {
    "name",
    "type",
    "description",
    "triggers",
    "best_for",
    "output_validation",
    "minimum_output",
    "minimum_output_aliases",
    "takeover_enabled",
    "takeover_statuses",
    "takeover_patterns",
    "takeover_on_process_failure",
}


def section_body(text: str, heading: str) -> str:
    current_heading: str | None = None
    current_lines: list[str] = []
    inside_fence = False

    for line in text.splitlines():
        stripped = line.strip()
        if not inside_fence and line.startswith("## "):
            if current_heading == heading:
                return "\n".join(current_lines).strip("\n")
            current_heading = line[3:].strip()
            current_lines = []
            continue
        if current_heading == heading:
            current_lines.append(line)
        if stripped.startswith("```"):
            inside_fence = not inside_fence
    if current_heading == heading:
        return "\n".join(current_lines).strip("\n")
    return ""
def section_lines(text: str, heading: str) -> list[str]:
    body = section_body(text, heading)
    if body:
        return [line.strip()[2:].strip() for line in body.splitlines() if line.strip().startswith("- ")]
    return []


def section_markdown_headings(text: str, heading: str, levels: set[int] | None = None) -> list[str]:
    body = section_body(text, heading)
    if not body:
        return []
    results: list[str] = []
    for match in ANY_HEADING_RE.finditer(body):
        if levels is not None and len(match.group(1)) not in levels:
            continue
        results.append(match.group(2).strip())
    return results


def section_mapping(text: str, heading: str, separator: str = "=>") -> dict[str, str]:
    mappings: dict[str, str] = {}
    for line in section_lines(text, heading):
        if separator not in line:
            continue
        source, target = line.split(separator, 1)
        source = source.strip()
        target = target.strip()
        if source and target:
            mappings[source] = target
    return mappings


def frontmatter_string_list(frontmatter: dict[str, object], key: str) -> list[str]:
    value = frontmatter.get(key, [])
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def frontmatter_mapping(frontmatter: dict[str, object], key: str) -> dict[str, str]:
    mappings: dict[str, str] = {}
    for line in frontmatter_string_list(frontmatter, key):
        if "=>" not in line:
            continue
        source, target = line.split("=>", 1)
        source = source.strip()
        target = target.strip()
        if source and target:
            mappings[source] = target
    return mappings


def frontmatter_takeover_policy(frontmatter: dict[str, object]) -> dict[str, object]:
    policy: dict[str, object] = {}
    enabled = frontmatter.get("takeover_enabled")
    if isinstance(enabled, bool):
        policy["enabled"] = enabled
    statuses = frontmatter_string_list(frontmatter, "takeover_statuses")
    if statuses:
        policy["statuses"] = statuses
    patterns = frontmatter_string_list(frontmatter, "takeover_patterns")
    if patterns:
        policy["patterns"] = patterns
    on_process_failure = frontmatter.get("takeover_on_process_failure")
    if isinstance(on_process_failure, bool):
        policy["onProcessFailure"] = on_process_failure
    return policy


def parse_takeover_policy(text: str) -> dict[str, object]:
    raw_lines = section_lines(text, SECTION_TAKEOVER_POLICY)
    if not raw_lines:
        return {}
    policy: dict[str, object] = {}
    for line in raw_lines:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if key == "enabled":
            value = parse_boolean_text(raw_value)
            if value is not None:
                policy["enabled"] = value
        elif key in {"statuses", "patterns"}:
            items = [item.strip() for item in raw_value.split(",") if item.strip()]
            policy[key] = items
        elif key == "onProcessFailure":
            value = parse_boolean_text(raw_value)
            if value is not None:
                policy["onProcessFailure"] = value
    return policy


def first_section_lines(text: str, headings: list[str]) -> list[str]:
    for heading in headings:
        lines = section_lines(text, heading)
        if lines:
            return lines
    return []


def validate_frontmatter_schema(role_file: Path, frontmatter: dict[str, object]) -> None:
    if not frontmatter:
        return

    errors: list[str] = []
    unknown_keys = sorted(set(frontmatter) - ALLOWED_FRONTMATTER_KEYS)
    if unknown_keys:
        errors.append(f"unknown frontmatter keys: {', '.join(unknown_keys)}")

    for key in ("name", "type", "description"):
        if key not in frontmatter:
            errors.append(f"missing required frontmatter key '{key}'")
            continue
        value = frontmatter.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"frontmatter '{key}' must be a non-empty string")

    role_type = frontmatter.get("type")
    if isinstance(role_type, str) and role_type not in ALLOWED_ROLE_TYPES:
        errors.append(f"frontmatter 'type' must be one of: {', '.join(sorted(ALLOWED_ROLE_TYPES))}")

    for key in ("triggers", "best_for", "output_validation", "minimum_output", "takeover_statuses", "takeover_patterns"):
        if key not in frontmatter:
            continue
        value = frontmatter.get(key)
        if not isinstance(value, list):
            errors.append(f"frontmatter '{key}' must be a list")
            continue
        if any(not isinstance(item, str) or not item.strip() for item in value):
            errors.append(f"frontmatter '{key}' must contain only non-empty strings")

    for key in ("takeover_enabled", "takeover_on_process_failure"):
        if key in frontmatter and not isinstance(frontmatter.get(key), bool):
            errors.append(f"frontmatter '{key}' must be a boolean")

    if "minimum_output_aliases" in frontmatter:
        raw_aliases = frontmatter.get("minimum_output_aliases")
        if not isinstance(raw_aliases, list):
            errors.append("frontmatter 'minimum_output_aliases' must be a list")
        else:
            for alias in raw_aliases:
                if not isinstance(alias, str) or not alias.strip():
                    errors.append("frontmatter 'minimum_output_aliases' must contain only non-empty strings")
                    continue
                if "=>" not in alias:
                    errors.append("frontmatter 'minimum_output_aliases' entries must use 'source => alias' format")
                    continue
                source, target = (part.strip() for part in alias.split("=>", 1))
                if not source or not target:
                    errors.append("frontmatter 'minimum_output_aliases' entries must define both source and alias")

    output_validation = set(frontmatter_string_list(frontmatter, "output_validation"))
    unsupported_rules = sorted(output_validation - ALLOWED_OUTPUT_VALIDATION_RULES)
    if unsupported_rules:
        errors.append(f"unsupported output_validation rules: {', '.join(unsupported_rules)}")

    minimum_output = frontmatter_string_list(frontmatter, "minimum_output")
    if "markdown-headings" in output_validation and not minimum_output:
        errors.append("frontmatter 'output_validation' with markdown-headings requires 'minimum_output'")

    minimum_output_aliases = frontmatter_mapping(frontmatter, "minimum_output_aliases")
    if minimum_output_aliases and not minimum_output:
        errors.append("frontmatter 'minimum_output_aliases' requires 'minimum_output'")
    for source in minimum_output_aliases:
        if source not in minimum_output:
            errors.append(f"minimum_output_aliases source '{source}' must exist in minimum_output")

    takeover_fields = {"takeover_statuses", "takeover_patterns", "takeover_on_process_failure"}
    if any(key in frontmatter for key in takeover_fields) and "takeover_enabled" not in frontmatter:
        errors.append("takeover_statuses/takeover_patterns/takeover_on_process_failure require 'takeover_enabled'")

    takeover_enabled = frontmatter.get("takeover_enabled")
    takeover_statuses = frontmatter_string_list(frontmatter, "takeover_statuses")
    takeover_patterns = frontmatter_string_list(frontmatter, "takeover_patterns")
    takeover_on_process_failure = frontmatter.get("takeover_on_process_failure")
    if takeover_enabled is True and not takeover_statuses and not takeover_patterns and not bool(takeover_on_process_failure):
        errors.append(
            "enabled takeover policy must define takeover_statuses, takeover_patterns, or takeover_on_process_failure"
        )

    if errors:
        raise ValueError(f"{role_file}: invalid role metadata schema: {'; '.join(errors)}")


def validate_parsed_role_metadata(role_file: Path, metadata: dict[str, object]) -> None:
    errors: list[str] = []

    minimum_output = [str(item).strip() for item in metadata.get("minimumOutput", []) if str(item).strip()]
    if metadata.get("validateMarkdownStructure") and not minimum_output:
        errors.append("validateMarkdownStructure requires minimumOutput")

    aliases = metadata.get("minimumOutputAliases", {})
    if not isinstance(aliases, dict):
        errors.append("minimumOutputAliases must be a mapping")
    else:
        for source, target in aliases.items():
            source_text = str(source).strip()
            target_text = str(target).strip()
            if not source_text or not target_text:
                errors.append("minimumOutputAliases must contain non-empty source and alias values")
                continue
            if source_text not in minimum_output:
                errors.append(f"minimumOutputAliases source '{source_text}' must exist in minimumOutput")

    policy = metadata.get("mainAgentTakeoverPolicy", {})
    if not isinstance(policy, dict):
        errors.append("mainAgentTakeoverPolicy must be a mapping")
    else:
        if "enabled" in policy and not isinstance(policy.get("enabled"), bool):
            errors.append("mainAgentTakeoverPolicy.enabled must be a boolean")
        for key in ("statuses", "patterns"):
            if key not in policy:
                continue
            value = policy.get(key)
            if not isinstance(value, list) or any(not str(item).strip() for item in value):
                errors.append(f"mainAgentTakeoverPolicy.{key} must be a list of non-empty strings")
        if "onProcessFailure" in policy and not isinstance(policy.get("onProcessFailure"), bool):
            errors.append("mainAgentTakeoverPolicy.onProcessFailure must be a boolean")
        if (
            bool(policy.get("enabled"))
            and not list(policy.get("statuses", []))
            and not list(policy.get("patterns", []))
            and not bool(policy.get("onProcessFailure", False))
        ):
            errors.append("enabled mainAgentTakeoverPolicy must define statuses, patterns, or onProcessFailure")

    if errors:
        raise ValueError(f"{role_file}: invalid parsed role metadata: {'; '.join(errors)}")


def parse_role_doc(role_file: Path) -> dict[str, object]:
    text = read_text(role_file)
    frontmatter = parse_frontmatter(text) or {}
    validate_frontmatter_schema(role_file, frontmatter)

    minimum_output = frontmatter_string_list(frontmatter, "minimum_output")
    if not minimum_output:
        minimum_output = section_markdown_headings(text, SECTION_MINIMUM_OUTPUT, levels={2})
    if not minimum_output:
        minimum_output = section_markdown_headings(text, SECTION_OUTPUT_FORMAT, levels={2})

    structure_validation_rules = frontmatter_string_list(frontmatter, "output_validation")
    if not structure_validation_rules:
        structure_validation_rules = section_lines(text, SECTION_OUTPUT_VALIDATION)

    minimum_output_aliases = frontmatter_mapping(frontmatter, "minimum_output_aliases")
    if not minimum_output_aliases:
        minimum_output_aliases = section_mapping(text, SECTION_OUTPUT_VALIDATION_ALIASES)

    main_agent_takeover_policy = frontmatter_takeover_policy(frontmatter)
    if not main_agent_takeover_policy:
        main_agent_takeover_policy = parse_takeover_policy(text)

    parsed = {
        "name": frontmatter.get("name"),
        "type": frontmatter.get("type"),
        "description": frontmatter.get("description"),
        "bestFor": frontmatter.get("best_for", []),
        "inputSources": section_lines(text, SECTION_INPUT_SOURCES),
        "inputs": section_lines(text, SECTION_INPUTS),
        "outputs": section_lines(text, SECTION_OUTPUTS),
        "consumers": section_lines(text, SECTION_CONSUMERS),
        "responsibilities": section_lines(text, SECTION_RESPONSIBILITIES),
        "executionRules": section_lines(text, SECTION_EXECUTION_RULES),
        "evidenceRequirements": section_lines(text, SECTION_EVIDENCE_REQUIREMENTS),
        "antiPatterns": section_lines(text, SECTION_ANTI_PATTERNS),
        "hardBoundaries": first_section_lines(text, [SECTION_HARD_BOUNDARIES, SECTION_SUMMARY_RULES]),
        "minimumOutput": minimum_output,
        "validateMarkdownStructure": "markdown-headings" in structure_validation_rules,
        "minimumOutputAliases": minimum_output_aliases,
        "mainAgentTakeoverPolicy": main_agent_takeover_policy,
    }
    validate_parsed_role_metadata(role_file, parsed)
    return parsed
