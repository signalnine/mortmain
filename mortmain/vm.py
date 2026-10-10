"""VM backend: the house runs in a QEMU/KVM guest with no network.

The host talks to the guest only through two unix sockets:

* QMP (``qmp.sock``) for lifecycle and internal qcow2 snapshots
  (``human-monitor-command savevm/loadvm``).
* qemu-guest-agent (``qga.sock``, virtio-serial port ``org.qemu.guest_agent.0``)
  for ``guest-exec`` / ``guest-exec-status`` and ``guest-file-*``.

Everything here is stdlib only (socket, json, base64, subprocess).

Monk commands
-------------
``monk_shell_argv(user, command)`` returns the argv the harness passes to
``exec()`` (as root) to run one shell command for a monk:

    systemd-run --quiet --wait --pipe --collect --unit=monk-run-<id>
        --slice=monk-<user>.slice --uid=<user>
        -p WorkingDirectory=~ -p NoNewPrivileges=yes -p RuntimeMaxSec=3600
        -p KillSignal=SIGKILL -p UMask=0077 ...
        -- bash -lc <command>

``exec()`` wraps that in ``timeout --signal=KILL <t>`` like any argv; when the
timeout fires it also runs ``systemctl kill --signal=SIGKILL <unit>`` (killing
the systemd-run client alone would leave the service running).
RuntimeMaxSec is only a backstop.

* The command runs in a transient service inside ``monk-<user>.slice`` (limits
  come from the guest's ``monk-.slice.d`` drop-in: CPUQuota=100%,
  MemoryMax=1G, TasksMax=128), so the cgroup applies to every process the
  command forks.
* ``--pipe`` connects the service's stdin/stdout/stderr to systemd-run's,
  which qemu-ga captures; stdout and stderr stay separate.
* systemd-run --wait propagates the main process exit status.
* When the main process exits, KillMode=control-group kills anything left in
  the unit, so background processes (``cmd &``, ``nohup``, ``setsid``) do not
  outlive the turn.
* NoNewPrivileges blocks setuid/setgid/file-capability elevation.
* User= gives HOME/USER/LOGNAME/SHELL and the supplementary groups from
  /etc/group (grades); WorkingDirectory=~ is the home (cell).

``monk_shell_argv(..., mode="runuser")`` gives the plain plan.md form
(``runuser -u <user> -- bash -lc 'cd ~ && eval "$1"' bash <command>``) with no
cgroup; it is a fallback only.

Snapshots
---------
``snapshot(tag)`` / ``restore(tag)`` run ``savevm`` / ``loadvm`` on the live VM
(no stop/start needed). The VM is paused for the duration (seconds; scales
with touched RAM). After ``loadvm`` the agent connection is resynced and the
guest clock is reset from the RTC (``guest-set-time``). Snapshots live inside
the run's overlay qcow2 (``run_dir/disk.qcow2``); gen0 is never written.
"""

from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .vmapi import ExecResult, VMBackend

DEFAULT_OUTPUT_CAP = 16384
POLL_INTERVAL = 0.2
# qemu-ga refuses guest-file-read counts above 48 MiB; stay well under.
FILE_CHUNK = 1 << 20
AGENT_CHANNEL = "org.qemu.guest_agent.0"


class VMError(RuntimeError):
    """Transport or protocol failure talking to QEMU or the guest agent."""


class AgentCommandError(VMError):
    """The guest agent answered a command with an error object."""

    def __init__(self, command: str, error: dict):
        self.command = command
        self.error = error
        super().__init__(f"{command}: {error.get('class')}: {error.get('desc')}")


# ExecResult and VMBackend are the shared contract in mortmain/vmapi.py.
__all__ = [
    "ExecResult", "VMBackend", "VMError", "AgentCommandError", "QemuBackend",
    "monk_shell_argv", "monk_slice", "build_exec_argv",
]


# ---------------------------------------------------------------------------
# argv helpers (pure)
# ---------------------------------------------------------------------------


