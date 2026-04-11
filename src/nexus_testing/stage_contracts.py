"""Stage input/output contract helpers for orchestration."""

from __future__ import annotations

from pathlib import Path


def _normalize_spec(item: object) -> str:
    text = str(item).strip().strip("`")
    if not text or text.startswith("("):
        return ""
    return text.replace("\\", "/")


def stage_required_inputs(stage: dict[str, object]) -> list[str]:
    value = stage.get("requiredInputs", [])
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        normalized = _normalize_spec(item)
        if normalized:
            items.append(normalized)
    return items


def _append_unique(target: list[str], candidate: str) -> None:
    if candidate not in target:
        target.append(candidate)


def verify_stage_preconditions(report_dir: Path, stage: dict[str, object]) -> dict[str, object]:
    required_inputs = stage_required_inputs(stage)
    missing_inputs: list[str] = []
    required_artifact_paths: list[str] = []
    artifact_base_dir = str(report_dir.resolve())

    for spec in required_inputs:
        if "*" in spec:
            matches = [path.resolve() for path in sorted(report_dir.glob(spec)) if path.is_file()]
            if not matches:
                missing_inputs.append(spec)
                continue
            for path in matches:
                _append_unique(required_artifact_paths, str(path))
            continue

        path = (report_dir / spec).resolve()
        _append_unique(required_artifact_paths, str(path))
        if not path.exists():
            missing_inputs.append(spec)

    return {
        "artifactBaseDir": artifact_base_dir,
        "requiredInputs": required_inputs,
        "requiredArtifactPaths": required_artifact_paths,
        "missingInputs": missing_inputs,
        "upstreamOutputsVerified": not missing_inputs,
    }
