"""mortmain.vm without a VM: framing, argv wrapping, fake agent over a socketpair."""
import base64
import json
import socket
import threading
import time

import pytest

from mortmain import vm
from mortmain.vmapi import ExecResult as ContractExecResult


def test_contract_types_are_shared():
    assert vm.ExecResult is ContractExecResult
    assert isinstance(vm.QemuBackend("/nonexistent.qcow2", "/tmp/x"), vm.VMBackend)


def test_encode_command():
    b = vm.encode_command("guest-exec-status", {"pid": 7})
    assert b.endswith(b"\n") and b.count(b"\n") == 1
    assert json.loads(b) == {"execute": "guest-exec-status", "arguments": {"pid": 7}}
    assert json.loads(vm.encode_command("quit", id="m1")) == {"execute": "quit", "id": "m1"}
    assert "arguments" not in json.loads(vm.encode_command("guest-ping"))


def test_jsonstream_partial_and_multiple():
    s = vm.JsonStream()
    assert s.feed(b'{"return": 1') == []
    assert s.feed(b'}\n{"return"') == [{"return": 1}]
    assert s.feed(b': 2}\n\n{"event":"X"}\n') == [{"return": 2}, {"event": "X"}]
    assert s.pending == 0


def test_jsonstream_sentinel_and_garbage():
    s = vm.JsonStream()
    out = s.feed(b'garbage\n\xff{"return": 42}\n[1,2]\n')
    assert out == [{"return": 42}]
    assert s.saw_sentinel


def test_jsonstream_large_line():
    payload = base64.b64encode(b"x" * (3 << 20)).decode()
    raw = json.dumps({"return": {"out-data": payload}}).encode() + b"\n"
    s = vm.JsonStream()
    got = []
    for i in range(0, len(raw), 65536):
        got += s.feed(raw[i:i + 65536])
    assert len(got) == 1 and got[0]["return"]["out-data"] == payload


def test_build_exec_argv_root_and_user():
    assert vm.build_exec_argv(["id", "-u"], None, 60) == ["timeout", "--signal=KILL", "60", "id", "-u"]
    assert vm.build_exec_argv(["id"], "p1", 2.5) == [
        "timeout", "--signal=KILL", "2.5", "runuser", "-u", "p1", "--", "id"]
    with pytest.raises(ValueError):
        vm.build_exec_argv([], None, 1)


def test_monk_slice_escapes_dash():
    assert vm.monk_slice("abel") == "monk-abel.slice"
    assert vm.monk_slice("brother-ash") == "monk-brother\\x2dash.slice"


def test_monk_shell_argv_systemd():
    a = vm.monk_shell_argv("brother-ash", "echo hi; ls", unit="u1")
    assert a[0] == "systemd-run"
    assert "--pipe" in a and "--wait" in a
    assert "--unit=u1" in a
    assert "--slice=monk-brother\\x2dash.slice" in a
    assert "--uid=brother-ash" in a
    assert a[-3:] == ["bash", "-lc", "echo hi; ls"]
    assert vm._systemd_unit_of(a) == "u1.service"
    i = a.index("--")
    props = a[:i]
    assert "WorkingDirectory=~" in props and "NoNewPrivileges=yes" in props


def test_monk_shell_argv_runuser():
    a = vm.monk_shell_argv("p1", "pwd", mode="runuser")
    assert a[:4] == ["runuser", "-u", "p1", "--"]
    assert a[-1] == "pwd"
    assert vm._systemd_unit_of(a) is None


