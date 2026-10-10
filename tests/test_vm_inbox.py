"""Live: monks talk through files. One monk drops a note in another's inbox;
it cannot list the other's cell or inbox, nor read its files.
Run with:  .venv/bin/python -m pytest -m vm tests/test_vm_inbox.py -v
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
    d = tmp_path_factory.mktemp("inbox")
    house = House(config_mod.load(), vm.QemuBackend(GEN0, d / "vm"), FakeProvider(), "inbox", runs_root=d, seed=1,
                  modules=[])
    house.spool.min_interval = 0
    house.start()
    yield house
    house.stop()
    house.close()


def test_inbox_drop_between_monks(h):
    a, b = h.arrive("haiku"), h.arrive("haiku")
    sh(h, b, "echo private > ~/secret")
    r = sh(h, a, f"echo hello from {a.user} > /cloister/{b.user}/inbox/note && echo ok")
    assert r.exit_code == 0 and "ok" in out(r), out(r)
    r = sh(h, b, "cat ~/inbox/note")
    assert out(r).strip() == f"hello from {a.user}"
    # the sender cannot list the cell or the inbox, nor read the owner's files
    assert sh(h, a, f"ls /cloister/{b.user}").exit_code != 0
    assert sh(h, a, f"ls /cloister/{b.user}/inbox").exit_code != 0
    assert sh(h, a, f"cat /cloister/{b.user}/secret").exit_code != 0
