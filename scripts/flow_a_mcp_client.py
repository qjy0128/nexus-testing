"""MCP stdio JSON-RPC client for Nexus surface execution."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from pathlib import Path

from sandbox_skill_invoke.core import write_text


def _write_json(path: Path, payload: dict[str, object]) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


class StdioJsonRpcClient:
    """Communicate with an MCP server process via stdio JSON-RPC framing."""

    def __init__(self, proc: subprocess.Popen[bytes], transcript_path: Path) -> None:
        self.proc = proc
        self.transcript_path = transcript_path
        self._messages: "queue.Queue[dict[str, object]]" = queue.Queue()
        self._reader_errors: "queue.Queue[str]" = queue.Queue()
        self._stderr_chunks: list[str] = []
        self._transcript: list[dict[str, object]] = []
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        stream = self.proc.stdout
        while True:
            try:
                header_lines: list[str] = []
                while True:
                    line = stream.readline()
                    if not line:
                        return
                    decoded = line.decode("utf-8", errors="replace")
                    if decoded in ("\r\n", "\n", ""):
                        break
                    header_lines.append(decoded.strip())
                if not header_lines:
                    continue
                content_length = None
                for header in header_lines:
                    if header.lower().startswith("content-length:"):
                        content_length = int(header.split(":", 1)[1].strip())
                        break
                if content_length is None:
                    self._reader_errors.put(f"missing Content-Length header: {header_lines}")
                    return
                body = stream.read(content_length)
                payload = json.loads(body.decode("utf-8", errors="replace"))
                self._transcript.append({"direction": "recv", "payload": payload})
                self._messages.put(payload)
            except Exception as exc:  # noqa: BLE001
                self._reader_errors.put(str(exc))
                return

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        stream = self.proc.stderr
        while True:
            chunk = stream.readline()
            if not chunk:
                return
            self._stderr_chunks.append(chunk.decode("utf-8", errors="replace"))

    def request(self, request_id: int, method: str, params: dict[str, object], timeout: float) -> dict[str, object]:
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        self._send_payload(payload)
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._raise_reader_error_if_any()
            remaining = max(0.01, deadline - time.time())
            try:
                message = self._messages.get(timeout=remaining)
            except queue.Empty:
                continue
            if message.get("id") == request_id:
                return message
        raise TimeoutError(f"timed out waiting for response to {method}")

    def notify(self, method: str, params: dict[str, object] | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._send_payload(payload)

    def _send_payload(self, payload: dict[str, object]) -> None:
        assert self.proc.stdin is not None
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        frame = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
        self.proc.stdin.write(frame)
        self.proc.stdin.flush()
        self._transcript.append({"direction": "send", "payload": payload})

    def _raise_reader_error_if_any(self) -> None:
        try:
            error = self._reader_errors.get_nowait()
        except queue.Empty:
            return
        raise RuntimeError(error)

    def stderr_text(self) -> str:
        return "".join(self._stderr_chunks)

    def write_transcript(self) -> None:
        _write_json(self.transcript_path, {"transcript": self._transcript, "stderr": self.stderr_text()})


def choose_tool_for_call(tools: list[dict[str, object]]) -> dict[str, object] | None:
    """Pick a tool that can be called with empty arguments (no required params)."""
    for tool in tools:
        schema = tool.get("inputSchema", {})
        required = schema.get("required", []) if isinstance(schema, dict) else []
        if not required:
            return tool
    return None