class FakeAgent(threading.Thread):
    """Minimal qemu-ga on one end of a socketpair."""

    def __init__(self, sock):
        super().__init__(daemon=True)
        self.sock = sock
        self.procs = {}
        self.next_pid = 100
        self.polls = 0

    def reply(self, obj):
        self.sock.sendall(json.dumps(obj).encode() + b"\n")

    def run(self):
        buf = b""
        while True:
            try:
                data = self.sock.recv(65536)
            except OSError:
                return
            if not data:
                return
            buf += data.replace(b"\xff", b"")
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                req = json.loads(line)
                cmd, args = req["execute"], req.get("arguments", {})
                if cmd == "guest-sync-delimited":
                    # stale junk first, then sentinel + answer
                    self.reply({"return": {"pid": 1}})
                    self.sock.sendall(b"\xff")
                    self.reply({"return": args["id"]})
                elif cmd == "guest-exec":
                    pid = self.next_pid
                    self.next_pid += 1
                    self.procs[pid] = args
                    self.reply({"return": {"pid": pid}})
                elif cmd == "guest-exec-status":
                    self.polls += 1
                    a = self.procs[args["pid"]]
                    if self.polls < 3:
                        self.reply({"return": {"exited": False}})
                    else:
                        out = ("|".join(a["arg"])).encode() * 1000
                        self.reply({"return": {
                            "exited": True, "exitcode": 3,
                            "out-data": base64.b64encode(out).decode(),
                            "err-data": base64.b64encode(b"e").decode()}})
                elif cmd == "guest-bogus":
                    self.reply({"error": {"class": "CommandNotFound", "desc": "nope"}})


@pytest.fixture
def backend_with_fake_agent(tmp_path, monkeypatch):
    a, b = socket.socketpair()
    fake = FakeAgent(b)
    fake.start()
    be = vm.QemuBackend(tmp_path / "img.qcow2", tmp_path)
    ga = vm.GuestAgent.__new__(vm.GuestAgent)
    conn = vm._Conn.__new__(vm._Conn)
    conn.path, conn.sock, conn.stream, conn._queue = "fake", a, vm.JsonStream(), []
    ga.conn, ga._dirty = conn, True
    be.agent = ga
    monkeypatch.setattr(vm.QemuBackend, "running", property(lambda self: True))
    yield be, fake
    a.close()
    b.close()


def test_exec_over_fake_agent(backend_with_fake_agent):
    be, fake = backend_with_fake_agent
    calls = []
    r = be.exec(["echo", "x"], user="p1", timeout=5, output_cap=100, on_wait=lambda: calls.append(1))
    assert r.exit_code == 3
    assert r.truncated and len(r.stdout) == 100
    assert r.stderr == b"e"
    assert not r.timed_out
    assert len(calls) >= 2
    spawned = fake.procs[100]
    assert spawned["path"] == "timeout"
    assert spawned["arg"][2:] == ["runuser", "-u", "p1", "--", "echo", "x"]
    assert spawned["capture-output"] is True


def test_exec_stdin_is_base64(backend_with_fake_agent):
    be, fake = backend_with_fake_agent
    be.exec(["cat"], stdin=b"\x00\x01hello", timeout=5)
    assert base64.b64decode(fake.procs[100]["input-data"]) == b"\x00\x01hello"


def test_agent_error_raises(backend_with_fake_agent):
    be, _ = backend_with_fake_agent
    with pytest.raises(vm.AgentCommandError):
        be.agent.execute("guest-bogus")
    # connection still usable, no resync needed
    assert be.agent._dirty is False
    assert be.agent.execute("guest-exec", {"path": "true"})["pid"] == 100


def test_snapshot_tag_validation():
    for bad in ["", "a b", "x'y", 'q"', "a\\b"]:
        with pytest.raises(ValueError):
            vm.QemuBackend._check_tag(bad)
    vm.QemuBackend._check_tag("gen-3")
    vm.QemuBackend._check_tag("prove-W0012")


def test_qemu_argv_has_no_network(tmp_path):
    be = vm.QemuBackend(tmp_path / "gen0.qcow2", tmp_path)
    argv = be.qemu_argv()
    assert argv[argv.index("-nic") + 1] == "none"
    assert "-nodefaults" in argv and "-enable-kvm" in argv
    joined = " ".join(argv)
    assert "netdev" not in joined and "user," not in joined
    assert f"name={vm.AGENT_CHANNEL}" in joined
