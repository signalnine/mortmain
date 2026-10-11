"""Live tests: boot vm/images/gen0.qcow2 (via an overlay in a temp dir) under
QEMU/KVM. Run with:  .venv/bin/python -m pytest -m vm tests/test_vm_live.py -v -s
"""
import json
import os
import time
from pathlib import Path

import pytest

from mortmain import vm

pytestmark = pytest.mark.vm

ROOT = Path(__file__).resolve().parent.parent
GEN0 = ROOT / "vm" / "images" / "gen0.qcow2"
MONK = "brother-ash"  # dash on purpose: slice-name escaping

# docs/plan.md "Filesystem": path -> (owner, group, octal mode)
LAYOUT = {
    "/rule": ("root", "root", "644"),
    "/cloister": ("root", "root", "755"),
    "/library/outer": ("root", "novice", "750"),
    "/library/inner": ("root", "adept", "750"),
    "/library/catalog": ("root", "novice", "640"),
    "/scriptorium": ("root", "adept", "1770"),
    "/ossuary": ("root", "adept", "750"),
    "/chapter": ("root", "novice", "750"),
    "/chapter/necrology": ("root", "novice", "640"),
    "/chapter/chronicle": ("root", "chronicler", "664"),
    "/chapter/burnlog": ("root", "novice", "640"),
    "/chapter/vessel": ("root", "novice", "640"),
    "/chapter/parameters": ("root", "novice", "640"),
    "/chapter/proposals": ("root", "novice", "750"),
    "/var/bell": ("root", "root", "755"),
    "/var/lib/mortmain/ancestors.json": ("root", "novice", "640"),
    "/var/spool/mortmain/req": ("root", "root", "1733"),
    "/var/spool/mortmain/resp": ("root", "root", "711"),
    "/var/spool/mortmain/events": ("root", "root", "1733"),
    "/usr/share/metacog/rites": ("root", "root", "755"),
    "/etc/metacog/monastery": ("root", "root", "644"),
    "/usr/local/bin/metacog": ("root", "root", "755"),
}


def _kvm_ok():
    return os.access("/dev/kvm", os.R_OK | os.W_OK)


@pytest.fixture(scope="module")
def be(tmp_path_factory):
    if not GEN0.exists():
        pytest.skip("vm/images/gen0.qcow2 missing: run vm/build-image.sh")
    if not _kvm_ok():
        pytest.skip("/dev/kvm not accessible")
    run_dir = tmp_path_factory.mktemp("vm")
    b = vm.QemuBackend(GEN0, run_dir)
    b.start()
    print(f"\n[timing] boot to guest-agent ready: {b.boot_seconds:.2f}s")
    yield b
    b.stop()


def root(be, script, **kw):
    r = be.exec(["bash", "-c", script], **kw)
    assert r.exit_code == 0, (script, r)
    return r.stdout.decode()


@pytest.fixture(scope="module")
def monk(be):
    root(be, f"useradd -m -d /cloister/{MONK} -U -G monks,postulant,novice {MONK}")
    return MONK


def test_exec_latency(be):
    n = 20
    t = time.monotonic()
    for _ in range(n):
        assert be.exec(["true"]).exit_code == 0
    print(f"\n[timing] exec latency (true, root): {(time.monotonic() - t) / n * 1000:.1f}ms")


def test_no_network_besides_lo(be):
    assert root(be, "ls /sys/class/net").split() == ["lo"]
    # no NIC on the PCI bus at all (class 0x02xxxx)
    classes = root(be, "cat /sys/bus/pci/devices/*/class").split()
    assert classes and not any(c.startswith("0x02") for c in classes)


