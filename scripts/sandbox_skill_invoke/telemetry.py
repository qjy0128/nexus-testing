"""Live telemetry protocol inspection and result payload parsing."""

from __future__ import annotations

import json
from pathlib import Path

from sandbox_skill_invoke.core import read_text

LIVE_TELEMETRY_PROTOCOL_VERSION = "nexus-live-telemetry/v1"
LIVE_TELEMETRY_SOURCE = "openclaw-runtime"
LIVE_TELEMETRY_REQUIRED_FIELDS = (
    "triggerMatched",
    "toolsCalled",
    "contextReferences",
    "deliveryStatus",
    "deliveryReceipts",
    "deliveryEvidence",
)


def extract_result_payload_from_text(raw_text: str) -> dict[str, object]:
    text = (raw_text or "").strip()
    if not text:
        return {}
    # Try direct JSON
    if text.startswith("{") and text.endswith("}"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return payload
    # Try NEXUS_RESULT_JSON= line
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("NEXUS_RESULT_JSON="):
            raw_value = stripped.split("=", 1)[1].strip()
            try:
                payload = json.loads(raw_value)
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}
    # Try NEXUS_RESULT_JSON_START / END block
    marker_start = "NEXUS_RESULT_JSON_START"
    marker_end = "NEXUS_RESULT_JSON_END"
    if marker_start in text and marker_end in text:
        inner = text.split(marker_start, 1)[1].split(marker_end, 1)[0].strip()
        try:
            payload = json.loads(inner)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def load_result_payload(result_file: Path, stdout_text: str = "", stderr_text: str = "") -> dict[str, object]:
    payload: dict[str, object] = {}
    if result_file.exists():
        try:
            payload = json.loads(read_text(result_file))
        except json.JSONDecodeError:
            payload = {}
    if not payload and stdout_text:
        payload = extract_result_payload_from_text(stdout_text)
    if not payload and stderr_text:
        payload = extract_result_payload_from_text(stderr_text)
    return payload


def inspect_live_runtime_telemetry(result_payload: dict[str, object]) -> dict[str, object]:
    protocol_version = str(result_payload.get("telemetryProtocolVersion", "")).strip()
    telemetry_source = str(result_payload.get("telemetrySource", "")).strip()
    issues: list[str] = []

    if not result_payload or not protocol_version:
        return {
            "status": "missing",
            "protocol_version": protocol_version or "missing",
            "telemetry_source": telemetry_source or "unknown",
            "issues": [
                f"OpenClaw CLI did not emit runtime telemetry protocol {LIVE_TELEMETRY_PROTOCOL_VERSION}"
            ],
        }

    if protocol_version != LIVE_TELEMETRY_PROTOCOL_VERSION:
        issues.append(
            f"expected telemetryProtocolVersion={LIVE_TELEMETRY_PROTOCOL_VERSION}, got {protocol_version}"
        )
    if telemetry_source != LIVE_TELEMETRY_SOURCE:
        issues.append(
            f"expected telemetrySource={LIVE_TELEMETRY_SOURCE}, got {telemetry_source or 'missing'}"
        )

    field_checks: list[tuple[str, type, str]] = [
        ("triggerMatched", bool, "boolean triggerMatched"),
        ("toolsCalled", list, "array toolsCalled"),
        ("contextReferences", list, "array contextReferences"),
        ("deliveryReceipts", list, "array deliveryReceipts"),
        ("deliveryEvidence", list, "array deliveryEvidence"),
    ]
    for field, expected_type, label in field_checks:
        value = result_payload.get(field)
        if not isinstance(value, expected_type):
            issues.append(f"runtime telemetry is missing {label}")

    delivery_status = str(result_payload.get("deliveryStatus", "")).strip()
    if not delivery_status:
        issues.append("runtime telemetry is missing non-empty deliveryStatus")

    return {
        "status": "passed" if not issues else "invalid",
        "protocol_version": protocol_version or "missing",
        "telemetry_source": telemetry_source or "unknown",
        "issues": issues,
    }


def merge_telemetry_payload(adapter_payload: dict[str, object], verifier_payload: dict[str, object]) -> dict[str, object]:
    merged = dict(adapter_payload)
    if not verifier_payload:
        return merged
    override_keys = (
        "triggerMatched", "toolsCalled", "contextReferences",
        "assistantMessage", "delivery", "deliveryStatus",
        "deliveryReceipt", "deliveryReceipts", "deliveryEvidence",
        "artifacts", "notes",
    )
    for key in override_keys:
        if key in verifier_payload:
            merged[key] = verifier_payload[key]
    return merged


def write_preferred_output(result_payload: dict[str, object], output_file: Path, stdout_text: str) -> None:
    from sandbox_skill_invoke.core import write_text

    assistant_message = str(result_payload.get("assistantMessage", "") or "")
    existing_output = read_text(output_file) if output_file.exists() else ""
    if assistant_message:
        write_text(
            output_file,
            assistant_message if assistant_message.endswith("\n") else assistant_message + "\n",
        )
    elif existing_output:
        return
    elif stdout_text:
        write_text(output_file, stdout_text)
    else:
        write_text(output_file, "")
