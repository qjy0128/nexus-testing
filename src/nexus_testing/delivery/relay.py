from __future__ import annotations

import shutil
from pathlib import Path


def resolve_input(root: Path, path_value: str) -> Path:
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def build_target_path(root: Path, report_root: Path, source: Path) -> tuple[Path, str]:
    if report_root in source.parents:
        relative = source.relative_to(report_root)
        relay_relative = Path("files") / "nexus-reports" / relative
    elif root in source.parents:
        relative = source.relative_to(root)
        relay_relative = Path("files") / relative
    else:
        raise ValueError(f"report file must stay under the workspace root: {source}")
    return root / relay_relative, relay_relative.as_posix()


def mirror_report(root: Path, report_root: Path, source: Path) -> tuple[Path, str]:
    if not source.exists():
        raise FileNotFoundError(f"report file does not exist: {source}")
    if not source.is_file():
        raise ValueError(f"report file must be a file: {source}")
    target, relay_relative = build_target_path(root, report_root, source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target, relay_relative