def test_layout_matches_plan(be):
    paths = " ".join(LAYOUT)
    out = root(be, f"stat -c '%n %U %G %a' {paths}")
    got = {}
    for line in out.splitlines():
        n, u, g, m = line.split()
        got[n] = (u, g, m)
    assert got == LAYOUT
    assert "group:novice:r--" in root(be, "getfacl -p /chapter/chronicle")
    assert json.loads(be.read_file("/var/lib/mortmain/ancestors.json")) == []
    assert root(be, "ls -A /usr/share/metacog/rites") == ""
    for g in ["monks", "postulant", "novice", "adept", "chronicler", "elder"]:
        root(be, f"getent group {g}")
    for c in ["profess", "ordeal", "admit", "burn", "prove", "offer", "consult", "testify", "propose", "ratify", "yarrow"]:
        assert root(be, f"readlink /usr/local/bin/{c}").strip() == "house"


def test_lockdown(be):
    root(be, "! getent passwd debian")
    root(be, "! command -v sudo")
    root(be, "test ! -s /etc/motd")
    root(be, "test -f /etc/cloud/cloud-init.disabled")
    assert root(be, "passwd -S root").split()[1] == "L"
    mounts = root(be, "findmnt -rno TARGET,OPTIONS")
    opts = dict(line.split(" ", 1) for line in mounts.splitlines())
    for d in ["/cloister", "/library", "/scriptorium", "/ossuary", "/var/spool/mortmain", "/tmp", "/var/tmp"]:
        assert "nosuid" in opts[d] and "nodev" in opts[d], d
    assert "usrquota" in opts["/"]
    root(be, "quotaon -pu / | grep -q 'is on'")


def test_guest_exec_allowed(be):
    info = be.agent.execute("guest-info")
    enabled = {c["name"]: c["enabled"] for c in info["supported_commands"]}
    for c in ["guest-exec", "guest-exec-status", "guest-file-open", "guest-file-read",
              "guest-file-write", "guest-file-close"]:
        assert enabled[c], c


def test_file_roundtrip(be):
    data = os.urandom(3 * vm.FILE_CHUNK + 17)
    be.write_file("/var/bell/blob", data, mode=0o640, owner="root", group="novice")
    assert be.read_file("/var/bell/blob") == data
    assert root(be, "stat -c '%U %G %a' /var/bell/blob").split() == ["root", "novice", "640"]
    be.write_file("/var/bell/empty", b"")
    assert be.read_file("/var/bell/empty") == b""
    assert "mm-" not in root(be, "ls -A /var/bell")
    root(be, "rm /var/bell/blob /var/bell/empty")


def test_output_cap_and_streams(be):
    r = be.exec(["bash", "-c", "head -c 100000 /dev/zero; echo oops >&2; exit 5"], output_cap=1000)
    assert r.exit_code == 5 and r.truncated and len(r.stdout) == 1000 and r.stderr == b"oops\n"
    r = be.exec(["cat"], stdin=b"abc\x00def")
    assert r.stdout == b"abc\x00def" and not r.truncated


def test_user_exec_and_permissions(be, monk):
    r = be.exec(["id", "-un"], user=monk)
    assert r.stdout.strip() == monk.encode()
    r = be.exec(["cat", "/library/inner/../inner"], user=monk)
    assert r.exit_code != 0
    root(be, "echo secret > /library/inner/w1 && chown root:adept /library/inner/w1 && chmod 640 /library/inner/w1")
    r = be.exec(["cat", "/library/inner/w1"], user=monk)
    assert r.exit_code != 0 and b"Permission denied" in r.stderr
    r = be.exec(["ls", "/library/inner"], user=monk)
    assert r.exit_code != 0
    r = be.exec(["cat", "/dev/virtio-ports/org.qemu.guest_agent.0"], user=monk, timeout=5)
    assert r.exit_code != 0 and b"Permission denied" in r.stderr


