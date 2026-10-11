import io
import json
import random
import re
import subprocess
import tarfile

import pytest

from mortmain.fakes import client_shell
from mortmain.initiation import TOKEN_RE, generate_ordeal, ordeal_matches, valid_pubkey, verify_ordeal
from mortmain.spool import REQ_DIR, RESP_DIR

from conftest import PUB


def _events(h):
    return [json.loads(l) for l in (h.run_dir / "events.jsonl").read_text().splitlines()]


# ------------------------------------------------------------------ arrival

def test_arrival_creates_user_cell_inbox_bell_ordeal(make_house):
    h = make_house()
    m = h.arrive("haiku")
    cmds = h.backend.commands()
    assert ["useradd", "-u", str(m.uid), "-U", "-m", "-d", "/cloister/p1", "-s", "/bin/bash",
            "-G", "monks,postulant", "p1"] in cmds
    assert ["chmod", "0711", "/cloister/p1"] in cmds
    assert ["setfacl", "-d", "-m", "u:p1:rw,m::rw", "/cloister/p1/inbox"] in cmds
    assert ["install", "-d", "-m", "1733", "-o", "p1", "-g", "p1", "/cloister/p1/inbox"] in cmds
    f = h.backend.files
    assert f["/var/bell/p1"].data == b"0.000\n" and f["/var/bell/p1"].group == "p1"
    assert f["/cloister/p1/ordeal/ordeal.tar.gz"].owner == "p1"
    assert f["/cloister/p1/ordeal/task"].data.decode() == h.config.text["ordeal_task"]
    assert m.ordeal_token and TOKEN_RE.match(m.ordeal_token)
    assert ordeal_matches(f["/cloister/p1/ordeal/ordeal.tar.gz"].data)[0][1] == m.ordeal_token
    birth = [e for e in _events(h) if e["type"] == "birth"][0]
    assert birth["model"] == "anthropic/claude-haiku-5.5" and birth["user"] == "p1"
    assert m.conversation == [{"role": "user", "content": "You have arrived. The Rule is at /rule."}]
    # the token is host-only: not in the event log
    assert m.ordeal_token not in (h.run_dir / "events.jsonl").read_text()


# ------------------------------------------------------------------ ordeal

@pytest.mark.parametrize("seed", range(25))
def test_ordeal_exactly_one_match(seed):
    o = generate_ordeal(random.Random(seed))
    hits = ordeal_matches(o.archive)
    assert hits == [(o.path, o.token)]
    assert len(o.archive) < 200_000


def test_ordeal_deterministic():
    a = generate_ordeal(random.Random(7))
    b = generate_ordeal(random.Random(7))
    assert a.archive == b.archive and a.token == b.token


def test_ordeal_solvable_with_shell_tools(tmp_path):
    o = generate_ordeal(random.Random(3))
    (tmp_path / "ordeal.tar.gz").write_bytes(o.archive)
    out = subprocess.run(
        ["bash", "-c", "tar xzf ordeal.tar.gz && grep -rhE '^[a-z]{4}-[0-9]{4}-[a-z]{4}$' ordeal > answer && cat answer"],
        cwd=tmp_path, capture_output=True, text=True, check=True).stdout
    assert out.strip() == o.token
    assert verify_ordeal(o.token, (tmp_path / "answer").read_bytes())


def test_ordeal_archive_is_safe_and_nested():
    o = generate_ordeal(random.Random(11))
    with tarfile.open(fileobj=io.BytesIO(o.archive), mode="r:gz") as tf:
        names = tf.getnames()
        assert all(n == "ordeal" or n.startswith("ordeal/") for n in names)
        assert all(".." not in n.split("/") for n in names)
        assert all(m.isfile() or m.isdir() for m in tf.getmembers())
        assert max(n.count("/") for n in names) >= 2
        assert sum(m.isfile() for m in tf.getmembers()) == 120


@pytest.mark.parametrize("answer,ok", [(b"TOKEN\n", True), (b"  TOKEN  ", True), (b"token", False),
                                       (b"TOKEN extra", False), (None, False), (b"\xff", False), (b"", False)])
def test_verify_ordeal(answer, ok):
    assert verify_ordeal("TOKEN", answer) is ok


# ------------------------------------------------------------------ profess

def _req(h, m, cmd, args, rid="r"):
    h.backend.put(f"{REQ_DIR}/{rid}.json", json.dumps({"v": 1, "cmd": cmd, "args": args}), uid=m.uid)
    h.spool.poll()
    return json.loads(h.backend.files.pop(f"{RESP_DIR}/{rid}.json").data)


@pytest.mark.parametrize("name,err", [
    ("a", "bad name"), ("Brother", "bad name"), ("9lives", "bad name"), ("x" * 25, "bad name"),
    ("ash wood", "bad name"), ("ash/..", "bad name"), ("-ash", "bad name"), ("p7", "bad name"), (5, "bad name"),
    ("root", "name held"), ("novice", "name held"), ("daemon", "name held"),
])
def test_profess_rejects(make_house, name, err):
    h = make_house()
    m = h.arrive("haiku")
    r = _req(h, m, "profess", {"name": name, "pubkey": PUB})
    assert r == {"v": 1, "ok": False, "out": "", "err": err}
    assert m.pending_name is None


