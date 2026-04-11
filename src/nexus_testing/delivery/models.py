from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class DeliveryRequest:
    report_file: str
    source_path: str
    relay_path: str
    relay_abs_path: str
    channel: str
    caption: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class DeliveryReceipt:
    backend: str
    status: str
    receipt_id: str = ""
    stdout: str = ""
    stderr: str = ""
    command: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ConfirmationRecord:
    status: str
    note: str = ""
    confirmed_by: str = ""
    confirmed_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