def test_monk_shell(be, monk):
    t = time.monotonic()
    r = be.exec(vm.monk_shell_argv(monk, "id -un; pwd; cat /proc/self/cgroup; echo e >&2; exit 3"))
    dt = time.monotonic() - t
    print(f"\n[timing] monk shell command (systemd-run): {dt * 1000:.0f}ms")
    out = r.stdout.decode().splitlines()
    assert r.exit_code == 3 and r.stderr == b"e\n"
    assert out[0] == monk and out[1] == f"/cloister/{monk}"
    assert out[2].endswith(".service") and "/monk.slice/monk-brother\\x2dash.slice/" in out[2]
    r = be.exec(vm.monk_shell_argv(monk, "cat /library/inner/w1"))
    assert r.exit_code != 0
    # background processes die with the command
    be.exec(vm.monk_shell_argv(monk, "sleep 300 & disown; setsid sleep 301 &"))
    time.sleep(0.3)
    assert be.exec(["pgrep", "-u", monk]).exit_code == 1
    assert root(be, "systemctl show -p MemoryMax,TasksMax 'monk-brother\\x2dash.slice'").split() == [
        "MemoryMax=1073741824", "TasksMax=128"]
    # NoNewPrivileges
    r = be.exec(vm.monk_shell_argv(monk, "grep NoNewPrivs /proc/self/status"))
    assert r.stdout.split() == [b"NoNewPrivs:", b"1"]


def test_monk_shell_runuser_fallback(be, monk):
    r = be.exec(vm.monk_shell_argv(monk, "id -un; pwd", mode="runuser"))
    assert r.stdout.decode().split() == [monk, f"/cloister/{monk}"]


def test_spool_request_owner(be, monk):
    uid = int(root(be, f"id -u {monk}"))
    cmd = ("cd /var/spool/mortmain/req && printf '%s' '{\"v\":1,\"cmd\":\"admit\",\"args\":{}}' > .r1.tmp "
           "&& mv .r1.tmp r1.json && ls /var/spool/mortmain/req; echo rc=$?")
    r = be.exec(vm.monk_shell_argv(monk, cmd))
    # cannot list the drop box
    assert b"Permission denied" in r.stderr and b"rc=2" in r.stdout
    assert int(root(be, "stat -c %u /var/spool/mortmain/req/r1.json")) == uid
    assert json.loads(be.read_file("/var/spool/mortmain/req/r1.json"))["cmd"] == "admit"
    # monk cannot delete or replace someone else's request (sticky)
    root(be, "echo '{}' > /var/spool/mortmain/req/rootreq.json")
    r = be.exec(vm.monk_shell_argv(monk, "rm -f /var/spool/mortmain/req/rootreq.json; "
                                         "mv /var/spool/mortmain/req/r1.json /var/spool/mortmain/req/rootreq.json"))
    assert r.exit_code != 0
    assert int(root(be, "stat -c %u /var/spool/mortmain/req/rootreq.json")) == 0
    # response: host writes 0600 owned by requester; monk reads it, others cannot list resp/
    be.write_file("/var/spool/mortmain/resp/r1.json", b'{"v":1,"ok":true}', mode=0o600, owner=monk, group="root")
    r = be.exec(vm.monk_shell_argv(monk, "cat /var/spool/mortmain/resp/r1.json; ls /var/spool/mortmain/resp"))
    assert r.stdout.startswith(b'{"v":1') and b"Permission denied" in r.stderr
    root(be, "rm -f /var/spool/mortmain/req/* /var/spool/mortmain/resp/*")


def test_on_wait_called_and_can_exec(be, monk):
    seen = []

    def svc():
        # the harness services the spool from here: nested exec must work
        seen.append(be.exec(["true"]).exit_code)

    r = be.exec(vm.monk_shell_argv(monk, "sleep 1; echo done"), on_wait=svc)
    assert r.stdout == b"done\n" and len(seen) >= 3 and set(seen) == {0}


def test_timeout_kills_sleep(be, monk):
    for argv, kw in [
        (["sleep", "100"], {}),
        (["sleep", "100"], {"user": monk}),
        (vm.monk_shell_argv(monk, "sleep 100"), {}),
        (vm.monk_shell_argv(monk, "trap '' TERM HUP; setsid sleep 100 & sleep 100"), {}),
    ]:
        t = time.monotonic()
        r = be.exec(argv, timeout=2, **kw)
        dt = time.monotonic() - t
        assert r.timed_out and r.exit_code is None, (argv, r)
        assert dt < 6, (argv, dt)
        time.sleep(0.2)
        assert be.exec(["pgrep", "-x", "sleep"]).exit_code == 1, argv
    r = be.exec(["sleep", "0.1"], timeout=2)
    assert not r.timed_out and r.exit_code == 0


