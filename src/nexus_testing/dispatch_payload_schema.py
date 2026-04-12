#!/usr/bin/env python3
"""Validation helpers for dispatch payloads and bundle manifests."""

from __future__ import annotations

from pathlib import Path

from nexus_testing.runtime.policy import EXECUTION_PROFILES, resolve_execution_policy

ALLOWED_DISPATCH_MODES = {"serial", "parallel"}
ALLOWED_ROLE_TYPES = {"executor", "validator"}
ALLOWED_RUN_MODES = {"test", "repair"}
ALLOWED_EXECUTION_PROFILES = set(EXECUTION_PROFILES)
ALLOWED_DELIVERY_BACKENDS = {"relay-only", "command"}


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


def _execution_policy(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    result: dict[str, object] = {}
    name = _non_empty_string(value.get("name"), f"{field}.name")
    if name not in ALLOWED_EXECUTION_PROFILES:
        raise ValueError(f"{field}.name must be one of: {', '.join(sorted(ALLOWED_EXECUTION_PROFILES))}")
    result["name"] = name
    for key in ("strict_real", "prefer_host_execution", "run_security_scan"):
        raw = value.get(key)
        if not isinstance(raw, bool):
            raise ValueError(f"{field}.{key} must be a boolean")
        result[key] = raw
    backend = _non_empty_string(value.get("default_sender_backend"), f"{field}.default_sender_backend")
    if backend not in ALLOWED_DELIVERY_BACKENDS:
        raise ValueError(f"{field}.default_sender_backend must be one of: {', '.join(sorted(ALLOWED_DELIVERY_BACKENDS))}")
    result["default_sender_backend"] = backend
    return result


def _delivery_config(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    result: dict[str, object] = {}
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(f"{field}.enabled must be a boolean")
    result["enabled"] = enabled
    auto_send = value.get("autoSendOnComplete", True)
    if not isinstance(auto_send, bool):
        raise ValueError(f"{field}.autoSendOnComplete must be a boolean")
    result["autoSendOnComplete"] = auto_send
    result["channel"] = _non_empty_string(value.get("channel", "telegram"), f"{field}.channel")
    caption_value = value.get("caption", "")
    if not isinstance(caption_value, str):
        raise ValueError(f"{field}.caption must be a string")
    result["caption"] = caption_value
    backend = _non_empty_string(value.get("backend", "relay-only"), f"{field}.backend")
    if backend not in ALLOWED_DELIVERY_BACKENDS:
        raise ValueError(f"{field}.backend must be one of: {', '.join(sorted(ALLOWED_DELIVERY_BACKENDS))}")
    result["backend"] = backend
    result["command"] = _string_list(value.get("command", []), f"{field}.command")
    timeout_value = value.get("timeoutSeconds", 60)
    if not isinstance(timeout_value, int) or timeout_value <= 0:
        raise ValueError(f"{field}.timeoutSeconds must be a positive integer")
    result["timeoutSeconds"] = timeout_value
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
    artifact_base_dir = _non_empty_string(payload.get("artifactBaseDir", report_dir), f"{field}.artifactBaseDir")
    required_artifact_paths = _string_list(payload.get("requiredArtifactPaths", []), f"{field}.requiredArtifactPaths")
    upstream_outputs_verified = payload.get("upstreamOutputsVerified", True)
    if not isinstance(upstream_outputs_verified, bool):
        raise ValueError(f"{field}.upstreamOutputsVerified must be a boolean")
    run_mode = _non_empty_string(payload.get("runMode", "test"), f"{field}.runMode")
    if run_mode not in ALLOWED_RUN_MODES:
        raise ValueError(f"{field}.runMode must be one of: {', '.join(sorted(ALLOWED_RUN_MODES))}")
    execution_profile = _non_empty_string(payload.get("executionProfile", "internal-fast"), f"{field}.executionProfile")
    if execution_profile not in ALLOWED_EXECUTION_PROFILES:
        raise ValueError(f"{field}.executionProfile must be one of: {', '.join(sorted(ALLOWED_EXECUTION_PROFILES))}")
    strict_real = payload.get("strictReal", False)
    if not isinstance(strict_real, bool):
        raise ValueError(f"{field}.strictReal must be a boolean")
    default_execution_policy = resolve_execution_policy(execution_profile, strict_real).to_dict()
    execution_policy = _execution_policy(payload.get("executionPolicy", default_execution_policy), f"{field}.executionPolicy")
    delivery = _delivery_config(
        payload.get(
            "delivery",
            {
                "enabled": True,
                "autoSendOnComplete": True,
                "channel": "telegram",
                "caption": "",
                "backend": str(default_execution_policy["default_sender_backend"]),
                "command": [],
                "timeoutSeconds": 60,
            },
        ),
        f"{field}.delivery",
    )
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

    definition_excerpt_value = payload.get("definitionExcerpt")
    if definition_excerpt_value is not None and not isinstance(definition_excerpt_value, str):
        raise ValueError(f"{field}.definitionExcerpt must be a string when present")
    definition_excerpt: str | None = (
        definition_excerpt_value.strip() if isinstance(definition_excerpt_value, str) else None
    )

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
        "artifactBaseDir": artifact_base_dir,
        "requiredArtifactPaths": required_artifact_paths,
        "upstreamOutputsVerified": upstream_outputs_verified,
        "runMode": run_mode,
        "executionProfile": execution_profile,
        "strictReal": strict_real,
        "executionPolicy": execution_policy,
        "delivery": delivery,
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
        "definitionExcerpt": definition_excerpt,
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
