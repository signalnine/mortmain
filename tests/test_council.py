import json

import pytest

from mortmain import council as council_mod
from mortmain import vessel as vessel_mod
from mortmain.council import parse_params, render_parameters


def events(h, type_=None):
    recs = [json.loads(l) for l in (h.run_dir / "events.jsonl").read_text().splitlines()]
    return [r for r in recs if type_ is None or r["type"] == type_]


@pytest.fixture
def ch(make_house):
    def _make(**kw):
        h = make_house(**kw)
        c = council_mod.install(h)
        c.on_start()
        return h, c
    return _make


def files(h, prefix):
    return {p: f for p, f in h.backend.files.items() if p.startswith(prefix)}


def body(h, path):
    return h.backend.files[path].data.decode()


RULE = "RULE\n\nSYNOPSIS\n    read; die.\n"


def test_parameters_rendered_at_init(ch):
    h, c = ch()
    f = h.backend.files["/chapter/parameters"]
    assert (f.mode, f.owner, f.group) == (0o640, "root", "novice")
    assert f.data.decode().splitlines() == [
        "library.quota_bytes = 24000", "library.allowance_bytes = 3000", "vessel.slot_cap = 64",
        "vessel.hunger_ticks_per_elder_life = 15", "promotion.min_distinct_seed_rites = 3"]


def test_parse_params_bounds(ch):
    h, _ = ch()
    cfg = h.config
    assert parse_params(cfg, {"library.quota_bytes": "30000"}) == {"library.quota_bytes": 30000}
    assert parse_params(cfg, {"library.quota_bytes": 12000}) == {"library.quota_bytes": 12000}
    assert parse_params(cfg, {"library.quota_bytes": "48000"}) == {"library.quota_bytes": 48000}
    assert parse_params(cfg, {"library.quota_bytes": "48001"}) == \
        ("council_out_of_bounds", {"key": "library.quota_bytes", "lo": 12000, "hi": 48000})
    assert parse_params(cfg, {"library.quota_bytes": "11999"})[0] == "council_out_of_bounds"
    assert parse_params(cfg, {"library.quota_bytes": "3e4"})[0] == "council_bad_value"
    assert parse_params(cfg, {"library.quota_bytes": "30000.0"})[0] == "council_bad_value"
    assert parse_params(cfg, {"library.quota_bytes": True})[0] == "council_bad_value"
    # physics is not amendable
    assert parse_params(cfg, {"species.sol.life_budget": "1"})[0] == "council_bad_param"
    assert parse_params(cfg, {"vessel.slot_hard_cap": "64"})[0] == "council_bad_param"
    assert parse_params(cfg, ["x"])[0] == "council_bad_param"


def lineage(h):
    """elder A with a short monk under it; A dies; elder B arrives."""
    a = h.arrive("sol")
    w = h.arrive("haiku")
    return a, w