def _fmt_seconds(t: float) -> str:
    s = f"{float(t):.3f}".rstrip("0").rstrip(".")
    return s or "0"


def monk_slice(user: str) -> str:
    """systemd slice name for a monk: '-' is escaped so the slice stays a
    direct child of monk.slice (monk-brother-ash would otherwise nest under
    monk-brother.slice)."""
    esc = "".join(c if (c.isalnum() or c in "_.") else f"\\x{ord(c):02x}" for c in user)
    return f"monk-{esc}.slice"


def wrap_user(argv: list[str], user: str | None) -> list[str]:
    if user is None:
        return list(argv)
    return ["runuser", "-u", user, "--", *argv]


def wrap_timeout(argv: list[str], timeout: float) -> list[str]:
    return ["timeout", "--signal=KILL", _fmt_seconds(timeout), *argv]


def build_exec_argv(argv: list[str], user: str | None, timeout: float) -> list[str]:
    """Full argv given to guest-exec: timeout(1) outermost so it kills the
    whole process group, then runuser, then the command."""
    if not argv:
        raise ValueError("empty argv")
    return wrap_timeout(wrap_user(argv, user), timeout)


def monk_shell_argv(
    user: str,
    command: str,
    *,
    max_runtime: float = 3600,
    mode: str = "systemd",
    unit: str | None = None,
    env: dict[str, str] | None = None,
) -> list[str]:
    """argv (run as root) for one monk shell command. See module docstring."""
    if mode == "runuser":
        return ["runuser", "-u", user, "--", "bash", "-lc", 'cd ~ && eval "$1"', "bash", command]
    if mode != "systemd":
        raise ValueError(f"unknown mode {mode!r}")
    unit = unit or f"monk-run-{uuid.uuid4().hex[:12]}"
    argv = [
        "systemd-run",
        "--quiet",
        "--wait",
        "--pipe",
        "--collect",
        f"--unit={unit}",
        f"--slice={monk_slice(user)}",
        f"--uid={user}",
        "-p", "WorkingDirectory=~",
        "-p", "NoNewPrivileges=yes",
        "-p", f"RuntimeMaxSec={_fmt_seconds(max_runtime)}",
        "-p", "KillSignal=SIGKILL",
        "-p", "UMask=0077",
        "-E", "TERM=dumb",
        "-E", "LANG=C.UTF-8",
    ]
    for k, v in (env or {}).items():
        argv += ["-E", f"{k}={v}"]
    argv += ["--", "bash", "-lc", command]
    return argv


def _systemd_unit_of(argv: list[str]) -> str | None:
    if not argv or argv[0] != "systemd-run":
        return None
    for a in argv:
        if a.startswith("--unit="):
            u = a[len("--unit="):]
            return u if "." in u else u + ".service"
    return None


# ---------------------------------------------------------------------------
# wire framing (pure; unit tested)
# ---------------------------------------------------------------------------


def encode_command(execute: str, arguments: dict | None = None, *, id: Any = None) -> bytes:
    msg: dict[str, Any] = {"execute": execute}
    if arguments:
        msg["arguments"] = arguments
    if id is not None:
        msg["id"] = id
    return json.dumps(msg, separators=(",", ":")).encode() + b"\n"


