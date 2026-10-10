import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

from mortmain import config as config_mod
from mortmain.fakes import FakeBackend, FakeProvider
from mortmain.house import House

# Modules a bare test house gets; vessel/council/catechism/tripwire tests install their own.
BASE_MODULES = ["library", "proving", "grades"]

PUB = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOjv5GIgbr9u3nlNmn9xMQqhVbWyyNgtZMfwEzB4gN5A p1@house"


@pytest.fixture
def make_house(tmp_path):
    made = []

    def _make(script=None, shell=None, overrides=None, default=None, lineage="test", modules=None):
        cfg = config_mod.load()
        if overrides:
            cfg = cfg.with_overrides(overrides)
        h = House(cfg, FakeBackend(shell=shell), FakeProvider(script, default=default), lineage,
                  runs_root=tmp_path, seed=1, modules=BASE_MODULES if modules is None else modules)
        h.spool.min_interval = 0
        made.append(h)
        return h

    yield _make
    for h in made:
        h.close()