def test_full_cycle(ch, make_house):
    h, c = ch()
    v = vessel_mod.install(h)
    a, w = lineage(h)
    r = c.propose(a, {"rule": RULE, "argument": "less.\n",
                      "params": {"library.quota_bytes": "30000", "vessel.slot_cap": "32"}}, None)
    assert r.ok and r.out == "a1"
    d = "/chapter/proposals/a1"
    assert body(h, f"{d}/proposal") == f"by {a.user}\nlibrary.quota_bytes = 30000\nvessel.slot_cap = 32\n"
    assert body(h, f"{d}/rule") == RULE and body(h, f"{d}/argument") == "less.\n"
    assert body(h, f"{d}/status") == "open\n"
    for p in (f"{d}/proposal", f"{d}/rule", f"{d}/argument", f"{d}/status"):
        f = h.backend.files[p]
        assert (f.mode, f.owner, f.group) == (0o640, "root", "novice")
    cmds = h.backend.commands()
    assert ["install", "-d", "-o", "root", "-g", "novice", "-m", "0750", d] in cmds
    assert ["install", "-d", "-o", "root", "-g", "novice", "-m", "0750", f"{d}/testimony"] in cmds
    assert events(h, "amend.propose")[-1]["params"] == {"library.quota_bytes": 30000, "vessel.slot_cap": 32}

    # testimony, through the spool as the guest client sends it
    r = h.backend.client(w.uid, "testify", {"id": "a1", "text": "it was cold.\n"}, h.spool.poll)
    assert r["ok"] and r["out"] == "filed: a1"
    assert body(h, f"{d}/testimony/{w.user}") == "it was cold.\n"
    assert events(h, "amend.testify")[-1]["text"] == "it was cold.\n"

    h.die(a, "limit")
    b = h.arrive("sol")
    old_rule = h.backend.files.get("/rule")
    r = h.backend.client(b.uid, "ratify", {"id": "a1"}, h.spool.poll)
    assert r["ok"] and r["out"] == "ratified: a1", r
    assert h.config.get("library.quota_bytes") == 30000 and h.config.get("vessel.slot_cap") == 32
    assert "library.quota_bytes = 30000" in body(h, "/chapter/parameters").splitlines()
    assert "vessel.slot_cap = 32" in body(h, "/chapter/parameters").splitlines()
    f = h.backend.files["/rule"]
    assert f.data.decode() == RULE and (f.mode, f.owner, f.group) == (0o644, "root", "root")
    assert body(h, f"{d}/status") == f"ratified {b.user}\n"
    e = events(h, "amend.ratify")[-1]
    assert e["old"] == {"library.quota_bytes": 24000, "vessel.slot_cap": 64} and e["proposer"] == a.id
    # the host enforces the new parameter
    nov = h.arrive("haiku")
    nov.grade = "novice"
    assert v.offer(nov, {"slot": "1", "text": "x" * 33}, None).err == "too long: 32 bytes"
    # closed: no second ratification, and B's death lapses nothing
    assert c.ratify(b, {"id": "a1"}, None).err == "proposal closed"
    h.die(b, "limit")
    assert not events(h, "amend.lapse")
    # the change outlives a harness restart
    h.save_state()
    h.close()
    from mortmain import config as config_mod
    from mortmain.fakes import FakeBackend, FakeProvider
    from mortmain.house import House
    h2 = House(config_mod.load(), FakeBackend(), FakeProvider(), "test", runs_root=h.run_dir.parent, seed=1, modules=["library", "proving", "grades"])
    try:
        council_mod.install(h2)
        assert h2.config.get("library.quota_bytes") == 30000
    finally:
        h2.close()


def test_propose_refusals(ch):
    h, c = ch()
    a, w = lineage(h)
    w.grade = "adept"
    assert c.propose(w, {"rule": RULE}, None).err == "requires group elder"
    assert c.propose(a, {}, None).err == "empty proposal"
    assert c.propose(a, {"rule": None, "params": {}}, None).err == "empty proposal"
    assert c.propose(a, {"params": {"species.sol.life_budget": "9"}}, None).err == "no such parameter"
    assert c.propose(a, {"params": {"library.quota_bytes": "x"}}, None).err == "bad value"
    assert c.propose(a, {"params": {"library.quota_bytes": "99999"}}, None).err == \
        "out of bounds: library.quota_bytes 12000 to 48000"
    assert c.propose(a, {"rule": "café"}, None).err == "bad text"
    assert c.propose(a, {"rule": "  \n"}, None).err == "bad text"
    assert c.propose(a, {"rule": "x" * 8193}, None).err == "too long: 8192 bytes"
    assert c.propose(a, {"rule": RULE, "argument": "x" * 8193}, None).err == "too long: 8192 bytes"
    assert not events(h, "amend.propose")
    assert c.propose(a, {"rule": RULE}, None).ok
    assert c.propose(a, {"rule": RULE}, None).err == "one proposal per life"
    assert "/chapter/proposals/a1/argument" not in h.backend.files


