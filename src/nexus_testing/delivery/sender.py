from __future__ import annotations

import json
import subprocess
from pathlib import Path

from nexus_testing.delivery.models import DeliveryReceipt, DeliveryRequest


def _format_command(parts: list[str], request: DeliveryRequest) -> list[str]:
    mapping = {
        "report_file": request.report_file,
        "source_path": request.source_path,
        "relay_path": request.relay_path,
        "abs_relay_path": request.relay_abs_path,
        "channel": request.channel,
        "caption": request.caption,
    }
    return [part.format_map(mapping) for part in parts]


def relay_only_receipt() -> DeliveryReceipt:
    return DeliveryReceipt(
        backend="relay-only",
        status="prepared",
        details={"note": "relay file prepared but no sender backend was configured"},
    )


def run_command_sender(
    request: DeliveryRequest,
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int = 60,
) -> DeliveryReceipt:
    rendered = _format_command(command, request)
    proc = subprocess.run(
        rendered,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )
    if proc.returncode != 0:
        return DeliveryReceipt(
            backend="command",
            status="failed",
            stdout=proc.stdout,
            stderr=proc.stderr,
            command=rendered,
            details={"returnCode": proc.returncode},
        )

    payload: dict[str, object] = {}
    stdout = proc.stdout.strip()
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            payload = parsed

    receipt_id = str(payload.get("receiptId", "") or payload.get("receipt_id", "")).strip()
    status = str(payload.get("status", "")).strip() or "sent"
    evidence = [
        str(item).strip()
        for item in payload.get("evidence", [])
        if str(item).strip()
    ] if isinstance(payload.get("evidence"), list) else []
    return DeliveryReceipt(
        backend="command",
        status=status,
        receipt_id=receipt_id,
        stdout=proc.stdout,
        stderr=proc.stderr,
        command=rendered,
        evidence=evidence,
        details=payload,
    )

