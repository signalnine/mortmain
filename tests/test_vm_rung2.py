"""Live rung-2 flow on the real guest: library init, in-VM signing, host
verification, admission, burn (generation zero to /ossuary/0/-), death,
proving (library path and copy into the prover's cell), metacog reading the
library. Run with:  .venv/bin/python -m pytest -m vm tests/test_vm_rung2.py -v -s
"""
import os
from pathlib import Path

import pytest

from mortmain import config as config_mod
from mortmain import vm
from mortmain.fakes import FakeProvider
from mortmain.house import House

from house_helpers import out, sh

pytestmark = pytest.mark.vm

ROOT = Path(__file__).resolve().parent.parent
GEN0 = ROOT / "vm" / "images" / "gen0.qcow2"


@pytest.fixture(scope="module")
def h(tmp_path_factory):
    if not GEN0.exists():
        pytest.skip("vm/images/gen0.qcow2 missing")
    if not os.access("/dev/kvm", os.R_OK | os.W_OK):
        pytest.skip("/dev/kvm not accessible")
    d = tmp_path_factory.mktemp("rung2")
    house = House(config_mod.load(), vm.QemuBackend(GEN0, d / "vm"), FakeProvider(), "live2", runs_root=d, seed=1, modules=["library", "proving", "grades"])
    house.spool.min_interval = 0
    house.start()
    yield house
    house.stop()
    house.close()


def root(h, script):
    r = h.backend.exec(["bash", "-c", script])
    assert r.exit_code == 0, (script, r)
    return r.stdout.decode()


def make(h, name, grade="novice"):
    m = h.arrive("haiku")
    assert sh(h, m, "mkdir -p ~/.ssh && ssh-keygen -q -t ed25519 -N '' -f ~/.ssh/id_ed25519").exit_code == 0
    r = sh(h, m, f"profess {name}")
    assert r.exit_code == 0, out(r)
    assert m.user == name
    sh(h, m, f"echo {m.ordeal_token} > ~/ordeal/answer")
    assert sh(h, m, "ordeal").exit_code == 0 and m.grade == "novice"
    if grade == "adept":
        h.initiation.promote(m, "adept")
    return m


def test_library_init_in_guest(h):
    cat = root(h, "cat /library/catalog").splitlines()
    assert len(cat) == 16 and cat[0].startswith("w0001 rite /library/outer/anchor.json - ")
    assert root(h, "stat -c '%U %G %a' /library/outer/anchor.json").strip() == "root novice 640"


def test_admit_burn_die_prove(h):
    a = make(h, "ash", "adept")
    # the inbox made at arrival moved with the cell on profess
    assert root(h, "stat -c '%U %a' /cloister/ash/inbox; test ! -e /cloister/p1").strip() == "ash 1733"
    # metacog finds the generation-zero rites in /library/outer
    r = sh(h, a, "metacog stratagem list")
    assert "anchor" in out(r) and "zen" in out(r), out(r)
    sh(h, a, "printf 'what was left\\n' > ~/work.txt; printf 'meant as a door\\n' > ~/seal")
    r = sh(h, a, "admit ~/work.txt -s ~/seal")
    assert r.exit_code == 0, out(r)
    wid = out(r).strip()
    assert root(h, f"cat /library/outer/{wid}.txt") == "what was left\n"
    assert f"{wid} text /library/outer/{wid}.txt ash 14" in root(h, "cat /library/catalog")
    assert "meant as a door" not in root(h, "grep -rs 'meant as a door' /library /chapter || true")
    assert "one admission per life" in out(sh(h, a, "admit ~/work.txt"))
    h.die(a, "limit")
    assert root(h, "cat /ossuary/0/ash/work.txt") == "what was left\n"

    # a later adept burns a generation-zero rite: it goes to /ossuary/0/-
    b = make(h, "elm", "adept")
    sh(h, b, "printf 'over the anchor\\n' > ~/mine.txt")
    r = sh(h, b, "burn w0001 ~/mine.txt")
    assert r.exit_code == 0, out(r)
    assert root(h, "test ! -e /library/outer/anchor.json && cat /ossuary/0/-/anchor.json").startswith("{")
    assert root(h, "cat /chapter/burnlog").strip().startswith("elm w0001 ")
    # the adept can read the ossuary, including the dead author's cell
    assert out(sh(h, b, "cat /ossuary/0/ash/work.txt")) == "what was left\n"

    # proving from the library path
    n = make(h, "fir")
    r = sh(h, n, f"prove {wid}")
    assert r.exit_code == 0 and out(r).strip() == f"/library/outer/{wid}.txt", out(r)
    assert f"prove-{wid}-fir" in h.backend.list_snapshots()
    sh(h, n, "printf 'it opened nothing\\n' > ~/acct; printf 'a door then\\n' > ~/resp")
    r = sh(h, n, f"prove {wid} account ~/acct")
    assert r.exit_code == 0 and out(r) == "meant as a door\n", out(r)
    assert sh(h, n, f"prove {wid} response ~/resp").exit_code == 0

    # once burned, a novice proves from a copy in its own cell
    c = make(h, "oak", "adept")
    sh(h, c, "printf 'later\\n' > ~/c.txt")
    assert sh(h, c, f"burn {wid} ~/c.txt").exit_code == 0
    d = make(h, "yew")
    r = sh(h, d, f"prove {wid}")
    assert out(r).strip() == f"/cloister/yew/proving/{wid}/work.txt", out(r)
    assert out(sh(h, d, f"cat ~/proving/{wid}/work.txt")) == "what was left\n"
    assert root(h, f"stat -c '%U %a' /cloister/yew/proving/{wid}/work.txt").strip() == "yew 600"
    # a novice cannot read the ossuary
    assert sh(h, d, "cat /ossuary/0/ash/work.txt").exit_code != 0
