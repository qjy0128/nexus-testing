"""Assertion evaluation and delivery metadata extraction."""

from __future__ import annotations

from pathlib import Path

from nexus_testing.sandbox_skill_invoke.core import session_relative


def normalize_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    return []


def normalize_context_references(value: object) -> list[int]:
    result: list[int] = []
    if not isinstance(value, list):
        return result
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def resolve_delivery_evidence_path(raw_value: str, session_dir: Path) -> Path | None:
    candidate = Path(raw_value.strip())
    path_like = (
        candidate.is_absolute()
        or "/" in raw_value
        or "\\" in raw_value
        or raw_value.startswith(".")
    )
    if not path_like:
        return None
    resolved = candidate.resolve() if candidate.is_absolute() else (session_dir / candidate).resolve()
    try:
        resolved.relative_to(session_dir.resolve())
    except ValueError:
        return None
    if not resolved.exists():
        return None
    return resolved


def dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in values:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def collect_delivery_metadata(
    result_payload: dict[str, object], session_dir: Path,
) -> tuple[str, list[str], list[str], list[str]]:
    status = "unknown"
    receipts: list[str] = []
    evidence_items: list[str] = []

    delivery = result_payload.get("delivery")
    if isinstance(delivery, dict):
        raw_status = str(delivery.get("status", "")).strip()
        if raw_status:
            status = raw_status
        for key in ("receipt", "receiptId"):
            raw_value = delivery.get(key)
            if raw_value:
                receipts.extend(normalize_string_list(raw_value))
        evidence_items.extend(normalize_string_list(delivery.get("evidence")))
        evidence_items.extend(normalize_string_list(delivery.get("proof")))

    top_status = str(result_payload.get("deliveryStatus", "")).strip()
    if top_status:
        status = top_status
    receipts.extend(normalize_string_list(result_payload.get("deliveryReceipt")))
    receipts.extend(normalize_string_list(result_payload.get("deliveryReceipts")))
    evidence_items.extend(normalize_string_list(result_payload.get("deliveryEvidence")))

    valid_evidence: list[str] = []
    invalid_evidence: list[str] = []
    for item in dedupe_strings(evidence_items):
        resolved = resolve_delivery_evidence_path(item, session_dir)
        if resolved is None:
            invalid_evidence.append(item)
        else:
            valid_evidence.append(session_relative(resolved, session_dir))

    return status, dedupe_strings(receipts), dedupe_strings(valid_evidence), dedupe_strings(invalid_evidence)


def evaluate_assertions(
    *,
    expect_trigger: str | None,
    require_tools: list[str],
    expect_context_refs: list[int],
    require_delivery_status: str | None,
    require_delivery_evidence: bool,
    actual_trigger: str,
    actual_tools: list[str],
    actual_context_refs: list[int],
    delivery_status: str,
    delivery_receipts: list[str],
    delivery_evidence: list[str],
    invalid_delivery_evidence: list[str],
) -> list[str]:
    failures: list[str] = []
    if expect_trigger is not None and actual_trigger != expect_trigger:
        failures.append(f"expected triggerMatched={expect_trigger}, got {actual_trigger}")
    if require_tools:
        actual_tool_set = {item.strip() for item in actual_tools if item.strip()}
        missing = [item for item in require_tools if item not in actual_tool_set]
        if missing:
            failures.append(f"missing expected tools: {', '.join(missing)}")
    if expect_context_refs:
        actual_ref_set = set(actual_context_refs)
        missing_refs = [str(item) for item in expect_context_refs if item not in actual_ref_set]
        if missing_refs:
            failures.append(f"missing expected context references: {', '.join(missing_refs)}")
    if require_delivery_status and delivery_status != require_delivery_status:
        failures.append(f"expected deliveryStatus={require_delivery_status}, got {delivery_status}")
    if require_delivery_evidence and not delivery_evidence:
        failures.append("delivery evidence is required but missing verified proof files")
    if invalid_delivery_evidence:
        failures.append(f"invalid delivery evidence paths: {', '.join(invalid_delivery_evidence)}")
    if require_delivery_status and not delivery_receipts and not delivery_evidence:
        failures.append("delivery status was asserted but neither receipts nor verified proof files were present")
    return failures
