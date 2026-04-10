#!/usr/bin/env python3
"""Validation helpers for dispatch payloads and bundle manifests."""

from __future__ import annotations

from pathlib import Path

ALLOWED_DISPATCH_MODES = {"serial", "parallel"}
ALLOWED_ROLE_TYPES = {"executor", "validator"}
ALLOWED_RUN_MODES = {"test", "repair"}


def _non_empty_string(value: object, field: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{field} must be a non-empty string")
    return text


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    items = [str(item).strip() for item in value]
    if any(not item for item in items):
        raise ValueError(f"{field} must contain only non-empty strings")
    return items


def _string_mapping(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    parsed: dict[str, str] = {}
    for key, item in value.items():
        key_text = str(key).strip()
        item_text = str(item).strip()
        if not key_text or not item_text:
            raise ValueError(f"{field} must contain only non-empty string pairs")
        parsed[key_text] = item_text
    return parsed


def _takeover_policy(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    result: dict[str, object] = {}
    if "enabled" in value:
        if not isinstance(value.get("enabled"), bool):
            raise ValueError(f"{field}.enabled must be a boolean")
        result["enabled"] = value.get("enabled")
    if "statuses" in value:
        result["statuses"] = _string_list(value.get("statuses"), f"{field}.statuses")
    if "patterns" in value:
        result["patterns"] = _string_list(value.get("patterns"), f"{field}.patterns")
    if "onProcessFailure" in value:
        if not isinstance(value.get("onProcessFailure"), bool):
            raise ValueError(f"{field}.onProcessFailure must be a boolean")
        result["onProcessFailure"] = value.get("onProcessFailure")
    if (
        bool(result.get("enabled"))
        and not result.get("statuses")
        and not result.get("patterns")
        and not bool(result.get("onProcessFailure", False))
    ):
        raise ValueError(f"{field} enabled policy must define statuses, patterns, or onProcessFailure")
    return result


def validate_dispatch_payload(payload: object, *, field: str = "dispatch payload") -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError(f"{field} must be an object")

    role_id = _non_empty_string(payload.get("roleId"), f"{field}.roleId")
    role_file = _non_empty_string(payload.get("roleFile"), f"{field}.roleFile")
    role_type = _non_empty_string(payload.get("roleType"), f"{field}.roleType")
    if role_type not in ALLOWED_ROLE_TYPES:
        raise ValueError(f"{field}.roleType must be one of: {', '.join(sorted(ALLOWED_ROLE_TYPES))}")

    order = payload.get("order")
    if not isinstance(order, int) or order <= 0:
        raise ValueError(f"{field}.order must be a positive integer")

    stage_id = _non_empty_string(payload.get("stageId"), f"{field}.stageId")
    stage_label = _non_empty_string(payload.get("stageLabel"), f"{field}.stageLabel")
    stage_name = _non_empty_string(payload.get("stageName"), f"{field}.stageName")
    dispatch_mode = _non_empty_string(payload.get("dispatchMode"), f"{field}.dispatchMode")
    if dispatch_mode not in ALLOWED_DISPATCH_MODES:
        raise ValueError(f"{field}.dispatchMode must be one of: {', '.join(sorted(ALLOWED_DISPATCH_MODES))}")

    report_dir = _non_empty_string(payload.get("reportDir"), f"{field}.reportDir")
    run_mode = _non_empty_string(payload.get("runMode", "test"), f"{field}.runMode")
    if run_mode not in ALLOWED_RUN_MODES:
        raise ValueError(f"{field}.runMode must be one of: {', '.join(sorted(ALLOWED_RUN_MODES))}")
    missing_deliverables = _string_list(payload.get("missingDeliverables", []), f"{field}.missingDeliverables")
    available_artifacts = _string_list(payload.get("availableArtifacts", []), f"{field}.availableArtifacts")
    input_sources = _string_list(payload.get("inputSources", []), f"{field}.inputSources")
    inputs = _string_list(payload.get("inputs", []), f"{field}.inputs")
    outputs = _string_list(payload.get("outputs", []), f"{field}.outputs")
    consumers = _string_list(payload.get("consumers", []), f"{field}.consumers")
    responsibilities = _string_list(payload.get("responsibilities", []), f"{field}.responsibilities")
    execution_rules = _string_list(payload.get("executionRules", []), f"{field}.executionRules")
    evidence_requirements = _string_list(payload.get("evidenceRequirements", []), f"{field}.evidenceRequirements")
    anti_patterns = _string_list(payload.get("antiPatterns", []), f"{field}.antiPatterns")
    hard_boundaries = _string_list(payload.get("hardBoundaries", []), f"{field}.hardBoundaries")
    minimum_output = _string_list(payload.get("minimumOutput", []), f"{field}.minimumOutput")

    validate_markdown_structure = payload.get("validateMarkdownStructure", False)
    if not isinstance(validate_markdown_structure, bool):
        raise ValueError(f"{field}.validateMarkdownStructure must be a boolean")
    if validate_markdown_structure and not minimum_output:
        raise ValueError(f"{field}.validateMarkdownStructure requires minimumOutput")

    minimum_output_aliases = _string_mapping(payload.get("minimumOutputAliases", {}), f"{field}.minimumOutputAliases")
    for source in minimum_output_aliases:
        if source not in minimum_output:
            raise ValueError(f"{field}.minimumOutputAliases source '{source}' must exist in minimumOutput")

    main_agent_takeover_policy = _takeover_policy(
        payload.get("mainAgentTakeoverPolicy", {}),
        f"{field}.mainAgentTakeoverPolicy",
    )

    description_value = payload.get("description")
    if description_value is not None and not isinstance(description_value, str):
        raise ValueError(f"{field}.description must be a string when present")
    description = str(description_value).strip() if isinstance(description_value, str) else None
    best_for = _string_list(payload.get("bestFor", []), f"{field}.bestFor")
    launch_prompt = _non_empty_string(payload.get("launchPrompt"), f"{field}.launchPrompt")

    return {
        "roleId": role_id,
        "roleFile": role_file,
        "roleType": role_type,
        "order": order,
        "stageId": stage_id,
        "stageLabel": stage_label,
        "stageName": stage_name,
        "dispatchMode": dispatch_mode,
        "reportDir": report_dir,
        "runMode": run_mode,
        "missingDeliverables": missing_deliverables,
        "availableArtifacts": available_artifacts,
        "inputSources": input_sources,
        "inputs": inputs,
        "outputs": outputs,
        "consumers": consumers,
        "responsibilities": responsibilities,
        "executionRules": execution_rules,
        "evidenceRequirements": evidence_requirements,
        "antiPatterns": anti_patterns,
        "hardBoundaries": hard_boundaries,
        "minimumOutput": minimum_output,
        "validateMarkdownStructure": validate_markdown_structure,
        "minimumOutputAliases": minimum_output_aliases,
        "mainAgentTakeoverPolicy": main_agent_takeover_policy,
        "description": description,
        "bestFor": best_for,
        "launchPrompt": launch_prompt,
    }


def validate_dispatch_payload_list(payloads: object, *, field: str = "dispatchPayloads") -> list[dict[str, object]]:
    if not isinstance(payloads, list):
        raise ValueError(f"{field} must be a list")
    normalized = [validate_dispatch_payload(item, field=f"{field}[{index}]") for index, item in enumerate(payloads)]
    seen_role_ids: set[str] = set()
    seen_orders: set[int] = set()
    for payload in normalized:
        role_id = str(payload["roleId"])
        order = int(payload["order"])
        if role_id in seen_role_ids:
            raise ValueError(f"{field} contains duplicate roleId '{role_id}'")
        if order in seen_orders:
            raise ValueError(f"{field} contains duplicate order '{order}'")
        seen_role_ids.add(role_id)
        seen_orders.add(order)
    return normalized


def validate_bundle_manifest(manifest: object, *, field: str = "bundle manifest") -> dict[str, object]:
    if not isinstance(manifest, dict):
        raise ValueError(f"{field} must be an object")
    stage_id = _non_empty_string(manifest.get("stageId"), f"{field}.stageId")
    stage_label = _non_empty_string(manifest.get("stageLabel"), f"{field}.stageLabel")
    stage_name = _non_empty_string(manifest.get("stageName"), f"{field}.stageName")
    dispatch_mode = _non_empty_string(manifest.get("dispatchMode"), f"{field}.dispatchMode")
    if dispatch_mode not in ALLOWED_DISPATCH_MODES:
        raise ValueError(f"{field}.dispatchMode must be one of: {', '.join(sorted(ALLOWED_DISPATCH_MODES))}")
    status = _non_empty_string(manifest.get("status"), f"{field}.status")
    generated_at = _non_empty_string(manifest.get("generatedAt"), f"{field}.generatedAt")
    roles = manifest.get("roles")
    if not isinstance(roles, list) or not roles:
        raise ValueError(f"{field}.roles must be a non-empty list")

    normalized_roles: list[dict[str, object]] = []
    seen_role_ids: set[str] = set()
    seen_orders: set[int] = set()
    for index, item in enumerate(roles):
        entry_field = f"{field}.roles[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{entry_field} must be an object")
        role_id = _non_empty_string(item.get("roleId"), f"{entry_field}.roleId")
        order = item.get("order")
        if not isinstance(order, int) or order <= 0:
            raise ValueError(f"{entry_field}.order must be a positive integer")
        payload_file = _non_empty_string(item.get("payloadFile"), f"{entry_field}.payloadFile")
        prompt_file = _non_empty_string(item.get("promptFile"), f"{entry_field}.promptFile")
        if role_id in seen_role_ids:
            raise ValueError(f"{field} contains duplicate roleId '{role_id}'")
        if order in seen_orders:
            raise ValueError(f"{field} contains duplicate order '{order}'")
        seen_role_ids.add(role_id)
        seen_orders.add(order)
        normalized_roles.append(
            {
                "roleId": role_id,
                "order": order,
                "payloadFile": payload_file,
                "promptFile": prompt_file,
            }
        )

    return {
        "stageId": stage_id,
        "stageLabel": stage_label,
        "stageName": stage_name,
        "dispatchMode": dispatch_mode,
        "status": status,
        "generatedAt": generated_at,
        "roles": normalized_roles,
    }


def validate_bundle_files(bundle_dir: Path, manifest: dict[str, object], payloads: list[dict[str, object]]) -> None:
    by_role = {str(item["roleId"]): item for item in payloads}
    manifest_roles = manifest.get("roles", [])
    if not isinstance(manifest_roles, list):
        raise ValueError("bundle manifest roles must be a list")
    if len(manifest_roles) != len(payloads):
        raise ValueError("bundle manifest role count does not match dispatch payload count")
    for entry in manifest_roles:
        if not isinstance(entry, dict):
            raise ValueError("bundle manifest role entry must be an object")
        role_id = str(entry["roleId"])
        payload = by_role.get(role_id)
        if payload is None:
            raise ValueError(f"bundle manifest references unknown roleId '{role_id}'")
        if int(entry["order"]) != int(payload["order"]):
            raise ValueError(f"bundle manifest order mismatch for roleId '{role_id}'")
        payload_path = bundle_dir / str(entry["payloadFile"])
        prompt_path = bundle_dir / str(entry["promptFile"])
        if payload_path.name != f"{int(payload['order']):02d}-{role_id}.payload.json":
            raise ValueError(f"bundle manifest payloadFile mismatch for roleId '{role_id}'")
        if prompt_path.name != f"{int(payload['order']):02d}-{role_id}.prompt.md":
            raise ValueError(f"bundle manifest promptFile mismatch for roleId '{role_id}'")
        if not payload_path.is_file():
            raise ValueError(f"bundle manifest payloadFile is missing for roleId '{role_id}': {payload_path.name}")
        if not prompt_path.is_file():
            raise ValueError(f"bundle manifest promptFile is missing for roleId '{role_id}': {prompt_path.name}")
