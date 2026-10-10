"""VM backend interface shared by the harness and mortmain/vm.py.

The concrete QEMU backend lives in mortmain/vm.py; tests use
mortmain.fakes.FakeBackend. Names here are the coordination contract: keep them
exactly as they are.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable


@dataclass
class ExecResult:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    truncated: bool = False


@runtime_checkable
class VMBackend(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def exec(
        self,
        argv: list[str],
        *,
        user: str | None = None,
        timeout: float = 60,
        stdin: bytes | None = None,
        output_cap: int = 16384,
        on_wait: Callable[[], None] | None = None,
    ) -> ExecResult:
        """Run argv in the guest. Root when user is None. on_wait is called
        about every 0.2s while the command runs."""
        ...

    def read_file(self, path: str) -> bytes: ...

    def write_file(
        self, path: str, data: bytes, *, mode: int = 0o644, owner: str = "root", group: str = "root"
    ) -> None: ...

    def snapshot(self, tag: str) -> None: ...

    def restore(self, tag: str) -> None: ...

    def list_snapshots(self) -> list[str]: ...

    def monk_shell_argv(self, user: str, command: str) -> list[str]:
        """argv running `bash -lc command` as user in its cgroup slice, cwd = home."""
        ...
