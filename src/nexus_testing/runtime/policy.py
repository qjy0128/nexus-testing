from __future__ import annotations

from dataclasses import asdict, dataclass

EXECUTION_PROFILES = ("internal-fast", "balanced", "strict")


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    name: str
    strict_real: bool
    prefer_host_execution: bool
    run_security_scan: bool
    default_sender_backend: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def resolve_execution_policy(profile: str, strict_real_requested: bool = False) -> ExecutionPolicy:
    normalized = (profile or "internal-fast").strip().lower()
    if normalized == "strict":
        return ExecutionPolicy(
            name="strict",
            strict_real=True,
            prefer_host_execution=False,
            run_security_scan=True,
            default_sender_backend="command",
        )
    if normalized == "balanced":
        return ExecutionPolicy(
            name="balanced",
            strict_real=bool(strict_real_requested),
            prefer_host_execution=True,
            run_security_scan=True,
            default_sender_backend="command",
        )
    return ExecutionPolicy(
        name="internal-fast",
        strict_real=bool(strict_real_requested),
        prefer_host_execution=True,
        run_security_scan=False,
        default_sender_backend="relay-only",
    )

