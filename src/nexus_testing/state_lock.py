"""Cross-process file-based lock for shared state files.

threading.RLock only prevents concurrent access within a single process.
When multiple CLI invocations (nexus_stage_executor.py, nexus_dispatch_runner.py)
run concurrently, they each have their own RLock instance and can stomp on the
same JSON state files simultaneously.

This module provides StateLock — a context manager backed by a .lock file —
that works across OS processes using platform-appropriate advisory locks:
  - Windows: msvcrt.locking (byte-range lock on the lock file)
  - POSIX:   fcntl.flock (exclusive advisory lock on the lock file)

Usage::

    from nexus_testing.state_lock import StateLock

    with StateLock(report_dir / "stage-transition-log.json"):
        data = load_json(...)
        data.append(entry)
        save_json(...)

The lock file path is derived from the guarded file by appending ".lock".
The lock file is created on first use and left in place between sessions
(it holds no meaningful content — only the OS lock).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import TracebackType


class StateLock:
    """Advisory cross-process exclusive lock tied to a .lock file.

    Args:
        guarded_path: The file whose access you want to serialise.  The lock
            file will be ``guarded_path`` with ``.lock`` appended.
        timeout_seconds: Not used for blocking acquisition; present for future
            compatibility.  The current implementation blocks indefinitely.
    """

    def __init__(self, guarded_path: Path, *, timeout_seconds: float = 30.0) -> None:
        self._lock_path = Path(str(guarded_path) + ".lock")
        self._timeout = timeout_seconds
        self._lock_file = None

    def acquire(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file = open(self._lock_path, "a+b")  # noqa: SIM115
        if sys.platform == "win32":
            self._acquire_windows()
        else:
            self._acquire_posix()

    def release(self) -> None:
        if self._lock_file is None:
            return
        if sys.platform == "win32":
            self._release_windows()
        else:
            self._release_posix()
        try:
            self._lock_file.close()
        except OSError:
            pass
        self._lock_file = None

    # ------------------------------------------------------------------
    # Windows: msvcrt byte-range lock
    # ------------------------------------------------------------------

    def _acquire_windows(self) -> None:
        import msvcrt
        import time

        deadline = time.monotonic() + self._timeout
        while True:
            try:
                self._lock_file.seek(0)
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire lock on {self._lock_path} within {self._timeout}s"
                    )
                time.sleep(0.05)

    def _release_windows(self) -> None:
        import msvcrt

        try:
            self._lock_file.seek(0)
            msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # POSIX: fcntl.flock (blocking exclusive)
    # ------------------------------------------------------------------

    def _acquire_posix(self) -> None:
        import fcntl

        fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX)

    def _release_posix(self) -> None:
        import fcntl

        try:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "StateLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: "TracebackType | None",
    ) -> None:
        self.release()
