#!/usr/bin/env python3
"""Generate Flow A stage-five skill execution worklist from the surface plan."""

from __future__ import annotations

from _bootstrap import bootstrap_paths

bootstrap_paths()

import argparse
import json
import sys
from pathlib import Path

from nexus_testing.flow_a_localization import add_output_language_argument
from nexus_testing.json_utils import load_json
from nexus_testing.sandbox_skill_invoke.core import write_text


def text(language: str, zh: str, en: str) -> str:
    return zh if language == "zh-CN" else en


def render_surface(surface: dict[str, object], language: str) -> str:
    source = surface.get("source", {})
    source_path = source.get("path", "unknown")
    source_key = source.get("key", "unknown")
    source_line = source.get("line")
    source_suffix = f":{source_line}" if isinstance(source_line, int) else ""
    target = surface.get("command") or surface.get("path") or surface.get("identifier")
    case_ids = ", ".join(str(item) for item in surface.get("testCaseIds", []))
    lines = [
        f"### {surface.get('surfaceId')} - {surface.get('kind')} (`{surface.get('identifier')}`)",
        f"- {text(language, 'minimum-mode', 'minimum-mode')}: `{surface.get('minimumMode')}`",
        f"- {text(language, 'primary-executor', 'primary-executor')}: `{surface.get('primaryExecutor')}`",
        f"- {text(language, 'secondary-executor', 'secondary-executor')}: `{surface.get('secondaryExecutor')}`",
        f"- {text(language, 'execution-target', 'execution-target')}: `{target}`",
        f"- {text(language, 'focus-areas', 'focus-areas')}: {', '.join(str(item) for item in surface.get('focusAreas', []))}",
        f"- {text(language, 'security-focus', 'security-focus')}: {', '.join(str(item) for item in surface.get('securityFocus', []))}",
        f"- {text(language, 'linked-capabilities', 'linked-capabilities')}: {', '.join(str(item) for item in surface.get('linkedCapabilityNames', [])) or text(language, '(无)', '(none)')}",
        f"- {text(language, 'source', 'source')}: `{source_path}{source_suffix} ({source_key})`",
        f"- {text(language, 'required-test-cases', 'required-test-cases')}: {case_ids or text(language, '(无)', '(none)')}",
        f"- {text(language, 'required-test-case-count', 'required-test-case-count')}: `{len(surface.get('testCaseIds', []))}`",
        f"- {text(language, 'execution-template', 'execution-template')}:",
        f"  - surface-id: `{surface.get('surfaceId')}`",
        f"  - {text(language, 'execution-level', 'execution-level')}: `{surface.get('minimumMode')}`",
        f"  - {text(language, 'status', 'status')}: `passed|blocked|incomplete`",
        f"  - {text(language, 'evidence', 'evidence')}: `<trace/output/log path>`",
        f"  - {text(language, 'executed-case-ids', 'executed-case-ids')}: `<TC-001, TC-002>`",
        f"  - {text(language, 'notes', 'notes')}: <{text(language, '简要结论', 'brief outcome')}>",
        "",
    ]
    return "\n".join(lines)


def build_coverage(plan: dict[str, object]) -> dict[str, object]:
    surfaces = []
    for surface in plan.get("surfaces", []):
        required_case_ids = [str(case_id) for case_id in surface.get("testCaseIds", []) if str(case_id).strip()]
        surfaces.append(
            {
                "surfaceId": surface.get("surfaceId"),
                "kind": surface.get("kind"),
                "identifier": surface.get("identifier"),
                "name": surface.get("name"),
                "path": surface.get("path"),
                "command": surface.get("command"),
                "minimumMode": surface.get("minimumMode"),
                "requiredCaseIds": required_case_ids,
                "requiredCaseCount": len(required_case_ids),
                "executedCaseIds": [],
                "executedCaseCount": 0,
                "caseResults": [
                    {
                        "caseId": case_id,
                        "status": "pending",
                        "evidence": [],
                    }
                    for case_id in required_case_ids
                ],
                "status": "pending",
                "executionLevel": None,
                "evidence": [],
                "notes": "",
            }
        )
    return {
        "packageName": plan.get("packageName", "unknown"),
        "parallelRoles": list(plan.get("parallelRoles", [])),
        "surfaces": surfaces,
    }


