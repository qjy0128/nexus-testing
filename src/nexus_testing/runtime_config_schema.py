#!/usr/bin/env python3
"""Validation helpers for nexus_runtime_bridge runtime-config files."""

from __future__ import annotations

ALLOWED_ROOT_KEYS = {
    "name",
    "default",
    "roles",
    "mainAgentTakeover",
    "mainAgentTakeoverPatterns",
    "mainAgentTakeoverPolicy",
}
ALLOWED_SPEC_KEYS = {
    "name",
    "command",
    "cwd",
    "env",
    "timeoutSeconds",
    "stallTimeoutSeconds",
    "fallback",
    "mainAgentTakeover",
    "mainAgentTakeoverPatterns",
    "mainAgentTakeoverPolicy",
}


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


def _env_map(value: object, field: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    normalized: dict[str, str] = {}
    for key, item in value.items():
        key_text = str(key).strip()
        item_text = str(item).strip()
        if not key_text or not item_text:
            raise ValueError(f"{field} must contain only non-empty string pairs")
        normalized[key_text] = item_text
    return normalized


def _takeover_policy(value: object, field: str) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    normalized: dict[str, object] = {}
    if "enabled" in value:
        if not isinstance(value.get("enabled"), bool):
            raise ValueError(f"{field}.enabled must be a boolean")
        normalized["enabled"] = value.get("enabled")
    if "statuses" in value:
        normalized["statuses"] = _string_list(value.get("statuses"), f"{field}.statuses")
    if "patterns" in value:
        normalized["patterns"] = _string_list(value.get("patterns"), f"{field}.patterns")
    if "onProcessFailure" in value:
        if not isinstance(value.get("onProcessFailure"), bool):
            raise ValueError(f"{field}.onProcessFailure must be a boolean")
        normalized["onProcessFailure"] = value.get("onProcessFailure")
    if (
        bool(normalized.get("enabled"))
        and not normalized.get("statuses")
        and not normalized.get("patterns")
        and not bool(normalized.get("onProcessFailure", False))
    ):
        raise ValueError(f"{field} enabled policy must define statuses, patterns, or onProcessFailure")
    return normalized


def validate_runtime_spec(spec: object, *, field: str = "runtime spec", require_command: bool = True) -> dict[str, object]:
    if not isinstance(spec, dict):
        raise ValueError(f"{field} must be an object")

    unknown_keys = sorted(set(spec) - ALLOWED_SPEC_KEYS)
    if unknown_keys:
        raise ValueError(f"{field} contains unknown keys: {', '.join(unknown_keys)}")

    normalized: dict[str, object] = {}
    name_value = spec.get("name")
    if name_value is not None:
        normalized["name"] = _non_empty_string(name_value, f"{field}.name")

    command_value = spec.get("command")
    if command_value is None:
        if require_command:
            raise ValueError(f"{field}.command is required")
    else:
        command = _string_list(command_value, f"{field}.command")
        if not command:
            raise ValueError(f"{field}.command must be a non-empty list")
        normalized["command"] = command

    cwd_value = spec.get("cwd")
    if cwd_value is not None:
        normalized["cwd"] = _non_empty_string(cwd_value, f"{field}.cwd")

    env = _env_map(spec.get("env"), f"{field}.env")
    if env is not None:
        normalized["env"] = env

    timeout_value = spec.get("timeoutSeconds")
    if timeout_value is not None:
        if not isinstance(timeout_value, int) or timeout_value <= 0:
            raise ValueError(f"{field}.timeoutSeconds must be a positive integer")
        normalized["timeoutSeconds"] = timeout_value

    stall_timeout_value = spec.get("stallTimeoutSeconds")
    if stall_timeout_value is not None:
        if not isinstance(stall_timeout_value, int) or stall_timeout_value <= 0:
            raise ValueError(f"{field}.stallTimeoutSeconds must be a positive integer")
        if isinstance(timeout_value, int) and stall_timeout_value >= timeout_value:
            raise ValueError(f"{field}.stallTimeoutSeconds must be smaller than timeoutSeconds")
        normalized["stallTimeoutSeconds"] = stall_timeout_value

    main_agent_takeover = spec.get("mainAgentTakeover")
    if main_agent_takeover is not None:
        if not isinstance(main_agent_takeover, bool):
            raise ValueError(f"{field}.mainAgentTakeover must be a boolean")
        normalized["mainAgentTakeover"] = main_agent_takeover

    takeover_patterns = spec.get("mainAgentTakeoverPatterns")
    if takeover_patterns is not None:
        normalized["mainAgentTakeoverPatterns"] = _string_list(
            takeover_patterns,
            f"{field}.mainAgentTakeoverPatterns",
        )

    takeover_policy = _takeover_policy(spec.get("mainAgentTakeoverPolicy"), f"{field}.mainAgentTakeoverPolicy")
    if takeover_policy is not None:
        normalized["mainAgentTakeoverPolicy"] = takeover_policy

    fallback_value = spec.get("fallback")
    if fallback_value is not None:
        normalized["fallback"] = validate_runtime_spec(
            fallback_value,
            field=f"{field}.fallback",
            require_command=True,
        )

    return normalized


def validate_runtime_config(config: object) -> dict[str, object]:
    if not isinstance(config, dict):
        raise ValueError("runtime config must be an object")

    unknown_keys = sorted(set(config) - ALLOWED_ROOT_KEYS)
    if unknown_keys:
        raise ValueError(f"runtime config contains unknown keys: {', '.join(unknown_keys)}")

    normalized: dict[str, object] = {}
    name_value = config.get("name")
    if name_value is not None:
        normalized["name"] = _non_empty_string(name_value, "runtime config.name")

    default_spec = config.get("default")
    if default_spec is None:
        raise ValueError("runtime config.default is required")
    normalized["default"] = validate_runtime_spec(default_spec, field="runtime config.default")

    roles = config.get("roles", {})
    if not isinstance(roles, dict):
        raise ValueError("runtime config.roles must be a mapping")
    normalized_roles: dict[str, dict[str, object]] = {}
    for role_id, spec in roles.items():
        role_name = str(role_id).strip()
        if not role_name:
            raise ValueError("runtime config.roles must use non-empty role ids")
        normalized_roles[role_name] = validate_runtime_spec(
            spec,
            field=f"runtime config.roles[{role_name}]",
            require_command=False,  # Role overrides inherit default.command when omitted
        )
    if normalized_roles:
        normalized["roles"] = normalized_roles

    main_agent_takeover = config.get("mainAgentTakeover")
    if main_agent_takeover is not None:
        if not isinstance(main_agent_takeover, bool):
            raise ValueError("runtime config.mainAgentTakeover must be a boolean")
        normalized["mainAgentTakeover"] = main_agent_takeover

    takeover_patterns = config.get("mainAgentTakeoverPatterns")
    if takeover_patterns is not None:
        normalized["mainAgentTakeoverPatterns"] = _string_list(
            takeover_patterns,
            "runtime config.mainAgentTakeoverPatterns",
        )

    takeover_policy = _takeover_policy(config.get("mainAgentTakeoverPolicy"), "runtime config.mainAgentTakeoverPolicy")
    if takeover_policy is not None:
        normalized["mainAgentTakeoverPolicy"] = takeover_policy

    return normalized
