#!/usr/bin/env python3
"""Behavior smoke tests for sandbox-exec container backend."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from test_helpers import (
    assert_contains,
    assert_equal,
    create_session,
    find_runnable_bash as _find_runnable_bash,
    make_temp_root,
    parse_kv_output,
    read_text,
    write_text,
)

ROOT = Path(__file__).resolve().parents[1]
EXEC_SCRIPT = ROOT / "scripts" / "sandbox-exec.sh"


def find_runnable_bash() -> str:
    result = _find_runnable_bash()
    if result is None:
        raise RuntimeError("No runnable bash found for sandbox-exec smoke test")
    return result


def build_mock_docker(bin_dir: Path, capture_file: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    driver = bin_dir / "mock_docker_driver.py"
    write_text(
        driver,
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "",
                "import json",
                "import os",
                "import shutil",
                "import subprocess",
                "import sys",
                "from pathlib import Path",
                "",
                "CAPTURE_FILE = Path(os.environ.get('MOCK_DOCKER_CAPTURE', '')) if os.environ.get('MOCK_DOCKER_CAPTURE') else None",
                "",
                "def find_bash() -> str:",
                "    configured = os.environ.get('MOCK_DOCKER_BASH', '').strip()",
                "    if configured:",
                "        return configured",
                "    primary = shutil.which('bash')",
                "    if primary:",
                "        return primary",
                "    raise RuntimeError('bash not found for mock docker driver')",
                "",
                "def capture(payload: dict[str, object]) -> None:",
                "    if CAPTURE_FILE is None:",
                "        return",
                "    CAPTURE_FILE.parent.mkdir(parents=True, exist_ok=True)",
                "    CAPTURE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')",
                "",
                "args = sys.argv[1:]",
                "if not args:",
                "    raise SystemExit(1)",
                "if args[0] in {'version', '--version'}:",
                "    print('Docker version 25.0.0, build mock')",
                "    raise SystemExit(0)",
                "if args[0] != 'run':",
                "    raise SystemExit(1)",
                "",
                "network = 'default'",
                "workdir = ''",
                "volume = ''",
                "env_pairs: dict[str, str] = {}",
                "image = ''",
                "command = []",
                "index = 1",
                "while index < len(args):",
                "    item = args[index]",
                "    if item == '--rm':",
                "        index += 1",
                "        continue",
                "    if item in {'--name', '--workdir', '--network', '--volume', '-v'}:",
                "        value = args[index + 1]",
                "        if item == '--workdir':",
                "            workdir = value",
                "        elif item in {'--volume', '-v'}:",
                "            volume = value",
                "        elif item == '--network':",
                "            network = value",
                "        index += 2",
                "        continue",
                "    if item == '-e':",
                "        raw = args[index + 1]",
                "        key, _, value = raw.partition('=')",
                "        env_pairs[key] = value",
                "        index += 2",
                "        continue",
                "    if item.startswith('-'):",
                "        index += 1",
                "        continue",
                "    image = item",
                "    command = args[index + 1:]",
                "    break",
                "",
                "source, _, target = volume.rpartition(':')",
                "if not source or not target:",
                "    raise RuntimeError(f'invalid volume spec: {volume}')",
                "capture({",
                "    'network': network,",
                "    'workdir': workdir,",
                "    'volume': volume,",
                "    'image': image,",
                "    'command': command,",
                "    'env': env_pairs,",
                "})",
                "env = os.environ.copy()",
                "env.update(env_pairs)",
                "cwd = Path(source)",
                "if command[:2] == ['bash', '-lc'] and len(command) >= 3:",
                "    proc = subprocess.run([find_bash(), '-lc', command[2]], cwd=str(cwd), env=env)",
                "else:",
                "    proc = subprocess.run(command, cwd=str(cwd), env=env)",
                "raise SystemExit(proc.returncode)",
            ]
        ),
    )
    wrapper = bin_dir / "docker"
    write_text(
        wrapper,
        "#!/usr/bin/env bash\n"
        f"\"{sys.executable}\" \"{driver}\" \"$@\"\n",
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    if os.name == "nt":
        wrapper_cmd = bin_dir / "docker.cmd"
        write_text(
            wrapper_cmd,
            "@echo off\r\n"
            f"\"{sys.executable}\" \"{driver}\" %*\r\n",
        )
    capture_file.write_text("{}\n", encoding="utf-8")
    return wrapper


def run_process(args: list[str], env: dict[str, str], bash: str) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    proc = subprocess.run(
        [bash, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return proc, parse_kv_output(proc.stdout)


def main() -> int:
    # Platform check: skip if Docker/container backend unavailable on this platform (e.g., Windows)
    # without real Docker containers)
    if os.name == "nt":
        print("Skip: container tests: Docker/container backend unavailable on Windows")
        return 0

    bash = find_runnable_bash()
    temp_root = make_temp_root("nexus-sandbox-exec-")
    try:
        sandbox_root = temp_root / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        capture_file = temp_root / "mock-docker-capture.json"
        mock_bin = temp_root / "mock-bin"
        build_mock_docker(mock_bin, capture_file)

        env = os.environ.copy()
        env["PATH"] = str(mock_bin) + os.pathsep + env.get("PATH", "")
        env["MOCK_DOCKER_CAPTURE"] = str(capture_file)
        env["MOCK_DOCKER_BASH"] = bash

        host_no_ack_proc, _ = run_process(
            [
                str(EXEC_SCRIPT),
                "--session-id",
                "missing-session",
                "--command",
                "echo hi",
                "--backend",
                "host-logged",
                "--sandbox-root",
                str(sandbox_root),
            ],
            env,
            bash,
        )
        assert_equal(host_no_ack_proc.returncode, 1, "host no ack return code")
        assert_contains(
            host_no_ack_proc.stderr,
            "host-logged backend requires --ack-unsafe-exec",
            "host no ack stderr",
        )

        probe_proc, probe = run_process(
            [
                str(EXEC_SCRIPT),
                "--probe",
                "container",
                "--backend",
                "container",
            ],
            env,
            bash,
        )
        assert_equal(probe_proc.returncode, 0, "container probe return code")
        assert_equal(probe.get("PROBE_RESULT"), "available", "container probe result")
        assert_equal(probe.get("RUNTIME"), "docker", "container probe runtime")

        create_session(sandbox_root, "exec-container-default")
        default_proc, default_result = run_process(
            [
                str(EXEC_SCRIPT),
                "--session-id",
                "exec-container-default",
                "--command",
                "printf 'container-ok' > outputs/container.txt",
                "--backend",
                "container",
                "--container-image",
                "mock/runtime:latest",
                "--sandbox-root",
                str(sandbox_root),
            ],
            env,
            bash,
        )
        assert_equal(default_proc.returncode, 0, "container default return code")
        assert_equal(default_result.get("BACKEND"), "container", "container default backend")
        assert_equal(default_result.get("ISOLATION_LEVEL"), "container", "container isolation level")
        assert_equal(default_result.get("CONTAINER_RUNTIME"), "docker", "container runtime")
        assert_equal(default_result.get("CONTAINER_IMAGE"), "mock/runtime:latest", "container image")
        assert_equal(default_result.get("NETWORK_ACCESS"), "disabled", "container network")
        assert_equal(default_result.get("UNSAFE_EXEC_ACKNOWLEDGED"), "false", "container ack flag")
        assert_equal(
            read_text(sandbox_root / "exec-container-default" / "workspace" / "outputs" / "container.txt"),
            "container-ok",
            "container output file",
        )
        capture_default = json.loads(read_text(capture_file))
        assert_equal(capture_default.get("network"), "none", "container runtime network flag")
        assert_equal(capture_default.get("image"), "mock/runtime:latest", "container runtime image")

        exit_codes_default = json.loads(
            read_text(sandbox_root / "exec-container-default" / "logs" / "exit-codes.json")
        )
        assert_equal(exit_codes_default[0].get("backend"), "container", "audit backend")
        assert_equal(exit_codes_default[0].get("networkAccess"), "disabled", "audit network access")

        create_session(sandbox_root, "exec-container-network")
        network_proc, network_result = run_process(
            [
                str(EXEC_SCRIPT),
                "--session-id",
                "exec-container-network",
                "--command",
                "printf 'network-ok' > outputs/network.txt",
                "--backend",
                "container",
                "--container-image",
                "mock/runtime:latest",
                "--allow-network",
                "--sandbox-root",
                str(sandbox_root),
            ],
            env,
            bash,
        )
        assert_equal(network_proc.returncode, 0, "container allow network return code")
        assert_equal(network_result.get("NETWORK_ACCESS"), "enabled", "container allow network output")
        capture_network = json.loads(read_text(capture_file))
        assert_equal(capture_network.get("network"), "default", "container allow network runtime flag")

        summary = {
            "probe_runtime": probe.get("RUNTIME"),
            "default_backend": default_result.get("BACKEND"),
            "default_network_access": default_result.get("NETWORK_ACCESS"),
            "default_container_runtime": default_result.get("CONTAINER_RUNTIME"),
            "allow_network_access": network_result.get("NETWORK_ACCESS"),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