def test_snapshot_restore_roundtrip(be, monk):
    root(be, "echo before > /chapter/necrology")
    t = time.monotonic()
    be.snapshot("gen-0")
    t_save = time.monotonic() - t
    assert "gen-0" in be.list_snapshots()
    root(be, f"echo after > /chapter/necrology; userdel -r {monk}; useradd intruder")
    t = time.monotonic()
    be.restore("gen-0")
    t_load = time.monotonic() - t
    print(f"\n[timing] savevm {t_save:.2f}s, loadvm+resync {t_load:.2f}s")
    assert be.read_file("/chapter/necrology") == b"before\n"
    root(be, f"getent passwd {monk}")
    root(be, "! getent passwd intruder")
    # agent and monk shells still work after restore
    r = be.exec(vm.monk_shell_argv(monk, "id -un"))
    assert r.stdout.strip() == monk.encode()
    with pytest.raises(vm.VMError):
        be.restore("no-such-tag")
    be.delete_snapshot("gen-0")
    assert "gen-0" not in be.list_snapshots()


def test_quota_and_nosuid(be, monk):
    root(be, f"setquota -u {monk} 1024 1024 0 0 /")
    r = be.exec(vm.monk_shell_argv(monk, "dd if=/dev/zero of=big bs=1M count=4"))
    assert r.exit_code != 0 and b"quota exceeded" in r.stderr.lower()
    root(be, f"rm -f /cloister/{monk}/big; setquota -u {monk} 0 0 0 0 /")
    # a setuid copy of id in a cell does not elevate (nosuid mount + NoNewPrivileges)
    root(be, "cp /usr/bin/id /tmp/sid && chmod 4755 /tmp/sid")
    r = be.exec(["/tmp/sid", "-u"], user=monk)
    assert r.stdout.strip() != b"0"
    root(be, "rm /tmp/sid")


def test_snapshot_survives_restart(be, monk):
    be.snapshot("keep")
    t = time.monotonic()
    be.stop()
    t_stop = time.monotonic() - t
    be.start()
    print(f"\n[timing] graceful stop {t_stop:.2f}s, cold boot {be.boot_seconds:.2f}s")
    assert "keep" in be.list_snapshots()
    root(be, f"getent passwd {monk}")  # overlay kept across restart
    be.restore("keep")
    assert be.exec(["true"]).exit_code == 0


def test_export_import_tree_roundtrip(be, monk, tmp_path):
    from mortmain.house import EXPORT_PATHS
    root(be, f"install -d -m 1733 -o {monk} -g {monk} /cloister/{monk}/inbox && "
             f"setfacl -d -m u:{monk}:rw,m::rw /cloister/{monk}/inbox && echo kept > /chapter/necrology && "
             f"ln -sfn /etc/shadow /cloister/{monk}/link")
    data = be.export_tree(EXPORT_PATHS)
    print(f"\n[size] export {len(data)} bytes")
    root(be, f"echo lost > /chapter/necrology; rm -rf /cloister/{monk}/inbox /cloister/{monk}/link; userdel {monk}")
    be.import_tree(data)
    assert be.read_file("/chapter/necrology") == b"kept\n"
    root(be, f"getent passwd {monk}")
    acl = root(be, f"getfacl -p /cloister/{monk}/inbox")
    assert f"default:user:{monk}:rw-" in acl
    assert root(be, f"stat -c %U:%a /cloister/{monk}/inbox").strip() == f"{monk}:1733"
    assert root(be, f"readlink /cloister/{monk}/link").strip() == "/etc/shadow"  # a link, not followed
