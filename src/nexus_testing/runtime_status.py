"""Normalized runtime status helpers for orchestration takeover logic."""

from __future__ import annotations

TAKEOVER_TRIGGER_STATUSES = {"blocked-env", "blocked-policy", "stalled"}

KNOWN_STATUSES = TAKEOVER_TRIGGER_STATUSES | {
    "blocked-dependency",
    "blocked-product",
    "blocked",
    "failed",
    "passed",
    "completed",
    "incomplete",
    "precondition-failed",
}

ENVIRONMENT_HINTS = (
    "gateway unavailable",
    "runtime unavailable",
    "environment limitation",
    "webreader",
    "mcp__",
    "tool unavailable",
    "tool missing",
    "no-openclaw",
    "no-real-exec",
    "no-adapter",
)

POLICY_HINTS = (
    "web_fetch",
    "web fetch",
    "web_fetch fallback",
    "web fetch fallback",
    "switched to",
    "switch to",
    "substitute",
    "substituted",
    "downgraded to",
    "degraded to",
    "alternate path",
)

DEPENDENCY_HINTS = (
    "missing input",
    "missing inputs",
    "missing deliverable",
    "missing deliverables",
    "missing artifact",
    "missing artifacts",
    "precondition",
    "dependency missing",
    "dependency unavailable",
)


def normalize_runtime_status(value: object) -> str:
    return str(value or "").strip().lower()


def build_runtime_haystack(parsed_stdout: dict[str, object], attempt: dict[str, object]) -> str:
    return "\n".join(
        str(item or "")
        for item in (
            parsed_stdout.get("note"),
            parsed_stdout.get("status"),
            " ".join(str(item) for item in parsed_stdout.get("blockers", [])),
            attempt.get("note"),
            attempt.get("stdout"),
            attempt.get("stderr"),
        )
    ).lower()


def classify_blocked_reason(haystack: str) -> str:
    if any(pattern in haystack for pattern in POLICY_HINTS):
        return "blocked-policy"
    if any(pattern in haystack for pattern in DEPENDENCY_HINTS):
        return "blocked-dependency"
    if any(pattern in haystack for pattern in ENVIRONMENT_HINTS):
        return "blocked-env"
    return "blocked-product"


def derive_runtime_status(parsed_stdout: dict[str, object], attempt: dict[str, object]) -> str:
    raw_status = normalize_runtime_status(parsed_stdout.get("status"))
    haystack = build_runtime_haystack(parsed_stdout, attempt)

    if bool(attempt.get("stalled")):
        return "stalled"
    if raw_status in KNOWN_STATUSES - {"blocked"}:
        return raw_status
    if raw_status == "blocked":
        return classify_blocked_reason(haystack)
    if raw_status:
        return raw_status
    if any(pattern in haystack for pattern in POLICY_HINTS):
        return "blocked-policy"
    if any(pattern in haystack for pattern in DEPENDENCY_HINTS):
        return "blocked-dependency"
    if any(pattern in haystack for pattern in ENVIRONMENT_HINTS):
        return "blocked-env"
    return ""


def matches_takeover_status(policy_statuses: set[str], raw_status: str, normalized_status: str) -> bool:
    if not policy_statuses:
        return False
    if normalized_status in policy_statuses or raw_status in policy_statuses:
        return True
    if normalized_status.startswith("blocked-") and "blocked" in policy_statuses:
        return True
    return False


def is_takeover_trigger_status(status: str) -> bool:
    return status in TAKEOVER_TRIGGER_STATUSES