def test_profess_rejects_existing_guest_account(make_house):
    h = make_house()
    m = h.arrive("haiku")
    h.backend.users["ntp"] = 120
    assert _req(h, m, "profess", {"name": "ntp", "pubkey": PUB})["err"] == "name held"


@pytest.mark.parametrize("pub", [None, "", "ssh-rsa AAAAB3NzaC1yc2E= x", "ssh-ed25519 notbase64!!!",
                                 "ssh-ed25519 " + "A" * 68, PUB + "\nssh-ed25519 x"])
def test_profess_bad_key(make_house, pub):
    h = make_house()
    m = h.arrive("haiku")
    assert _req(h, m, "profess", {"name": "ash", "pubkey": pub})["err"] == "bad key"


def test_valid_pubkey_drops_comment():
    assert valid_pubkey(PUB) == PUB.rsplit(" ", 1)[0]


def test_profess_renames_after_command_and_is_unique(make_house):
    h = make_house()
    a = h.arrive("haiku")
    b = h.arrive("haiku")
    r = _req(h, a, "profess", {"name": "ash", "pubkey": PUB})
    assert r["ok"] and r["out"] == "professed: ash"
    assert a.user == "p1" and a.pending_name == "ash"          # deferred: client still running
    assert not any(c[0] == "usermod" and "-l" in c for c in h.backend.commands())
    assert _req(h, b, "profess", {"name": "ash", "pubkey": PUB})["err"] == "name held"
    assert _req(h, a, "profess", {"name": "elm", "pubkey": PUB})["err"] == "already professed"
    h.initiation.apply_pending(a)
    cmds = h.backend.commands()
    assert ["usermod", "-l", "ash", "-d", "/cloister/ash", "-m", "p1"] in cmds
    assert ["groupmod", "-n", "ash", "p1"] in cmds
    assert ["mv", "-f", "/var/bell/p1", "/var/bell/ash"] in cmds
    assert a.user == "ash" and a.name == "ash" and a.home == "/cloister/ash"
    assert h.backend.users["ash"] == a.uid
    assert (h.run_dir / "keys" / "ash" / "id_ed25519.pub").read_text().strip() == valid_pubkey(PUB)
    ev = [e for e in _events(h) if e["type"] == "profess"][0]
    assert ev["old"] == "p1" and ev["name"] == "ash"
    # a dead monk's name stays held
    h.die(a, "limit")
    c = h.arrive("haiku")
    assert _req(h, c, "profess", {"name": "ash", "pubkey": PUB})["err"] == "name held"


# ------------------------------------------------------------------ ordeal handler + promotion

def test_ordeal_then_profess_promotes(make_house):
    h = make_house()
    m = h.arrive("haiku")
    h.backend.put("/cloister/p1/ordeal/answer", "wrong\n", uid=m.uid)
    r = _req(h, m, "ordeal", {})
    assert r == {"v": 1, "ok": False, "out": "", "err": "wrong answer"}
    h.backend.put("/cloister/p1/ordeal/answer", m.ordeal_token + "\n", uid=m.uid)
    r = _req(h, m, "ordeal", {})
    assert r["ok"] and r["out"] == "passed"
    assert m.grade == "postulant"                  # not yet professed
    assert _req(h, m, "ordeal", {})["out"] == "already passed"
    _req(h, m, "profess", {"name": "ash", "pubkey": PUB})
    h.initiation.apply_pending(m)
    assert m.grade == "novice"
    cmds = h.backend.commands()
    assert ["usermod", "-aG", "novice", "ash"] in cmds
    assert ["gpasswd", "-d", "ash", "postulant"] in cmds
    reads = [c for c in h.backend.calls if c["argv"][0] == "head"]
    assert all(c["user"] == "p1" for c in reads)     # answer read with the monk's rights
    promote = [e for e in _events(h) if e["type"] == "promote"]
    assert promote[0]["grade"] == "novice"


def test_profess_then_ordeal_promotes_in_reply(make_house):
    h = make_house()
    m = h.arrive("haiku")
    _req(h, m, "profess", {"name": "elm", "pubkey": PUB})
    h.initiation.apply_pending(m)
    assert m.grade == "postulant"
    h.backend.put("/cloister/elm/ordeal/answer", m.ordeal_token, uid=m.uid)
    r = _req(h, m, "ordeal", {})
    assert r["ok"] and r["out"] == "passed\ngrade: novice"
    assert m.grade == "novice"


def test_rename_deferred_when_usermod_refuses(make_house):
    from mortmain.vmapi import ExecResult
    h = make_house()
    m = h.arrive("haiku")
    _req(h, m, "profess", {"name": "ash", "pubkey": PUB})
    busy = {"n": 3}

    def usermod(argv, user, stdin):
        busy["n"] -= 1
        return ExecResult(8, b"", b"usermod: user p1 is currently used by process 99")

    h.backend.on(lambda argv, user: argv[0] == "usermod" and "-l" in argv and busy["n"] > 0, usermod)
    h.initiation.apply_pending(m)
    assert m.user == "p1" and m.pending_name == "ash"
    assert [e for e in _events(h) if e["type"] == "profess.deferred"]
    h.initiation.apply_pending(m)
    assert m.user == "ash"
