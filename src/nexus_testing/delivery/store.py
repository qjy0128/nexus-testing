from __future__ import annotations

import json
from pathlib import Path

REPORT_ROOT_TOKEN = Path("memory") / "nexus-reports"


def _report_relative(report_file: Path) -> Path:
    parts = report_file.resolve().parts
    token_parts = REPORT_ROOT_TOKEN.parts
    for index in range(len(parts) - len(token_parts) + 1):
        if parts[index : index + len(token_parts)] == token_parts:
            return Path(*parts[index + len(token_parts) :])
    return Path(report_file.name)


def delivery_dir(report_file: Path) -> Path:
    return report_file.parent / "DELIVERY"


def delivery_record_path(report_file: Path) -> Path:
    relative = _report_relative(report_file).with_suffix(".delivery.json")
    return delivery_dir(report_file) / relative.as_posix().replace("/", "__")


def confirmation_record_path(report_file: Path) -> Path:
    relative = _report_relative(report_file).with_suffix(".confirmation.json")
    return delivery_dir(report_file) / relative.as_posix().replace("/", "__")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