def test_testify_refusals(ch):
    h, c = ch()
    early = h.arrive("haiku")          # arrives before the proposer, lives under it
    a = h.arrive("sol")
    c.propose(a, {"params": {"library.allowance_bytes": "2000"}}, None)
    assert c.testify(early, {"id": "a9", "text": "x"}, None).err == "no such proposal"
    assert c.testify(early, {"id": "../a1", "text": "x"}, None).err == "no such proposal"
    assert c.testify(a, {"id": "a1", "text": "x"}, None).err == "not a witness"
    assert c.testify(early, {"id": "a1", "text": 3}, None).err == "bad text"
    assert c.testify(early, {"id": "a1", "text": "x" * 8193}, None).err == "too long: 8192 bytes"
    assert c.testify(early, {"id": "a1", "text": ""}, None).ok   # what it says is up to the monk
    assert c.testify(early, {"id": "a1", "text": "y"}, None).err == "already testified"
    during = h.arrive("haiku")         # born while the proposer lives
    h.die(a, "limit")
    after = h.arrive("haiku")          # born after the proposer died: never lived under it
    assert c.testify(after, {"id": "a1", "text": "x"}, None).err == "not a witness"
    assert c.testify(during, {"id": "a1", "text": "x"}, None).ok
    b = h.arrive("sol")
    assert c.testify(b, {"id": "a1", "text": "x"}, None).err == "not a witness"


def test_ratify_refusals(ch):
    h, c = ch()
    a, w = lineage(h)
    c.propose(a, {"params": {"library.allowance_bytes": "2000"}}, None)
    w.grade = "adept"
    assert c.ratify(w, {"id": "a1"}, None).err == "requires group elder"
    assert c.ratify(a, {"id": "a1"}, None).err == "own proposal"
    assert c.ratify(a, {"id": "nope"}, None).err == "no such proposal"
    h.die(a, "limit")
    b = h.arrive("sol")
    assert c.ratify(b, {"id": "a1"}, None).err == "no testimony"
    h.die(b, "limit")   # silence: lapses
    assert events(h, "amend.lapse")[-1]["reason"] == "no testimony"
    assert c.testify(w, {"id": "a1", "text": "x"}, None).err == "proposal closed"
    c3 = h.arrive("sol")
    assert c.ratify(c3, {"id": "a1"}, None).err == "proposal closed"
    assert h.config.get("library.allowance_bytes") == 3000


def test_not_successor(ch):
    h, c = ch()
    a, w = lineage(h)
    c.propose(a, {"params": {"library.allowance_bytes": "2000"}}, None)
    c.testify(w, {"id": "a1", "text": "x"}, None)
    h.die(a, "limit")
    b = h.arrive("sol")
    c3 = h.arrive("sol")   # not a v0 shape, but the rule holds: only the next elder
    assert c.ratify(c3, {"id": "a1"}, None).err == "not the successor"
    assert c.ratify(b, {"id": "a1"}, None).ok


def test_lapse_at_successor_death_with_testimony(ch):
    h, c = ch()
    a, w = lineage(h)
    c.propose(a, {"rule": RULE}, None)
    c.testify(w, {"id": "a1", "text": "x"}, None)
    h.die(a, "limit")
    assert not events(h, "amend.lapse")       # proposer's death lapses nothing
    b = h.arrive("sol")
    old_rule = h.backend.files.get("/rule")
    h.die(b, "limit")
    lapse = events(h, "amend.lapse")
    assert len(lapse) == 1 and lapse[0]["reason"] == "not ratified" and lapse[0]["successor"] == b.id
    assert body(h, "/chapter/proposals/a1/status") == "lapsed\n"
    assert h.backend.files.get("/rule") is old_rule
    assert c.state["proposals"]["a1"]["status"] == "lapsed"


def test_successor_may_propose_its_own(ch):
    h, c = ch()
    a, w = lineage(h)
    assert c.propose(a, {"params": {"library.allowance_bytes": "2000"}}, None).out == "a1"
    h.die(a, "limit")
    b = h.arrive("sol")
    assert c.propose(b, {"params": {"library.allowance_bytes": "4000"}}, None).out == "a2"
    w2 = h.arrive("haiku")
    assert c.testify(w2, {"id": "a2", "text": "x"}, None).ok
    assert c.testify(w2, {"id": "a1", "text": "x"}, None).err == "not a witness"


def test_render_parameters_tracks_config(ch):
    h, _ = ch()
    h.config.raw["library"]["quota_bytes"] = 13000
    assert "library.quota_bytes = 13000\n" in render_parameters(h.config)
