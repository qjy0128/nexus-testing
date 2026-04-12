"""On-demand section loader for DEFINITIONS.md.

Sections in DEFINITIONS.md are delimited by HTML comment markers of the form:
    <!-- section:section-id -->

This module extracts only the requested sections, reducing the token footprint
per dispatch payload compared to injecting the full 847-line file.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFINITIONS_PATH = ROOT / "DEFINITIONS.md"

# Regex: matches <!-- section:xxx --> marker lines
_SECTION_MARKER_RE = re.compile(r"<!--\s*section:(\S+?)\s*-->")

# ---------------------------------------------------------------------------
# Role → section dependency mapping
# Each role lists only the DEFINITIONS sections it actually needs at runtime.
# Unlisted roles fall back to DEFAULT_SECTIONS.
# ---------------------------------------------------------------------------

DEFAULT_SECTIONS: list[str] = ["stages", "artifact-flow", "report-dir"]

ROLE_SECTION_DEPS: dict[str, list[str]] = {
    "environment-checker": [
        "stages", "flow-config", "timeouts", "sandbox-env",
    ],
    "requirement-analyst": [
        "stages", "artifact-flow", "report-dir",
        "role-classification", "role-io",
    ],
    "spec-consistency-validator": [
        "stages", "artifact-flow", "report-dir",
    ],
    "quality-assessor": [
        "stages", "artifact-flow", "report-dir",
        "token-budget", "execution-verification",
    ],
    "test-designer": [
        "stages", "artifact-flow", "report-dir",
        "flow-config", "token-budget", "execution-verification",
        "test-dimension-matrix",
    ],
    "test-case-evaluator": [
        "stages", "artifact-flow", "report-dir",
        "token-budget", "execution-verification",
    ],
    "skill-tester": [
        "stages", "artifact-flow", "report-dir",
        "flow-config", "token-budget",
        "channel-degradation", "execution-verification",
    ],
    "security-tester": [
        "stages", "artifact-flow", "report-dir",
        "token-budget", "execution-verification",
    ],
    "functional-tester": [
        "stages", "artifact-flow", "report-dir",
        "token-budget", "execution-verification",
    ],
    "compatibility-tester": [
        "stages", "artifact-flow", "report-dir",
        "token-budget", "execution-verification",
    ],
    "performance-tester": [
        "stages", "artifact-flow", "report-dir",
        "token-budget", "execution-verification",
    ],
    "accessibility-auditor": [
        "stages", "artifact-flow", "report-dir",
        "token-budget", "execution-verification",
    ],
    "mcp-tester": [
        "stages", "artifact-flow", "report-dir",
        "token-budget", "execution-verification",
    ],
    "reality-checker": [
        "stages", "artifact-flow", "report-dir",
        "execution-verification",
    ],
    "evidence-collector": [
        "stages", "artifact-flow", "report-dir",
        "execution-verification",
    ],
    "defect-analyst": [
        "stages", "artifact-flow", "report-dir",
        "token-budget", "execution-verification",
    ],
    "report-integrator": [
        "stages", "artifact-flow", "report-dir",
        "token-budget", "execution-verification",
        "skill-classification",
    ],
    "experience-tester-a": [
        "stages", "artifact-flow", "report-dir",
        "token-budget", "execution-verification",
    ],
    "experience-tester-b": [
        "stages", "artifact-flow", "report-dir",
        "token-budget", "execution-verification",
    ],
}


def _parse_sections(text: str) -> dict[str, str]:
    """Parse DEFINITIONS.md text into a dict of {section_id: section_content}."""
    sections: dict[str, str] = {}
    current_id: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines(keepends=True):
        m = _SECTION_MARKER_RE.match(line.strip())
        if m:
            # Save previous section
            if current_id is not None:
                sections[current_id] = "".join(current_lines).rstrip()
            current_id = m.group(1)
            current_lines = []
        else:
            if current_id is not None:
                current_lines.append(line)

    # Save last section
    if current_id is not None:
        sections[current_id] = "".join(current_lines).rstrip()

    return sections


def load_sections(
    section_ids: list[str],
    definitions_path: Path | None = None,
) -> str:
    """Extract and concatenate the requested sections from DEFINITIONS.md.

    Args:
        section_ids: List of section identifiers (e.g. ["stages", "token-budget"]).
        definitions_path: Override path for testing; defaults to DEFINITIONS_PATH.

    Returns:
        Concatenated markdown text for the requested sections, separated by blank
        lines.  Sections not found are silently skipped.
    """
    path = definitions_path or DEFINITIONS_PATH
    text = path.read_text(encoding="utf-8")
    parsed = _parse_sections(text)

    parts: list[str] = []
    for sid in section_ids:
        if sid in parsed:
            parts.append(parsed[sid])

    return "\n\n".join(parts)


def load_sections_for_role(
    role_id: str,
    definitions_path: Path | None = None,
) -> str:
    """Load DEFINITIONS.md sections required by the given role.

    Falls back to DEFAULT_SECTIONS for unknown roles.
    """
    section_ids = ROLE_SECTION_DEPS.get(role_id, DEFAULT_SECTIONS)
    return load_sections(section_ids, definitions_path=definitions_path)


def sections_for_role(role_id: str) -> list[str]:
    """Return the section ID list for a given role (without loading content)."""
    return ROLE_SECTION_DEPS.get(role_id, DEFAULT_SECTIONS)
