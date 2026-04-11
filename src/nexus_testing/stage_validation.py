"""Lightweight stage artifact validation before approval gates."""

from __future__ import annotations

import json
import re
from pathlib import Path

from nexus_testing.role_metadata import parse_role_doc
from nexus_testing.sandbox_skill_invoke.core import read_text

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
PLACEHOLDER_RE = re.compile(r"^(mock|todo|tbd|placeholder|n/?a|待补充|待填写|略)\b", re.IGNORECASE)
MIN_SUBSTANTIVE_LINE_LENGTH = 12


def normalize_heading_marker(text: str) -> str:
    normalized = str(text).strip()
    normalized = re.sub(r"^[#\s]+", "", normalized)
    normalized = re.sub(r"[`*_]+", "", normalized)
    normalized = normalized.replace("锛?, ", ":")
    return normalized.strip().lower()


def normalize_content_line(line: str) -> str:
    normalized = str(line).strip()
    normalized = re.sub(r"^[-*+]\s*", "", normalized)
    normalized = re.sub(r"^\d+[.)]\s*", "", normalized)
    normalized = normalized.strip("`*_ ")
    return normalized.strip()


def is_substantive_line(line: str) -> bool:
    normalized = normalize_content_line(line)
    if not normalized:
        return False
    if PLACEHOLDER_RE.match(normalized):
        return False
    return len(normalized) >= MIN_SUBSTANTIVE_LINE_LENGTH


def extract_markdown_sections(text: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return sections
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        heading = match.group(2).strip()
        body = text[start:end].splitlines()
        sections.append((heading, body))
    return sections


def section_map(text: str) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for heading, body in extract_markdown_sections(text):
        normalized = normalize_heading_marker(heading)
        if normalized and normalized not in mapping:
            mapping[normalized] = body
    return mapping


def summarize_artifact(path: Path) -> dict[str, object]:
    summary: dict[str, object] = {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "sizeBytes": 0,
        "preview": [],
        "headings": [],
    }
    if not path.exists() or not path.is_file():
        return summary
    try:
        stat = path.stat()
        summary["sizeBytes"] = int(stat.st_size)
    except OSError:
        summary["sizeBytes"] = 0
    text = path.read_text(encoding="utf-8-sig")
    preview: list[str] = []
    for line in text.splitlines():
        normalized = normalize_content_line(line)
        if not normalized:
            continue
        preview.append(normalized[:160])
        if len(preview) >= 3:
            break
    summary["preview"] = preview
    if path.suffix.lower() == ".md":
        summary["headings"] = [match.group(2).strip() for match in HEADING_RE.finditer(text)]
    return summary


def validate_json_artifact(path: Path, issues: list[str]) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        issues.append(f"{path.name} is not valid JSON: {exc.msg}")
        return
    if path.name == "SURFACE-EXECUTION-PLAN.json":
        surfaces = payload.get("surfaces", []) if isinstance(payload, dict) else []
        if not isinstance(surfaces, list) or not surfaces:
            issues.append(f"{path.name} must contain at least one surface")


def validate_markdown_artifact(path: Path, metadata: dict[str, object], issues: list[str]) -> dict[str, object]:
    text = read_text(path)
    markers = section_map(text)
    aliases = metadata.get("minimumOutputAliases", {})
    if not isinstance(aliases, dict):
        aliases = {}
    minimum_output = [str(item).strip() for item in metadata.get("minimumOutput", []) if str(item).strip()]

    section_checks: list[dict[str, object]] = []
    for heading in minimum_output:
        accepted = {
            normalize_heading_marker(heading),
            normalize_heading_marker(str(aliases.get(heading, heading))),
        }
        accepted.discard("")
        matched_key = next((marker for marker in accepted if marker in markers), None)
        if not matched_key:
            issues.append(f"{path.name} is missing required section {heading}")
            section_checks.append({"heading": heading, "present": False, "substantive": False})
            continue
        substantive = any(is_substantive_line(line) for line in markers.get(matched_key, []))
        if not substantive:
            issues.append(f"{path.name} section {heading} does not contain substantive content")
        section_checks.append({"heading": heading, "present": True, "substantive": substantive})
    return {"path": str(path.resolve()), "sectionChecks": section_checks}


def validate_stage_artifacts(report_dir: Path, stage: dict[str, object]) -> dict[str, object]:
    issues: list[str] = []
    checked_files: list[str] = []
    file_summaries: list[dict[str, object]] = []
    markdown_validation: list[dict[str, object]] = []
    roles = [item for item in stage.get("roles", []) if isinstance(item, dict)]
    deliverables = [str(item) for item in stage.get("deliverables", []) if str(item).strip() and not str(item).startswith("(")]

    metadata: dict[str, object] = {}
    if roles:
        role_file = Path(str(roles[-1].get("file", "")))
        if role_file.exists():
            metadata = parse_role_doc(role_file)

    for relative in deliverables:
        if "*" in relative:
            matches = [path for path in sorted(report_dir.glob(relative)) if path.is_file()]
            if not matches:
                issues.append(f"missing deliverable {relative}")
                continue
            for path in matches:
                checked_files.append(str(path.resolve()))
                summary = summarize_artifact(path)
                file_summaries.append(summary)
                if not path.read_text(encoding="utf-8-sig").strip():
                    issues.append(f"{path.name} is empty")
            continue

        path = report_dir / relative
        checked_files.append(str(path.resolve()))
        summary = summarize_artifact(path)
        file_summaries.append(summary)
        if not path.exists():
            issues.append(f"missing deliverable {relative}")
            continue
        if not path.read_text(encoding="utf-8-sig").strip():
            issues.append(f"{path.name} is empty")
            continue
        if path.suffix.lower() == ".json":
            validate_json_artifact(path, issues)
            continue
        if path.suffix.lower() == ".md" and bool(metadata.get("validateMarkdownStructure")):
            markdown_validation.append(validate_markdown_artifact(path, metadata, issues))

    return {
        "ok": not issues,
        "issues": issues,
        "checkedFiles": checked_files,
        "fileSummaries": file_summaries,
        "markdownValidation": markdown_validation,
    }