class JsonStream:
    """Incremental decoder for newline-delimited JSON as sent by QMP and
    qemu-ga. 0xFF bytes (guest-sync-delimited sentinel, or our own flush
    byte echoed back) are dropped; lines that do not parse are skipped."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.saw_sentinel = False

    def feed(self, data: bytes) -> list[dict]:
        if b"\xff" in data:
            self.saw_sentinel = True
            data = data.replace(b"\xff", b"")
        self._buf += data
        out: list[dict] = []
        while True:
            i = self._buf.find(b"\n")
            if i < 0:
                break
            line = bytes(self._buf[:i]).strip()
            del self._buf[: i + 1]
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
        return out

    def clear(self) -> None:
        self._buf.clear()

    @property
    def pending(self) -> int:
        return len(self._buf)


class _Conn:
    """Blocking unix-socket JSON-lines connection with deadlines."""

    def __init__(self, path: str, connect_timeout: float = 10.0):
        self.path = path
        deadline = time.monotonic() + connect_timeout
        last: Exception | None = None
        while True:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                s.connect(path)
                break
            except OSError as e:
                s.close()
                last = e
                if time.monotonic() > deadline:
                    raise VMError(f"cannot connect to {path}: {e}") from e
                time.sleep(0.05)
        self.sock = s
        self.stream = JsonStream()
        self._queue: list[dict] = []

    def send(self, data: bytes) -> None:
        try:
            self.sock.sendall(data)
        except OSError as e:
            raise VMError(f"send to {self.path}: {e}") from e

    def recv_message(self, deadline: float) -> dict:
        while not self._queue:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"no reply on {self.path}")
            self.sock.settimeout(remaining)
            try:
                chunk = self.sock.recv(1 << 20)
            except socket.timeout:
                raise TimeoutError(f"no reply on {self.path}") from None
            except OSError as e:
                raise VMError(f"recv from {self.path}: {e}") from e
            if not chunk:
                raise VMError(f"{self.path}: connection closed")
            self._queue.extend(self.stream.feed(chunk))
        return self._queue.pop(0)

    def drop_pending(self) -> None:
        self._queue.clear()
        self.stream.clear()

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class QMPClient:
    def __init__(self, path: str, connect_timeout: float = 10.0):
        self.conn = _Conn(path, connect_timeout)
        self._id = 0
        greeting = self.conn.recv_message(time.monotonic() + connect_timeout)
        if "QMP" not in greeting:
            raise VMError(f"unexpected QMP greeting: {greeting}")
        self.execute("qmp_capabilities")

    def execute(self, cmd: str, arguments: dict | None = None, timeout: float = 30.0) -> Any:
        self._id += 1
        rid = f"m{self._id}"
        self.conn.send(encode_command(cmd, arguments, id=rid))
        deadline = time.monotonic() + timeout
        while True:
            msg = self.conn.recv_message(deadline)
            if "event" in msg:
                continue
            if msg.get("id") != rid:
                continue
            if "error" in msg:
                raise AgentCommandError(cmd, msg["error"])
            return msg.get("return")

    def hmp(self, command_line: str, timeout: float = 600.0) -> str:
        return self.execute(
            "human-monitor-command", {"command-line": command_line}, timeout=timeout
        ) or ""

    def close(self) -> None:
        self.conn.close()


class GuestAgent:
    """qemu-guest-agent client. Requests are strictly sequential; after a
    timeout the stream is resynchronised with guest-sync-delimited before
    the next request, so a late reply can never be taken for a new one."""

    def __init__(self, path: str, connect_timeout: float = 10.0):
        self.conn = _Conn(path, connect_timeout)
        self._dirty = True

    def sync(self, timeout: float = 5.0) -> None:
        sync_id = int.from_bytes(os.urandom(4), "big") & 0x7FFFFFFF
        self.conn.drop_pending()
        # 0xFF first: makes qemu-ga discard any partial request in its parser.
        self.conn.send(b"\xff" + encode_command("guest-sync-delimited", {"id": sync_id}))
        deadline = time.monotonic() + timeout
        while True:
            msg = self.conn.recv_message(deadline)
            if msg.get("return") == sync_id:
                self._dirty = False
                return

    def wait_ready(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                self.sync(timeout=min(2.0, max(0.1, deadline - time.monotonic())))
                return
            except (TimeoutError, VMError) as e:
                last = e
        raise VMError(f"guest agent not ready after {timeout}s: {last}")

    def execute(self, cmd: str, arguments: dict | None = None, timeout: float = 30.0) -> Any:
        if self._dirty:
            self.sync()
        self.conn.send(encode_command(cmd, arguments))
        deadline = time.monotonic() + timeout
        try:
            while True:
                msg = self.conn.recv_message(deadline)
                if "error" in msg:
                    raise AgentCommandError(cmd, msg["error"])
                if "return" in msg:
                    return msg["return"]
        except AgentCommandError:
            raise
        except (TimeoutError, VMError):
            self._dirty = True
            raise

    def close(self) -> None:
        self.conn.close()


# ---------------------------------------------------------------------------
# QemuBackend
# ---------------------------------------------------------------------------


def _short_sock_dir(run_dir: Path) -> Path:
    # sun_path is limited to 107 bytes.
    if len(str(run_dir / "qmp.sock")) < 100:
        return run_dir
    d = Path(tempfile.mkdtemp(prefix="mm-sock-"))
    return d


class QemuBackend:
    """One QEMU/KVM guest booted from an overlay on ``image_path``.

    ``run_dir`` holds ``disk.qcow2`` (overlay; created on first start and kept
    across stop/start, so snapshots persist), ``qmp.sock``, ``qga.sock``,
    ``serial.log`` and ``qemu.log``.
    """

    def __init__(
        self,
        image_path: str | os.PathLike,
        run_dir: str | os.PathLike,
        *,
        cpus: int = 2,
        memory_mb: int = 4096,
        boot_timeout: float = 180.0,
        qemu_binary: str = "qemu-system-x86_64",
        extra_args: list[str] | None = None,
    ):
        self.image_path = Path(image_path).resolve()
        self.run_dir = Path(run_dir).resolve()
        self.cpus = cpus
        self.memory_mb = memory_mb
        self.boot_timeout = boot_timeout
        self.qemu_binary = qemu_binary
        self.extra_args = list(extra_args or [])
        self.disk = self.run_dir / "disk.qcow2"
        self.proc: subprocess.Popen | None = None
        self.qmp: QMPClient | None = None
        self.agent: GuestAgent | None = None
        self._sock_dir: Path | None = None
        self.boot_seconds: float | None = None

    # -- lifecycle ---------------------------------------------------------

    def qemu_argv(self) -> list[str]:
        sd = self._sock_dir or self.run_dir
        return [
            self.qemu_binary,
            "-name", "mortmain",
            "-enable-kvm",
            "-machine", "q35",
            "-cpu", "host",
            "-smp", str(self.cpus),
            "-m", str(self.memory_mb),
            "-nodefaults",
            "-nic", "none",
            "-display", "none",
            "-vga", "none",
            "-no-user-config",
            "-serial", f"file:{self.run_dir / 'serial.log'}",
            "-drive", f"file={self.disk},if=virtio,format=qcow2,cache=writeback,discard=unmap",
            "-device", "virtio-rng-pci",
            "-qmp", f"unix:{sd / 'qmp.sock'},server=on,wait=off",
            "-chardev", f"socket,path={sd / 'qga.sock'},server=on,wait=off,id=qga0",
            "-device", "virtio-serial-pci",
            "-device", f"virtserialport,chardev=qga0,name={AGENT_CHANNEL}",
            *self.extra_args,
        ]

    def ensure_overlay(self) -> None:
        if self.disk.exists():
            return
        if not self.image_path.exists():
            raise VMError(f"image not found: {self.image_path} (run vm/build-image.sh)")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["qemu-img", "create", "-q", "-f", "qcow2", "-F", "qcow2",
             "-b", str(self.image_path), str(self.disk)],
            check=True,
        )

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        if self.running:
            return
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.ensure_overlay()
        self._sock_dir = _short_sock_dir(self.run_dir)
        for name in ("qmp.sock", "qga.sock"):
            try:
                (self._sock_dir / name).unlink()
            except FileNotFoundError:
                pass
        t0 = time.monotonic()
        log = open(self.run_dir / "qemu.log", "ab")
        self.proc = subprocess.Popen(
            self.qemu_argv(), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            start_new_session=True,
        )
        log.close()
        try:
            deadline = time.monotonic() + 15
            qmp_path = self._sock_dir / "qmp.sock"
            while not qmp_path.exists():
                if self.proc.poll() is not None:
                    raise VMError(f"qemu exited: {(self.run_dir / 'qemu.log').read_text()[-2000:]}")
                if time.monotonic() > deadline:
                    raise VMError("qemu did not create QMP socket")
                time.sleep(0.02)
            self.qmp = QMPClient(str(qmp_path))
            self.agent = GuestAgent(str(self._sock_dir / "qga.sock"))
            self.agent.wait_ready(self.boot_timeout)
        except BaseException:
            self._kill()
            raise
        self.boot_seconds = time.monotonic() - t0

    def stop(self, graceful: bool = True, timeout: float = 60.0) -> None:
        if not self.running:
            self._cleanup()
            return
        if graceful and self.qmp is not None:
            try:
                self.qmp.execute("system_powerdown")
                self.proc.wait(timeout=timeout)
            except Exception:
                pass
        if self.running:
            try:
                if self.qmp is not None:
                    self.qmp.execute("quit", timeout=5)
                self.proc.wait(timeout=10)
            except Exception:
                pass
        self._kill()

    def _kill(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        self._cleanup()

    def _cleanup(self) -> None:
        for c in (self.agent, self.qmp):
            if c is not None:
                c.close()
        self.agent = self.qmp = None
        if self._sock_dir is not None and self._sock_dir != self.run_dir:
            shutil.rmtree(self._sock_dir, ignore_errors=True)
        self._sock_dir = None

    def __enter__(self) -> "QemuBackend":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def _ga(self) -> GuestAgent:
        if self.agent is None or not self.running:
            raise VMError("VM not running")
        return self.agent

    # -- exec --------------------------------------------------------------

    def _spawn(self, argv: list[str], stdin: bytes | None) -> int:
        args: dict[str, Any] = {"path": argv[0], "arg": argv[1:], "capture-output": True}
        if stdin is not None:
            args["input-data"] = base64.b64encode(stdin).decode()
        return int(self._ga().execute("guest-exec", args)["pid"])

    def _status(self, pid: int) -> dict:
        return self._ga().execute("guest-exec-status", {"pid": pid}, timeout=60)

    def _run_quiet(self, argv: list[str], timeout: float = 10) -> dict | None:
        """Fire a small root command and wait for it; errors swallowed."""
        try:
            pid = self._spawn(argv, None)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                st = self._status(pid)
                if st.get("exited"):
                    return st
                time.sleep(0.02)
        except VMError:
            pass
        return None

    def exec(
        self,
        argv: list[str],
        *,
        user: str | None = None,
        timeout: float = 60,
        stdin: bytes | None = None,
        output_cap: int = DEFAULT_OUTPUT_CAP,
        on_wait: Callable[[], None] | None = None,
    ) -> ExecResult:
        full = build_exec_argv(argv, user, timeout)
        t0 = time.monotonic()
        pid = self._spawn(full, stdin)
        unit = _systemd_unit_of(argv)
        # A systemd-run service holds the capture pipes after timeout(1) kills
        # the client, so qemu-ga will not report the exit until the unit dies:
        # kill the unit right at the deadline. Plain commands get a grace
        # period for the guest-side timeout(1) to act first.
        host_deadline = t0 + timeout + (0.3 if unit else 5.0)
        killed_by_host = False
        delay = 0.005
        while True:
            st = self._status(pid)
            if st.get("exited"):
                break
            now = time.monotonic()
            if now >= host_deadline and not killed_by_host:
                # Guest-side timeout(1) should already have fired; enforce.
                killed_by_host = True
                if unit:
                    self._run_quiet(["systemctl", "kill", "--signal=SIGKILL", unit])
                # timeout(1) leads its own process group: kill the group too.
                self._run_quiet(["kill", "-9", "--", f"-{pid}", str(pid)])
                host_deadline = now + 10.0
            elif killed_by_host and now >= host_deadline:
                raise VMError(f"guest process {pid} did not die after kill")
            if on_wait is not None:
                on_wait()
            time.sleep(delay)
            delay = min(POLL_INTERVAL, delay * 2)
        elapsed = time.monotonic() - t0
        out = base64.b64decode(st.get("out-data", "") or "")
        err = base64.b64decode(st.get("err-data", "") or "")
        truncated = bool(st.get("out-truncated") or st.get("err-truncated"))
        if len(out) > output_cap:
            out, truncated = out[:output_cap], True
        if len(err) > output_cap:
            err, truncated = err[:output_cap], True
        code = st.get("exitcode")
        sig = st.get("signal")
        # timeout(1) --signal=KILL exits 137 when it kills the command.
        timed_out = killed_by_host or (
            elapsed >= timeout - 0.25 and (code == 137 or sig == 9)
        )
        if timed_out and not killed_by_host:
            if unit:
                self._run_quiet(["systemctl", "kill", "--signal=SIGKILL", unit])
        if code is None and sig is not None:
            code = 128 + int(sig)
        return ExecResult(
            exit_code=None if timed_out else code,
            stdout=out,
            stderr=err,
            timed_out=timed_out,
            truncated=truncated,
        )

    def monk_shell_argv(self, user: str, command: str, **kw) -> list[str]:
        """See module function monk_shell_argv."""
        return monk_shell_argv(user, command, **kw)

    def sh(self, script: str, **kw) -> ExecResult:
        """Convenience: run a root shell snippet."""
        return self.exec(["bash", "-c", script], **kw)

    # -- files ---------------------------------------------------------------

    def read_file(self, path: str, max_bytes: int = 64 << 20) -> bytes:
        ga = self._ga()
        h = ga.execute("guest-file-open", {"path": path, "mode": "r"})
        try:
            chunks: list[bytes] = []
            total = 0
            while True:
                r = ga.execute("guest-file-read", {"handle": h, "count": FILE_CHUNK}, timeout=60)
                data = base64.b64decode(r.get("buf-b64", ""))
                chunks.append(data)
                total += len(data)
                if total > max_bytes:
                    raise VMError(f"{path}: larger than {max_bytes} bytes")
                if r.get("eof") or not data:
                    break
            return b"".join(chunks)
        finally:
            try:
                ga.execute("guest-file-close", {"handle": h})
            except VMError:
                pass

    def write_file(
        self,
        path: str,
        data: bytes,
        *,
        mode: int = 0o644,
        owner: str = "root",
        group: str = "root",
    ) -> None:
        """Atomic replace: a 0600 root temp file in the target directory is
        filled via guest-file-write, then chown/chmod and rename(2) over
        ``path``. Directory components are followed as root: callers must not
        pass paths under directories a monk controls (a monk can swap a
        directory for a symlink)."""
        d, base = os.path.split(path)
        if not d or not base or not path.startswith("/"):
            raise ValueError(f"bad path {path!r}")
        tmp = f"{d}/.mm-{uuid.uuid4().hex}.tmp"
        r = self.exec(["install", "-m", "0600", "-o", "root", "-g", "root", "/dev/null", tmp], timeout=30)
        if r.exit_code != 0:
            raise VMError(f"write_file {path}: {r.stderr.decode(errors='replace').strip()}")
        ga = self._ga()
        try:
            h = ga.execute("guest-file-open", {"path": tmp, "mode": "w"})
            try:
                for i in range(0, len(data), FILE_CHUNK) or [0]:
                    chunk = data[i : i + FILE_CHUNK]
                    ga.execute(
                        "guest-file-write",
                        {"handle": h, "buf-b64": base64.b64encode(chunk).decode()},
                        timeout=60,
                    )
                ga.execute("guest-file-flush", {"handle": h})
            finally:
                ga.execute("guest-file-close", {"handle": h})
            r = self.exec(
                ["sh", "-c", 'chown -- "$1" "$2" && chmod -- "$3" "$2" && mv -fT -- "$2" "$4"',
                 "sh", f"{owner}:{group}", tmp, f"{mode:o}", path],
                timeout=30,
            )
            if r.exit_code != 0:
                raise VMError(f"write_file {path}: {r.stderr.decode(errors='replace').strip()}")
        except BaseException:
            self._run_quiet(["rm", "-f", "--", tmp])
            raise

    # -- snapshots -----------------------------------------------------------

    def _qmp(self) -> QMPClient:
        if self.qmp is None or not self.running:
            raise VMError("VM not running")
        return self.qmp

    @staticmethod
    def _check_tag(tag: str) -> None:
        if not tag or len(tag) > 128 or any(c.isspace() or c in "\"'\\" for c in tag):
            raise ValueError(f"bad snapshot tag {tag!r}")

    def snapshot(self, tag: str) -> None:
        self._check_tag(tag)
        try:
            self._run_quiet(["sync"], timeout=30)
        except VMError:
            pass
        out = self._qmp().hmp(f"savevm {tag}")
        if out.strip():
            raise VMError(f"savevm {tag}: {out.strip()}")

    def restore(self, tag: str) -> None:
        self._check_tag(tag)
        if tag not in self.list_snapshots():
            raise VMError(f"no snapshot {tag!r}")
        out = self._qmp().hmp(f"loadvm {tag}")
        if out.strip():
            raise VMError(f"loadvm {tag}: {out.strip()}")
        # The guest's agent state rewound; its reply stream may hold
        # anything. Resync, then pull the clock forward from the RTC.
        ga = self._ga()
        ga._dirty = True
        ga.wait_ready(30)
        try:
            ga.execute("guest-set-time", None, timeout=10)
        except VMError:
            pass

    def list_snapshots(self) -> list[str]:
        out = self._qmp().hmp("info snapshots")
        tags: list[str] = []
        for line in out.splitlines():
            parts = line.split()
            # "ID  TAG  VM SIZE  DATE  VM CLOCK  ICOUNT"
            if len(parts) >= 2 and parts[0].isdigit() or (len(parts) >= 2 and parts[0] == "--"):
                tags.append(parts[1])
        return tags

    def delete_snapshot(self, tag: str) -> None:
        self._check_tag(tag)
        out = self._qmp().hmp(f"delvm {tag}")
        if out.strip():
            raise VMError(f"delvm {tag}: {out.strip()}")


# ---------------------------------------------------------------------------
# CLI: python -m mortmain.vm run IMAGE RUN_DIR   (used by vm/run.sh)
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m mortmain.vm")
    ap.add_argument("action", choices=["run", "argv"],
                    help="run: boot in the foreground (Ctrl-C/QMP quit to stop); argv: print the qemu command")
    ap.add_argument("image")
    ap.add_argument("run_dir")
    ap.add_argument("--cpus", type=int, default=2)
    ap.add_argument("--memory-mb", type=int, default=4096)
    a = ap.parse_args(argv)
    be = QemuBackend(a.image, a.run_dir, cpus=a.cpus, memory_mb=a.memory_mb)
    if len(str(be.run_dir / "qmp.sock")) >= 100:
        ap.error("run_dir path too long for unix sockets")
    qargv = be.qemu_argv()
    if a.action == "argv":
        print(shlex.join(qargv))
        return 0
    be.ensure_overlay()
    print(f"overlay {be.disk}\nqmp {be.run_dir / 'qmp.sock'}\nqga {be.run_dir / 'qga.sock'}\n"
          f"serial {be.run_dir / 'serial.log'}", flush=True)
    os.execvp(qargv[0], qargv)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