def build_worklist(plan: dict[str, object], language: str) -> str:
    title = str(plan.get("packageName", "unknown"))
    surfaces = list(plan.get("surfaces", []))
    lines = [
        f"# SKILL-SURFACE-WORKLIST - {title}",
        "",
        text(language, "## 阶段五规则", "## Stage-Five Rules"),
        "",
        text(language, "- 按顺序执行各个 surface；禁止只挑单一入口。", "- Execute surfaces in order; do not cherry-pick a single entry point."),
        text(language, "- 每个 surface 都必须在 `skill-results.md` 中生成一个结构化区块。", "- Every surface must produce one structured block in `skill-results.md`."),
        text(language, "- 每个区块都必须包含 `surface-id`、`execution-level`、`status`、`evidence` 和 `notes`。", "- Each block must include `surface-id`, `execution-level`, `status`, `evidence`, and `notes`."),
        text(language, "- `SURFACE-COVERAGE.json` 必须逐条回填 `requiredCaseIds`；未回填的 case 默认视为未执行。", "- `SURFACE-COVERAGE.json` must update every `requiredCaseIds` entry; untouched cases are treated as unexecuted."),
        text(language, "- 只做 surface smoke 或 spot check 时，surface 结论必须写 `incomplete`，不能把全部 required cases 写成 `passed`。", "- A surface must stay `incomplete` when only a smoke test or spot check ran; it cannot mark all required cases as `passed`."),
        text(language, "- 只拿到 trace 或 probe-only 证据的 surface，最终结论不得当成功能通过。", "- If a surface only reached trace or probe-only evidence, the final conclusion must not treat it as a functional pass."),
        "",
        text(language, "## 有序 Surface 工单", "## Ordered Surface Worklist"),
        "",
    ]
    for surface in surfaces:
        lines.append(render_surface(surface, language))

    lines.extend(
        [
            text(language, "## skill-results.md 必备结构", "## skill-results.md Required Shape"),
            "",
            "```text",
            "### SURFACE-XX - <kind> (`<identifier>`)",
            "- surface-id: `SURFACE-XX`",
            f"- {text(language, 'execution-level', 'execution-level')}: `live|shim-live|trace`",
            f"- {text(language, 'status', 'status')}: `passed|blocked|incomplete`",
            f"- {text(language, 'evidence', 'evidence')}: `<path1>, <path2>`",
            f"- {text(language, 'executed-case-ids', 'executed-case-ids')}: `<TC-001, TC-002>`",
            f"- {text(language, 'notes', 'notes')}: <{text(language, '简要结论', 'brief outcome')}>",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface-plan", required=True, help="Path to SURFACE-EXECUTION-PLAN.json")
    parser.add_argument("--output-dir", required=True, help="Report root directory")
    add_output_language_argument(parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    surface_plan_path = Path(args.surface_plan).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not surface_plan_path.exists():
        raise SystemExit(f"ERROR: surface plan does not exist: {surface_plan_path}")

    plan = load_json(surface_plan_path)
    execution_dir = output_dir / "TEST-EXECUTION"
    execution_dir.mkdir(parents=True, exist_ok=True)

    worklist_path = execution_dir / "SKILL-SURFACE-WORKLIST.md"
    coverage_path = execution_dir / "SURFACE-COVERAGE.json"
    write_text(worklist_path, build_worklist(plan, args.language) + "\n")
    write_text(coverage_path, json.dumps(build_coverage(plan), ensure_ascii=False, indent=2) + "\n")

    print(f"OUTPUT_DIR={output_dir}")
    print(f"WORKLIST={worklist_path}")
    print(f"SURFACE_COVERAGE={coverage_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
