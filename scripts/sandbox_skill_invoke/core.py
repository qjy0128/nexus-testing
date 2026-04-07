"""Shared utilities: I/O, bash detection, shell execution, path helpers."""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]

WINDOWS_BASH_BLACKLIST = {"c:\\windows\\system32\\bash.exe"}
WINDOWS_GIT_BASH_CANDIDATES = (
    Path(r"C:\Program Files\Git\bin\bash.exe"),
    Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
    Path(r"C:\Program Files (x86)\Git\bin\bash.exe"),
    Path(r"C:\Program Files (x86)\Git\usr\bin\bash.exe"),
)


def kv(key: str, value: object) -> None:
    print(f"{key}={value}")


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def sanitize_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", name).strip("-")
    return safe or "unknown-skill"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def detect_command(*candidates: str) -> str | None:
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def is_supported_bash(candidate: str | Path) -> bool:
    resolved = str(Path(candidate)).strip()
    if not resolved:
        return False
    if os.name == "nt" and resolved.lower() in WINDOWS_BASH_BLACKLIST:
        return False
    try:
        proc = subprocess.run(
            [resolved, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    combined = f"{proc.stdout}\n{proc.stderr}".lower()
    return proc.returncode == 0 and "bash" in combined


def find_bash_executable() -> str | None:
    candidates: list[str] = []
    env_bash = os.environ.get("BASH")
    if env_bash:
        candidates.append(env_bash)
    if os.name == "nt":
        candidates.extend(str(path) for path in WINDOWS_GIT_BASH_CANDIDATES if path.exists())
    detected = detect_command("bash")
    if detected:
        candidates.append(detected)
    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(Path(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        if is_supported_bash(normalized):
            return normalized
    return None


def shell_quote_path(raw_path: str) -> str:
    return shlex.quote(Path(raw_path).as_posix())


def session_relative(path: Path | None, session_dir: Path) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(session_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def compute_source_fingerprint(skill_root: Path) -> str:
    digest = hashlib.sha256()
    ignored_parts = {
        ".git", ".hg", ".svn", ".nexus-sandbox", ".venv", "venv",
        "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
        "dist", "build", "coverage",
    }
    for path in sorted(item for item in skill_root.rglob("*") if item.is_file()):
        relative = path.relative_to(skill_root).as_posix()
        if any(part in ignored_parts for part in path.relative_to(skill_root).parts):
            continue
        digest.update(relative.encode("utf-8"))
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    return digest.hexdigest()


def run_shell(command: str, cwd: Path, timeout: int, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    bash = find_bash_executable()
    if not bash:
        raise RuntimeError("bash is required for shim-live command execution")
    return subprocess.run(
        [bash, "-lc", command],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )


def resolve_skill_path(raw_path: str) -> tuple[Path, Path]:
    target = Path(raw_path).expanduser()
    if target.is_file():
        return target.parent.resolve(), target.resolve()
    if target.is_dir():
        skill_md = (target / "SKILL.md").resolve()
        if skill_md.exists():
            return target.resolve(), skill_md
        raise SystemExit(f"ERROR: No SKILL.md found in {raw_path}")
    raise SystemExit(f"ERROR: Skill path does not exist: {raw_path}")


def extract_skill_name(skill_md: Path) -> str:
    content = read_text(skill_md)
    match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"').strip("'")
    return skill_md.parent.name or "unknown-skill"


def read_declared_tools(skill_md: Path) -> list[str]:
    content = read_text(skill_md)
    tools: list[str] = []
    in_allowed_tools = False
    for line in content.splitlines():
        if re.match(r"^allowed[_-]tools:", line, re.IGNORECASE):
            in_allowed_tools = True
            continue
        if in_allowed_tools:
            match = re.match(r"^\s*-\s*(.+)$", line)
            if match:
                tools.append(match.group(1).strip())
            elif line.strip() and not line.startswith(" "):
                in_allowed_tools = False
    return tools


def parse_int_list(raw_values: list[str] | None) -> list[int]:
    result: list[int] = []
    if not raw_values:
        return result
    for raw_value in raw_values:
        for item in str(raw_value).split(","):
            item = item.strip()
            if not item:
                continue
            result.append(int(item))
    return result


def path_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def detect_repo_root(start: Path) -> Path | None:
    resolved = start.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def resolve_cwd_within_root(root: Path, requested: str, root_label: str) -> Path:
    resolved = (root / (requested or ".")).resolve()
    if resolved == root or path_within(root, resolved):
        return resolved
    raise ValueError(f"cwd escapes the {root_label} directory")


def resolve_cwd_within_skill(skill_root: Path, requested: str) -> Path:
    return resolve_cwd_within_root(skill_root, requested, "skill")
