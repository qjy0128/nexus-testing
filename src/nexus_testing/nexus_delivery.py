#!/usr/bin/env python3
"""Prepare, send, confirm, and inspect delivery state for generated reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nexus_testing.delivery.confirmation import build_confirmation
from nexus_testing.delivery.models import DeliveryRequest
from nexus_testing.delivery.relay import mirror_report, resolve_input
from nexus_testing.delivery.sender import relay_only_receipt, run_command_sender
from nexus_testing.delivery.store import (
    confirmation_record_path,
    delivery_record_path,
    read_json,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = (ROOT / "memory" / "nexus-reports").resolve()


def build_request(report_file: Path, relay_abs: Path, relay_path: str, channel: str, caption: str) -> DeliveryRequest:
    try:
        report_relative = report_file.relative_to(ROOT).as_posix()
    except ValueError:
        report_relative = str(report_file)
    return DeliveryRequest(
        report_file=report_relative,
        source_path=report_relative,
        relay_path=relay_path,
        relay_abs_path=str(relay_abs),
        channel=channel,
        caption=caption,
    )


def ensure_report_file(report_file: Path) -> Path:
    resolved = report_file.resolve()
    if REPORT_ROOT not in resolved.parents:
        raise SystemExit(
            f"ERROR: delivery commands only support artifacts under {REPORT_ROOT}: {resolved}"
        )
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--report-file", required=True)

    send_parser = sub.add_parser("send")
    send_parser.add_argument("--report-file", required=True)
    send_parser.add_argument("--channel", default="telegram")
    send_parser.add_argument("--caption", default="")
    send_parser.add_argument("--backend", choices=("relay-only", "command"), default="relay-only")
    send_parser.add_argument("--command", dest="sender_command", nargs="+")
    send_parser.add_argument("--timeout-seconds", type=int, default=60)

    confirm_parser = sub.add_parser("confirm")
    confirm_parser.add_argument("--report-file", required=True)
    confirm_parser.add_argument("--status", choices=("accepted", "rejected", "needs-work"), required=True)
    confirm_parser.add_argument("--note", default="")
    confirm_parser.add_argument("--confirmed-by", default="")

    status_parser = sub.add_parser("status")
    status_parser.add_argument("--report-file", required=True)
    return parser.parse_args(argv)


def command_prepare(report_file: Path) -> dict[str, object]:
    relay_abs, relay_path = mirror_report(ROOT, REPORT_ROOT, report_file)
    payload = {
        "status": "prepared",
        "reportFile": str(report_file),
        "sendablePath": relay_path,
        "sendableAbs": str(relay_abs),
    }
    return payload


def command_send(
    report_file: Path,
    *,
    channel: str,
    caption: str,
    backend: str,
    command: list[str] | None,
    timeout_seconds: int,
) -> dict[str, object]:
    relay_abs, relay_path = mirror_report(ROOT, REPORT_ROOT, report_file)
    request = build_request(report_file, relay_abs, relay_path, channel, caption)
    if backend == "relay-only":
        receipt = relay_only_receipt()
    else:
        if not command:
            raise SystemExit("ERROR: --command is required when --backend command is used")
        receipt = run_command_sender(
            request,
            command,
            cwd=ROOT,
            timeout_seconds=timeout_seconds,
        )
    payload = {
        "request": request.to_dict(),
        "receipt": receipt.to_dict(),
    }
    write_json(delivery_record_path(report_file), payload)
    return payload


def command_confirm(report_file: Path, *, status: str, note: str, confirmed_by: str) -> dict[str, object]:
    record = build_confirmation(status=status, note=note, confirmed_by=confirmed_by)
    payload = record.to_dict()
    write_json(confirmation_record_path(report_file), payload)
    return payload


def command_status(report_file: Path) -> dict[str, object]:
    return {
        "delivery": read_json(delivery_record_path(report_file)),
        "confirmation": read_json(confirmation_record_path(report_file)),
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    report_file = ensure_report_file(resolve_input(ROOT, args.report_file))

    if args.command == "prepare":
        payload = command_prepare(report_file)
    elif args.command == "send":
        payload = command_send(
            report_file,
            channel=args.channel,
            caption=args.caption,
            backend=args.backend,
            command=args.sender_command,
            timeout_seconds=args.timeout_seconds,
        )
    elif args.command == "confirm":
        payload = command_confirm(
            report_file,
            status=args.status,
            note=args.note,
            confirmed_by=args.confirmed_by,
        )
    else:
        payload = command_status(report_file)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
