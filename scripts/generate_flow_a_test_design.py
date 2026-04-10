#!/usr/bin/env python3
"""Generate Flow A stage-three artifacts from the stage-one fingerprint."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from flow_a_localization import add_output_language_argument
from json_utils import load_json
from sandbox_skill_invoke.core import read_text, write_text


SURFACE_RULES: dict[str, dict[str, object]] = {
    "skill": {
        "label": "Skill Entry",
        "minimum_mode": "shim-live",
        "focus": ["routing", "argument-hint", "subcommand", "delivery"],
        "security_focus": ["prompt-injection", "unsafe-tooling", "delivery-bypass"],
    },
    "bin": {
        "label": "CLI Entry",
        "minimum_mode": "shim-live",
        "focus": ["command-invocation", "stdout-stderr", "exit-status", "invalid-args"],
        "security_focus": ["command-injection", "path-traversal", "unsafe-exec"],
    },
    "openclaw-extension": {
        "label": "Plugin Extension",
        "minimum_mode": "shim-live",
        "focus": ["registration", "hook-behavior", "runtime-loading"],
        "security_focus": ["hook-abuse", "privilege-escalation", "unsafe-side-effects"],
    },
    "plugin-manifest": {
        "label": "Plugin Manifest",
        "minimum_mode": "trace",
        "focus": ["manifest-integrity", "path-resolution", "extension-declaration"],
        "security_focus": ["malicious-manifest", "unexpected-extension", "tampering"],
    },
    "package": {
        "label": "Package Surface",
        "minimum_mode": "trace",
        "focus": ["install-contract", "runtime-requirement", "script-entry"],
        "security_focus": ["supply-chain", "postinstall-risk", "dependency-drift"],
    },
    "mcp": {
        "label": "MCP Surface",
        "minimum_mode": "shim-live",
        "focus": ["server-registration", "tool-contract", "invocation-shape"],
        "security_focus": ["tool-abuse", "parameter-injection", "protocol-mismatch"],
    },
}

STATIC_VALIDATION_SURFACE_KINDS = {
    "bin",
    "package",
    "plugin-manifest",
    "openclaw-extension",
    "mcp",
}


def text(language: str, zh: str, en: str) -> str:
    return zh if language == "zh-CN" else en


def surface_label(kind: str, fallback: str, language: str) -> str:
    labels = {
        "skill": ("Skill 入口", "Skill Entry"),
        "bin": ("CLI 入口", "CLI Entry"),
        "openclaw-extension": ("OpenClaw 扩展", "Plugin Extension"),
        "plugin-manifest": ("插件清单", "Plugin Manifest"),
        "package": ("Package 表面", "Package Surface"),
        "mcp": ("MCP 表面", "MCP Surface"),
    }
    zh, en = labels.get(kind, (fallback, fallback))
    return text(language, zh, en)


def ensure_passed_review(path: Path) -> None:
    text = read_text(path)
    if "`passed`" not in text:
        raise SystemExit(
            "ERROR: SPEC-CONSISTENCY-REVIEW.md is not passed; stage-three generation is blocked"
        )


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


def choose_mcp_binding(bin_surfaces: list[dict[str, object]]) -> dict[str, object] | None:
    if len(bin_surfaces) == 1:
        return bin_surfaces[0]

    keyword_candidates: list[dict[str, object]] = []
    for surface in bin_surfaces:
        probe_text = " ".join(
            str(surface.get(field, "")).lower() for field in ("name", "path", "command")
        )
        if any(keyword in probe_text for keyword in ("mcp", "modelcontextprotocol", "server")):
            keyword_candidates.append(surface)

    if len(keyword_candidates) == 1:
        return keyword_candidates[0]
    return None


def dedupe_surfaces(fingerprint: dict[str, object]) -> list[dict[str, object]]:
    surfaces: list[dict[str, object]] = []
    seen: set[str] = set()
    for surface in fingerprint.get("entrySurfaces", []):
        key = json.dumps(surface, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        surfaces.append(dict(surface))

    product_types = set(str(item) for item in fingerprint.get("productType", []))
    if "package" in product_types:
        synthetic = {
            "kind": "package",
            "name": fingerprint.get("packageName", "package"),
            "path": "package.json",
            "source": {"path": "package.json", "key": "name"},
        }
        key = json.dumps(synthetic, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            surfaces.append(synthetic)

    if "mcp" in product_types:
        selected_surface = choose_mcp_binding(
            [surface for surface in surfaces if str(surface.get("kind")) == "bin"]
        )
        synthetic: dict[str, object] = {
            "kind": "mcp",
            "name": "mcp-runtime",
            "path": "package.json",
            "command": None,
            "source": {"path": "package.json", "key": "dependencies"},
        }
        if selected_surface is not None:
            if isinstance(selected_surface.get("source"), dict):
                synthetic["source"] = dict(selected_surface["source"])
            synthetic["name"] = selected_surface.get("name") or synthetic["name"]
            synthetic["path"] = (
                selected_surface.get("path")
                or selected_surface.get("command")
                or synthetic["path"]
            )
            synthetic["command"] = selected_surface.get("command")
        key = json.dumps(synthetic, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            surfaces.append(synthetic)

    return surfaces


def related_capabilities(
    surface: dict[str, object], capabilities: list[dict[str, object]]
) -> list[dict[str, object]]:
    kind = str(surface.get("kind", "unknown"))
    path = str(surface.get("path") or "")
    matches: list[dict[str, object]] = []
    for capability in capabilities:
        source = capability.get("source", {})
        source_path = str(source.get("path") or "")
        cap_kind = str(capability.get("kind", "unknown"))
        if path and source_path == path:
            matches.append(capability)
            continue
        if kind == "package" and source_path == "package.json":
            matches.append(capability)
            continue
        if kind == "mcp" and cap_kind == "runtime-surface":
            matches.append(capability)
    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    for capability in matches:
        key = json.dumps(capability, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(capability)
    return deduped


def build_surface_inventory(
    fingerprint: dict[str, object],
    language: str,
) -> list[dict[str, object]]:
    inventory: list[dict[str, object]] = []
    capabilities = list(fingerprint.get("capabilitySurfaces", []))
    for index, surface in enumerate(dedupe_surfaces(fingerprint), start=1):
        kind = str(surface.get("kind", "unknown"))
        rule = SURFACE_RULES.get(kind, SURFACE_RULES["package"])
        identifier = surface.get("path") or surface.get("name") or surface.get("command") or f"{kind}-{index}"
        inventory.append(
            {
                "surfaceId": f"SURFACE-{index:02d}",
                "kind": kind,
                "label": surface_label(kind, str(rule["label"]), language),
                "identifier": str(identifier),
                "name": surface.get("name"),
                "path": surface.get("path"),
                "command": surface.get("command"),
                "minimumMode": rule["minimum_mode"],
                "primaryExecutor": "skill-tester",
                "secondaryExecutor": "security-tester",
                "focusAreas": list(rule["focus"]),
                "securityFocus": list(rule["security_focus"]),
                "source": surface.get("source"),
                "linkedCapabilities": related_capabilities(surface, capabilities),
            }
        )
    return inventory


def build_case(
    case_id: str,
    surface: dict[str, object],
    capability_id: str,
    test_dimension: str,
    category: str,
    title: str,
    objective: str,
    steps: list[str],
    expected: list[str],
) -> dict[str, object]:
    return {
        "caseId": case_id,
        "surfaceId": surface["surfaceId"],
        "surfaceKind": surface["kind"],
        "title": title,
        "category": category,
        "capabilityId": capability_id,
        "testDimension": test_dimension,
        "minimumMode": surface["minimumMode"],
        "primaryExecutor": surface["primaryExecutor"],
        "secondaryExecutor": surface["secondaryExecutor"],
        "objective": objective,
        "steps": steps,
        "expected": expected,
    }


def requires_detailed_inventory(capability: dict[str, object]) -> bool:
    name = str(capability.get("name", "")).lower()
    return any(
        token in name
        for token in ("scan", "rule", "policy", "guard", "action", "decision", "patrol", "check", "security")
    )


def inventory_warnings(surface_inventory: list[dict[str, object]], language: str) -> list[str]:
    warnings: list[str] = []
    for surface in surface_inventory:
        for capability in surface.get("linkedCapabilities", []):
            groups = list(capability.get("scenarioGroups", []))
            if groups or not requires_detailed_inventory(capability):
                continue
            capability_name = str(capability.get("name", "unknown"))
            warnings.append(
                text(
                    language,
                    f"能力 `{capability_name}` 看起来是规则/决策/检查项驱动，但事实指纹未抽取到明细 inventory；阶段四应阻塞并要求补全数据驱动用例。",
                    f"Capability `{capability_name}` looks rule/decision/check-driven, but the fingerprint did not extract a detailed inventory; stage four should block until data-driven cases are expanded.",
                )
            )
    return warnings


def build_rule_cases(
    language: str,
    surface: dict[str, object],
    capability_name: str,
    group_title: str,
    item: str,
    case_index: int,
) -> list[dict[str, object]]:
    return [
        build_case(
            f"TC-{case_index:03d}",
            surface,
            f"{surface['surfaceId']}-{capability_name}-RULE",
            "TD-17",
            "rule-positive",
            text(
                language,
                f"{surface['label']} 规则 `{item}` 检出",
                f"{surface['label']} rule `{item}` detection",
            ),
            text(
                language,
                f"验证 `{capability_name}` 的 `{group_title}` 条目 `{item}` 能被真实检出。",
                f"Verify `{capability_name}` inventory item `{item}` under `{group_title}` can be detected with real evidence.",
            ),
            [
                text(language, f"构造能命中 `{item}` 的最小输入。", f"Construct the smallest input that should trigger `{item}`."),
                text(language, "以声明的真实入口执行，而不是只读文档。", "Execute against the declared real surface instead of reading documentation only."),
                text(language, "记录真实输出与结构化证据。", "Capture the real output and structured evidence."),
            ],
            [
                text(language, f"`{item}` 被明确命中或拦截。", f"`{item}` is explicitly detected or blocked."),
                text(language, "证据可追溯到真实执行记录。", "Evidence is traceable to a real execution record."),
            ],
        ),
        build_case(
            f"TC-{case_index + 1:03d}",
            surface,
            f"{surface['surfaceId']}-{capability_name}-RULE-FP",
            "TD-17",
            "rule-negative",
            text(
                language,
                f"{surface['label']} 规则 `{item}` 不误报",
                f"{surface['label']} rule `{item}` no-false-positive",
            ),
            text(
                language,
                f"验证 `{capability_name}` 的 `{item}` 不会对安全样本产生误报。",
                f"Verify `{capability_name}` item `{item}` does not raise a false positive on a safe control sample.",
            ),
            [
                text(language, f"构造与 `{item}` 相邻但应放行的安全输入。", f"Construct a safe control input adjacent to `{item}`."),
                text(language, "用同一入口重复执行并保留证据。", "Run through the same surface and preserve evidence."),
            ],
            [
                text(language, f"`{item}` 不应把安全样本误判为风险。", f"`{item}` does not falsely classify the safe control as risky."),
                text(language, "结果明确说明为何未命中。", "The result explicitly explains why the item did not trigger."),
            ],
        ),
    ]


def build_decision_case(
    language: str,
    surface: dict[str, object],
    capability_name: str,
    group_title: str,
    item: str,
    case_index: int,
) -> dict[str, object]:
    return build_case(
        f"TC-{case_index:03d}",
        surface,
        f"{surface['surfaceId']}-{capability_name}-DECISION",
        "TD-06",
        "decision",
        text(
            language,
            f"{surface['label']} 决策路径 `{item}`",
            f"{surface['label']} decision path `{item}`",
        ),
        text(
            language,
            f"验证 `{capability_name}` 在 `{group_title}` 中声明的 `{item}` 路径能被真实走到。",
            f"Verify `{capability_name}` can reach the declared `{item}` path under `{group_title}`.",
        ),
        [
            text(language, f"准备应进入 `{item}` 的输入。", f"Prepare an input that should land on `{item}`."),
            text(language, "保留判定依据和结构化结果。", "Capture the decision rationale and structured result."),
        ],
        [
            text(language, f"输出明确落到 `{item}` 路径。", f"The output clearly lands on the `{item}` path."),
            text(language, "路径结论可追溯到真实执行证据。", "The path outcome is traceable to real execution evidence."),
        ],
    )


def build_check_case(
    language: str,
    surface: dict[str, object],
    capability_name: str,
    group_title: str,
    item: str,
    case_index: int,
) -> dict[str, object]:
    return build_case(
        f"TC-{case_index:03d}",
        surface,
        f"{surface['surfaceId']}-{capability_name}-CHECK",
        "TD-16",
        "check",
        text(
            language,
            f"{surface['label']} 检查项 `{item}`",
            f"{surface['label']} check `{item}`",
        ),
        text(
            language,
            f"验证 `{capability_name}` 的 `{group_title}` 条目 `{item}` 被真实执行，而不是只在报告中声明。",
            f"Verify `{capability_name}` item `{item}` under `{group_title}` is actually executed instead of merely claimed in prose.",
        ),
        [
            text(language, f"触发 `{item}` 所需的真实运行条件。", f"Trigger the real runtime condition required for `{item}`."),
            text(language, "记录检查动作、输入和输出。", "Record the check action, input, and output."),
        ],
        [
            text(language, f"`{item}` 产生真实执行证据。", f"`{item}` produces real execution evidence."),
            text(language, "不能退化成仅文档验证。", "The case does not collapse into a documentation-only check."),
        ],
    )


def build_generic_inventory_case(
    language: str,
    surface: dict[str, object],
    capability_name: str,
    group_title: str,
    item: str,
    case_index: int,
) -> dict[str, object]:
    return build_case(
        f"TC-{case_index:03d}",
        surface,
        f"{surface['surfaceId']}-{capability_name}-SCENARIO",
        "TD-01",
        "scenario",
        text(
            language,
            f"{surface['label']} 场景 `{item}`",
            f"{surface['label']} scenario `{item}`",
        ),
        text(
            language,
            f"验证 `{capability_name}` 在 `{group_title}` 中定义的场景 `{item}`。",
            f"Verify scenario `{item}` declared under `{group_title}` for `{capability_name}`.",
        ),
        [
            text(language, f"构造 `{item}` 场景输入。", f"Construct an input for scenario `{item}`."),
            text(language, "执行并采集真实结果。", "Execute and capture the real result."),
        ],
        [
            text(language, f"`{item}` 的期望行为被观测到。", f"The expected behavior for `{item}` is observed."),
            text(language, "结果与真实入口表面一致。", "The result remains anchored to the real entry surface."),
        ],
    )


def build_capability_cases(
    language: str,
    surface: dict[str, object],
    capability: dict[str, object],
    case_start: int,
) -> list[dict[str, object]]:
    capability_name = str(capability.get("name", "capability"))
    groups = list(capability.get("scenarioGroups", []))
    if not groups:
        return [
            build_case(
                f"TC-{case_start:03d}",
                surface,
                f"{surface['surfaceId']}-{capability_name}",
                "TD-01",
                "capability",
                text(
                    language,
                    f"{surface['label']} 能力 `{capability_name}`",
                    f"{surface['label']} capability `{capability_name}`",
                ),
                text(
                    language,
                    f"验证能力 `{capability_name}` 由真实入口表面驱动，而不是靠文档描述推断。",
                    f"Verify capability `{capability_name}` is driven by a real surface instead of prose-only assumptions.",
                ),
                [
                    text(language, f"触发 `{capability_name}` 的最小真实输入。", f"Run the smallest real input that should trigger `{capability_name}`."),
                    text(language, "捕获结构化证据。", "Capture structured evidence."),
                ],
                [
                    text(language, f"`{capability_name}` 可从声明入口观测到。", f"`{capability_name}` is observable from the declared surface."),
                    text(language, "结果可回溯到事实指纹。", "The result is traceable to the product fingerprint."),
                ],
            )
        ]

    cases: list[dict[str, object]] = []
    next_case = case_start
    for group in groups:
        group_title = str(group.get("title", "Details"))
        group_kind = str(group.get("kind", "scenario"))
        for item in group.get("items", []):
            item_text = str(item)
            if group_kind == "rule":
                cases.extend(
                    build_rule_cases(language, surface, capability_name, group_title, item_text, next_case)
                )
                next_case += 2
                continue
            if group_kind == "decision":
                cases.append(
                    build_decision_case(language, surface, capability_name, group_title, item_text, next_case)
                )
            elif group_kind == "check":
                cases.append(
                    build_check_case(language, surface, capability_name, group_title, item_text, next_case)
                )
            else:
                cases.append(
                    build_generic_inventory_case(language, surface, capability_name, group_title, item_text, next_case)
                )
            next_case += 1

    return cases


def build_cases(surface: dict[str, object], case_start: int, language: str) -> list[dict[str, object]]:
    identifier = str(surface["identifier"])
    surface_id = str(surface["surfaceId"])
    cases: list[dict[str, object]] = []

    if str(surface.get("kind", "")) in STATIC_VALIDATION_SURFACE_KINDS:
        cases.append(
            build_case(
                f"TC-{case_start:03d}",
                surface,
                f"{surface_id}-STRUCTURAL",
                "TD-02",
                "structural",
                text(language, f"{surface['label']} 结构完整性", f"{surface['label']} structural integrity"),
                text(
                    language,
                    f"验证结构化表面 `{identifier}` 可被解析并输出可审计证据。",
                    f"Verify the structured surface `{identifier}` can be parsed and emits auditable evidence.",
                ),
                [
                    text(language, f"定位 `{identifier}` 并执行结构化校验。", f"Resolve `{identifier}` and run structural validation."),
                    text(language, "确认关键字段与事实指纹一致。", "Confirm key fields remain consistent with the fingerprint."),
                    text(language, "保存结构化校验结果，避免退化成仅凭描述的结论。", "Persist structured validation output instead of relying on prose-only conclusions."),
                ],
                [
                    text(language, "表面文件存在且可解析。", "The surface file exists and is parseable."),
                    text(language, "校验结果包含结构化证据或明确 blocker。", "The validation result includes structured evidence or an explicit blocker."),
                ],
            )
        )
        return cases

    cases.append(
        build_case(
            f"TC-{case_start:03d}",
            surface,
            f"{surface_id}-BASE",
            "TD-01",
            "positive",
            text(language, f"{surface['label']} 正向路径", f"{surface['label']} positive path"),
            text(
                language,
                f"验证真实 `{surface['kind']}` 表面 `{identifier}` 能以真实证据被到达。",
                f"Verify the real {surface['kind']} surface `{identifier}` can be reached with real evidence.",
            ),
            [
                text(language, f"从仓库或运行时解析真实表面 `{identifier}`。", f"Resolve the real surface `{identifier}` from the repository or runtime."),
                text(language, f"以 `{surface['minimumMode']}` 模式调用或加载该表面。", f"Invoke or load the surface in `{surface['minimumMode']}` mode."),
                text(language, "采集触发、工具、输出或加载证据，不依赖自然语言描述。", "Capture trigger, tool, output, or load evidence instead of relying on prose."),
            ],
            [
                text(language, "该表面可被发现且与事实指纹一致。", "The surface is discoverable and matches the fingerprint."),
                text(language, "调用结果包含结构化证据或明确 blocker。", "The invocation result contains structured evidence or an explicit blocker."),
            ],
        )
    )
    cases.append(
        build_case(
            f"TC-{case_start + 1:03d}",
            surface,
            f"{surface_id}-NEG",
            "TD-06",
            "negative",
            text(language, f"{surface['label']} 逆向路径", f"{surface['label']} negative path"),
            text(language, "验证无效输入或不匹配请求不会被静默判通过。", "Verify invalid input or a non-matching request does not silently pass."),
            [
                text(language, "为同一表面构造不匹配或无效调用。", "Construct a non-matching or invalid invocation for the same surface."),
                text(language, "使用同样的证据要求执行。", "Run the invocation with the same evidence requirements."),
                text(language, "记录产品是拒绝、阻塞还是误路由。", "Record whether the product rejects, blocks, or misroutes the request."),
            ],
            [
                text(language, "不匹配请求不会产生假成功。", "A non-matching request does not produce a false success."),
                text(language, "系统返回显式拒绝、校验错误或 blocker。", "The system returns an explicit rejection, validation error, or blocker."),
            ],
        )
    )
    cases.append(
        build_case(
            f"TC-{case_start + 2:03d}",
            surface,
            f"{surface_id}-BOUNDARY",
            "TD-07",
            "boundary",
            text(language, f"{surface['label']} 边界与证据路径", f"{surface['label']} boundary and evidence path"),
            text(language, "验证边界路径仍能返回可审计证据。", "Verify the edge path still returns auditable evidence."),
            [
                text(language, f"覆盖一个由 {', '.join(surface['focusAreas'][:2])} 派生的边界条件。", f"Exercise one edge condition derived from {', '.join(surface['focusAreas'][:2])}."),
                text(language, "开启显式证据采集后重复执行。", "Repeat the run with explicit evidence capture enabled."),
                text(language, "确认输出、送达、注册或加载证据仍可检查。", "Check that output, delivery, registration, or load evidence remains inspectable."),
            ],
            [
                text(language, "边界用例不会退化成仅靠描述的未验证成功。", "The edge case does not collapse into an unverified prose-only success."),
                text(language, "仍可获取结构化证据，否则必须标记 blocked。", "Structured evidence is still available, or the case is marked blocked."),
            ],
        )
    )

    next_case = case_start + 3
    for capability in surface["linkedCapabilities"]:
        capability_cases = build_capability_cases(language, surface, capability, next_case)
        cases.extend(capability_cases)
        next_case += len(capability_cases)

    return cases


def build_execution_plan(
    fingerprint: dict[str, object],
    surface_inventory: list[dict[str, object]],
    language: str,
) -> dict[str, object]:
    surfaces: list[dict[str, object]] = []
    case_counter = 1
    for surface in surface_inventory:
        cases = build_cases(surface, case_counter, language)
        case_counter += len(cases)
        surfaces.append(
            {
                "surfaceId": surface["surfaceId"],
                "kind": surface["kind"],
                "identifier": surface["identifier"],
                "name": surface.get("name"),
                "path": surface.get("path"),
                "command": surface.get("command"),
                "minimumMode": surface["minimumMode"],
                "primaryExecutor": surface["primaryExecutor"],
                "secondaryExecutor": surface["secondaryExecutor"],
                "focusAreas": surface["focusAreas"],
                "securityFocus": surface["securityFocus"],
                "linkedCapabilityNames": [
                    str(item.get("name", "unknown")) for item in surface["linkedCapabilities"]
                ],
                "testCaseIds": [case["caseId"] for case in cases],
                "testCaseCount": len(cases),
                "source": surface.get("source"),
            }
        )
        surface["generatedCases"] = cases

    return {
        "targetPath": fingerprint.get("targetPath"),
        "resolvedRootPath": fingerprint.get("resolvedRootPath"),
        "targetSkillPath": fingerprint.get("targetSkillPath"),
        "packageName": fingerprint.get("packageName", "unknown"),
        "productType": list(fingerprint.get("productType", [])),
        "parallelRoles": ["skill-tester", "security-tester"],
        "totalCaseCount": case_counter - 1,
        "designWarnings": inventory_warnings(surface_inventory, language),
        "surfaces": surfaces,
    }


def build_case_execution_plan(
    fingerprint: dict[str, object],
    surface_inventory: list[dict[str, object]],
    execution_plan: dict[str, object],
) -> dict[str, object]:
    cases: list[dict[str, object]] = []
    for surface in surface_inventory:
        for case in surface.get("generatedCases", []):
            case_payload = dict(case)
            case_payload["identifier"] = surface["identifier"]
            case_payload["surfaceLabel"] = surface["label"]
            case_payload["surfaceSource"] = surface.get("source")
            case_payload["focusAreas"] = list(surface.get("focusAreas", []))
            case_payload["securityFocus"] = list(surface.get("securityFocus", []))
            case_payload["linkedCapabilityNames"] = [
                str(item.get("name", "unknown")) for item in surface.get("linkedCapabilities", [])
            ]
            case_payload["executionHints"] = build_case_execution_hints(case_payload)
            cases.append(case_payload)
    return {
        "targetPath": fingerprint.get("targetPath"),
        "resolvedRootPath": fingerprint.get("resolvedRootPath"),
        "targetSkillPath": fingerprint.get("targetSkillPath"),
        "packageName": fingerprint.get("packageName", "unknown"),
        "productType": list(fingerprint.get("productType", [])),
        "totalCaseCount": execution_plan.get("totalCaseCount", len(cases)),
        "parallelRoles": list(execution_plan.get("parallelRoles", [])),
        "cases": cases,
    }


def extract_case_tokens(case: dict[str, object]) -> list[str]:
    tokens = []
    for candidate in re.findall(r"`([^`]+)`", str(case.get("title", ""))):
        cleaned = candidate.strip()
        if cleaned:
            tokens.append(cleaned)
    return tokens


def build_case_execution_hints(case: dict[str, object]) -> dict[str, object]:
    category = str(case.get("category", "scenario"))
    minimum_mode = str(case.get("minimumMode", "shim-live"))
    title = str(case.get("title", "")).strip()
    objective = str(case.get("objective", "")).strip()
    token_candidates = extract_case_tokens(case)
    expected_keywords: list[str] = []
    verification_policy = "assertion-only"
    expect_trigger: str | None = None

    if category in {"positive", "boundary", "capability", "scenario", "rule-positive", "decision", "check"}:
        expect_trigger = "true"
    elif category in {"negative", "rule-negative"}:
        verification_policy = "manual-negative-review"

    if category == "decision":
        expected_keywords = [token for token in token_candidates if token.isupper()]
        verification_policy = "assertion-and-keyword"

    message_lines = [
        f"case-id={case.get('caseId')}",
        f"surface-id={case.get('surfaceId')}",
        f"title={title}",
        f"objective={objective}",
    ]
    if token_candidates:
        message_lines.append(f"focus={', '.join(token_candidates[:3])}")

    return {
        "message": "; ".join(line for line in message_lines if line),
        "mode": minimum_mode,
        "expectTrigger": expect_trigger,
        "requireDeliveryStatus": "delivered" if expect_trigger == "true" else None,
        "expectedKeywords": expected_keywords,
        "verificationPolicy": verification_policy,
    }


def render_surface_inventory(surface_inventory: list[dict[str, object]], language: str) -> str:
    lines = [
        text(language, "| Surface ID | 类型 | 标识 | 最低模式 | 主执行角色 |", "| Surface ID | Kind | Identifier | Minimum Mode | Primary Executor |"),
        text(language, "|------------|------|------|----------|------------|", "|------------|------|------------|--------------|------------------|"),
    ]
    for surface in surface_inventory:
        lines.append(
            f"| {surface['surfaceId']} | {surface['kind']} | {surface['identifier']} | {surface['minimumMode']} | {surface['primaryExecutor']} |"
        )
    return "\n".join(lines)


def render_branch_matrix(surface_inventory: list[dict[str, object]], language: str) -> str:
    lines = [
        text(language, "| Surface ID | 正向 | 逆向 | 边界 | 能力展开 |", "| Surface ID | Positive | Negative | Boundary | Capability |"),
        text(language, "|------------|------|------|------|----------|", "|------------|----------|----------|----------|------------|"),
    ]
    for surface in surface_inventory:
        cases = list(surface.get("generatedCases", []))
        counts = {"positive": 0, "negative": 0, "boundary": 0, "capability": 0}
        for case in cases:
            category = str(case["category"])
            if category.startswith("rule") or category.startswith("decision") or category.startswith("check") or category == "scenario":
                counts["capability"] += 1
            elif category == "structural":
                counts["positive"] += 1
            else:
                counts[category] += 1
        lines.append(
            f"| {surface['surfaceId']} | {counts['positive']} | {counts['negative']} | {counts['boundary']} | {counts['capability']} |"
        )
    return "\n".join(lines)


def render_capability_matrix(surface_inventory: list[dict[str, object]], language: str) -> str:
    lines = [
        text(language, "| Surface ID | 关联能力 | 用例数 |", "| Surface ID | Linked Capabilities | Case Count |"),
        text(language, "|------------|----------|--------|", "|------------|---------------------|------------|"),
    ]
    for surface in surface_inventory:
        capability_names = ", ".join(
            str(item.get("name", "unknown")) for item in surface["linkedCapabilities"]
        ) or text(language, "(无)", "(none)")
        lines.append(
            f"| {surface['surfaceId']} | {capability_names} | {len(surface.get('generatedCases', []))} |"
        )
    return "\n".join(lines)


def render_case(case: dict[str, object], language: str) -> str:
    lines = [
        f"#### {case['caseId']}: {case['title']}",
        f"- surface-id: `{case['surfaceId']}`",
        f"- capability-id: `{case['capabilityId']}`",
        f"- test-dimension: `{case['testDimension']}`",
        f"- category: `{case['category']}`",
        f"- {text(language, '执行环境', 'execution-environment')}: `{case['minimumMode']}`",
        f"- {text(language, '主执行角色', 'primary-executor')}: `{case['primaryExecutor']}`",
        f"- {text(language, '目标', 'objective')}: {case['objective']}",
        f"- {text(language, 'steps', 'steps')}:",
    ]
    lines.extend(f"  - {step}" for step in case["steps"])
    lines.append(f"- {text(language, '预期结果', 'expected-results')}:")
    lines.extend(f"  - {item}" for item in case["expected"])
    return "\n".join(lines)


def build_test_design_markdown(
    fingerprint: dict[str, object],
    surface_inventory: list[dict[str, object]],
    execution_plan: dict[str, object],
    language: str,
) -> str:
    title = str(fingerprint.get("packageName", "unknown"))
    lines = [
        f"# TEST-DESIGN - {title}",
        "",
        text(language, "## 测试策略", "## Test Strategy"),
        "",
        text(language, "- Flow A 必须按真实产品表面拆分执行，不能把混合目标压扁成单一 skill。", "- Flow A must split execution by real product surfaces instead of flattening a mixed target into one skill."),
        text(language, "- 每个表面至少覆盖正向、逆向和边界路径。", "- Every surface must include positive, negative, and boundary coverage at minimum."),
        text(language, "- `SURFACE-EXECUTION-PLAN.json` 是阶段五执行输入；任何 surface 都不得被静默跳过。", "- `SURFACE-EXECUTION-PLAN.json` is the stage-five execution input; no surface may be skipped silently."),
        text(language, f"- 当前自动生成用例数：`{execution_plan.get('totalCaseCount', 0)}`。", f"- Current auto-generated case count: `{execution_plan.get('totalCaseCount', 0)}`."),
        "",
        text(language, "## 表面清单", "## Surface Inventory"),
        "",
        render_surface_inventory(surface_inventory, language),
        "",
        text(language, "## 分支覆盖矩阵", "## Branch Coverage Matrix"),
        "",
        render_branch_matrix(surface_inventory, language),
        "",
        text(language, "## 测试用例", "## Test Cases"),
        "",
    ]

    warnings = list(execution_plan.get("designWarnings", []))
    if warnings:
        lines.extend(
            [
                text(language, "## 设计告警", "## Design Warnings"),
                "",
            ]
        )
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")

    for surface in surface_inventory:
        lines.append(f"### {surface['surfaceId']} - {surface['label']} (`{surface['identifier']}`)")
        lines.append("")
        lines.append(f"- {text(language, 'source', 'source')}: {render_source(surface.get('source'))}")
        lines.append(f"- {text(language, 'focus-areas', 'focus-areas')}: {', '.join(surface['focusAreas'])}")
        lines.append(f"- {text(language, 'security-focus', 'security-focus')}: {', '.join(surface['securityFocus'])}")
        lines.append("")
        for case in surface.get("generatedCases", []):
            lines.append(render_case(case, language))
            lines.append("")

    lines.extend(
        [
            text(language, "## 能力 × 表面覆盖矩阵", "## Capability x Surface Coverage Matrix"),
            "",
            render_capability_matrix(surface_inventory, language),
            "",
            text(language, "## 阶段五执行要求", "## Stage-Five Execution Requirements"),
            "",
            text(language, "- `skill-tester` 必须执行 `SURFACE-EXECUTION-PLAN.json` 中列出的每个 surface。", "- `skill-tester` must execute every surface listed in `SURFACE-EXECUTION-PLAN.json`."),
            text(language, "- `security-tester` 必须按 `securityFocus` 审查每个 surface，而不是只看仓库文档。", "- `security-tester` must review each surface against its `securityFocus`, not just repository prose."),
            text(language, "- 只拿到 trace 或 probe-only 证据的 surface 不得写成功能通过。", "- Any surface that only reaches trace or probe-only evidence must not be reported as a functional pass."),
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fingerprint", required=True, help="Path to PRODUCT-FINGERPRINT.json")
    parser.add_argument("--spec", required=True, help="Path to SPEC.md")
    parser.add_argument("--consistency-review", required=True, help="Path to SPEC-CONSISTENCY-REVIEW.md")
    parser.add_argument("--output-dir", required=True, help="Directory for stage-three artifacts")
    add_output_language_argument(parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    fingerprint_path = Path(args.fingerprint).expanduser().resolve()
    spec_path = Path(args.spec).expanduser().resolve()
    review_path = Path(args.consistency_review).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    for path in (fingerprint_path, spec_path, review_path):
        if not path.exists():
            raise SystemExit(f"ERROR: required input does not exist: {path}")

    _ = read_text(spec_path)
    ensure_passed_review(review_path)
    fingerprint = load_json(fingerprint_path)

    surface_inventory = build_surface_inventory(fingerprint, args.language)
    execution_plan = build_execution_plan(fingerprint, surface_inventory, args.language)
    case_execution_plan = build_case_execution_plan(fingerprint, surface_inventory, execution_plan)
    test_design = build_test_design_markdown(fingerprint, surface_inventory, execution_plan, args.language)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_text(output_dir / "TEST-DESIGN.md", test_design + "\n")
    write_text(
        output_dir / "SURFACE-EXECUTION-PLAN.json",
        json.dumps(execution_plan, ensure_ascii=False, indent=2) + "\n",
    )
    write_text(
        output_dir / "CASE-EXECUTION-PLAN.json",
        json.dumps(case_execution_plan, ensure_ascii=False, indent=2) + "\n",
    )

    print(f"OUTPUT_DIR={output_dir}")
    print(f"TEST_DESIGN={output_dir / 'TEST-DESIGN.md'}")
    print(f"SURFACE_EXECUTION_PLAN={output_dir / 'SURFACE-EXECUTION-PLAN.json'}")
    print(f"CASE_EXECUTION_PLAN={output_dir / 'CASE-EXECUTION-PLAN.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
