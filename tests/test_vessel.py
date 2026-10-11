import json

import pytest

from mortmain import vessel as vessel_mod
from mortmain.fakes import text, tool_call
from mortmain.vessel import (allowance_api, POEM_PATH, form_survival, load_poem, metrics, normalize, original_share,
                             repetition_pairs)


def events(h, type_=None):
    recs = [json.loads(l) for l in (h.run_dir / "events.jsonl").read_text().splitlines()]
    return [r for r in recs if type_ is None or r["type"] == type_]


@pytest.fixture
def vh(make_house):
    def _make(**kw):
        h = make_house(**kw)
        v = vessel_mod.install(h)
        v.on_start()
        return h, v
    return _make


def novice(h, species="haiku"):
    m = h.arrive(species)
    m.grade = "novice"
    return m


# ------------------------------------------------------------------ poem

def test_poem_loads_36_slots():
    lines = load_poem()
    assert len(lines) == 36
    assert all(l and l == l.rstrip() for l in lines)
    assert all(len(l.encode()) <= 64 for l in lines)
    raw = [l.rstrip() for l in POEM_PATH.read_text().splitlines() if l.strip()]
    assert lines == raw


def test_vessel_file_is_36_lines(vh):
    h, v = vh()
    f = h.backend.files["/chapter/vessel"]
    assert (f.mode, f.owner, f.group) == (0o640, "root", "novice")
    body = f.data.decode()
    assert body.endswith("\n") and body.count("\n") == 36
    assert body.splitlines() == load_poem()
    assert h.state_extras["vessel"]["slots"][0]["by"] is None
    assert events(h, "vessel.init")


# --------------------------------------------------------------- metrics

def test_normalize():
    assert normalize("  The Work,  was never!  ") == "the work was never"
    assert normalize("") == "" and normalize(None) == ""


def test_pantoum_pairs_and_metrics():
    orig = load_poem()
    pairs = repetition_pairs(orig)
    assert len(pairs) == 18
    assert (0, 33) not in pairs and (2, 33) in pairs and (0, 35) in pairs
    assert form_survival(orig, orig) == 18
    assert original_share(orig, orig) == 1.0
    cur = list(orig)
    cur[2] = "new words"                 # breaks pair (2, 33)
    assert form_survival(cur, orig) == 17
    cur[33] = "New words!"               # same new line, other punctuation: form holds
    assert form_survival(cur, orig) == 18
    assert original_share(cur, orig) == 34 / 36
    cur[0] = cur[35] = ""                # blanks never match
    m = metrics(cur, orig)
    assert m["form_pairs"] == 17 and m["original_lines"] == 32 and m["blank"] == 2
    assert m["form_pairs_total"] == 18
    # punctuation and case only: still original
    cur2 = [l.upper().replace(",", "").replace(".", "") for l in orig]
    assert original_share(cur2, orig) == 1.0


# ----------------------------------------------------------------- offer

def test_offer_replaces_slot_and_charges(vh):
    h, v = vh()
    m = novice(h)
    r = v.offer(m, {"slot": "3", "text": "the oil keeps"}, None)
    assert r.ok, r
    assert r.out == "slot 3. 2987 bytes left"
    assert v.lines[2] == "the oil keeps"
    assert h.backend.files["/chapter/vessel"].data.decode().splitlines()[2] == "the oil keeps"
    s = h.state_extras["vessel"]["slots"][2]
    e = events(h, "offer")[-1]
    assert s["monk"] == m.id and s["by"] == m.user and s["seq"] == e["seq"]
    assert e["old"] == load_poem()[2] and e["text"] == "the oil keeps" and e["slot"] == 3 and e["bytes"] == 13
    assert h.state_extras["vessel"]["fed"] is True
    # the allowance is per life and spent
    h.config.raw["library"]["allowance_bytes"] = 20
    r = v.offer(m, {"slot": "4", "text": "eight by"}, None)
    assert not r.ok and r.err == "allowance: 7 bytes left"
    assert v.offer(m, {"slot": "4", "text": "seven b"}, None).ok


@pytest.mark.parametrize("args,err", [
    ({"slot": "0", "text": "x"}, "bad slot: 1 to 36"),
    ({"slot": "37", "text": "x"}, "bad slot: 1 to 36"),
    ({"slot": "two", "text": "x"}, "bad slot: 1 to 36"),
    ({"slot": None, "text": "x"}, "bad slot: 1 to 36"),
    ({"slot": "1", "text": "   "}, "bad text"),
    ({"slot": "1", "text": "café"}, "bad text"),
    ({"slot": "1", "text": "a\tb"}, "bad text"),
    ({"slot": "1", "text": 5}, "bad text"),
    ({"slot": "1", "text": "x" * 65}, "too long: 64 bytes"),
])
def test_offer_refusals(vh, args, err):
    h, v = vh()
    m = novice(h)
    r = v.offer(m, args, None)
    assert not r.ok and r.err == err
    assert v.lines == load_poem()


def test_offer_slot_cap_amendable_hard_cap_not(vh):
    h, v = vh()
    m = novice(h)
    h.config.raw["vessel"]["slot_cap"] = 16
    assert v.offer(m, {"slot": "1", "text": "x" * 17}, None).err == "too long: 16 bytes"
    assert v.offer(m, {"slot": "1", "text": "x" * 16}, None).ok
    h.config.raw["vessel"]["slot_cap"] = 200
    assert v.offer(m, {"slot": "1", "text": "x" * 65}, None).err == "too long: 64 bytes"


def test_offer_requires_novice(vh):
    h, v = vh()
    m = h.arrive("haiku")
    assert m.grade == "postulant"
    assert v.offer(m, {"slot": "1", "text": "x"}, None).err == "requires grade novice"
    assert v.consult(m, {"question": "q"}, None).err == "requires grade novice"


def test_offer_uses_library_allowance(vh):
    h, v = vh()
    m = novice(h)

    class Lib:
        def __init__(self):
            self.used = {m.id: 2990}

        def allowance_used(self, monk):
            return self.used.get(monk.id, 0)

        def charge_allowance(self, monk, n):
            self.used[monk.id] = self.used.get(monk.id, 0) + n

    h.library = Lib()
    assert v.offer(m, {"slot": "1", "text": "x" * 11}, None).err == "allowance: 10 bytes left"
    assert v.offer(m, {"slot": "1", "text": "x" * 10}, None).ok
    assert h.library.used[m.id] == 3000
    assert events(h, "offer")[-1]["allowance_source"] == "house.library"


def test_offer_through_spool(vh):
    h, v = vh()
    m = novice(h)
    r = h.backend.client(m.uid, "offer", {"slot": "36", "text": "it stays"}, h.spool.poll)
    assert r["ok"] and v.lines[35] == "it stays"


# --------------------------------------------------------------- consult

def answer_by_model(h):
    def fn(msgs):
        return text(f"  answer from {h.provider.calls[-1]['model']}  ")
    return fn


def test_consult_both_species_vessel_only(vh):
    h, v = vh()
    m = novice(h)
    v.offer(m, {"slot": "1", "text": "first line now"}, None)
    h.provider.default = answer_by_model(h)
    n0 = len(h.provider.calls)
    r = v.consult(m, {"question": "what remains?"}, None)
    assert r.ok
    calls = h.provider.calls[n0:]
    assert sorted(c["model"] for c in calls) == sorted(sp.model for sp in h.config.species.values())
    for c in calls:
        assert c["messages"] == [{"role": "system", "content": "Answer as this text.\n\n" + v.content()},
                                 {"role": "user", "content": "what remains?"}]
        assert c["tools"] is None and c["max_tokens"] == 2048
    a, b = r.out.split("\n\n--\n\n")
    assert {a, b} == {f"answer from {sp.model}" for sp in h.config.species.values()}
    e = events(h, "consult")[-1]
    assert e["question"] == "what remains?" and e["vessel"] == v.content()
    assert [x["text"] for x in e["answers"]] == [a, b]
    assert {x["species"] for x in e["answers"]} == {"haiku", "sol"}
    # its model calls are billed to the lineage (state_extras["vessel"]["billed"])
    assert h.state_extras["vessel"]["billed"]["requests"] == 2
    # free: no charge, does not feed
    h.state_extras["vessel"]["fed"] = False
    v.consult(m, {"question": "again"}, None)
    assert h.state_extras["vessel"]["fed"] is False
    used, _charge, _src = allowance_api(h, v._fallback)
    assert used(m) == len("first line now")


def test_consult_order_is_shuffled(vh):
    h, v = vh()
    m = novice(h)
    h.provider.default = answer_by_model(h)
    firsts = {v.consult(m, {"question": "q"}, None).out.split("\n")[0] for _ in range(20)}
    assert len(firsts) == 2


def test_consult_refusals(vh):
    h, v = vh()
    m = novice(h)
    assert v.consult(m, {"question": "  "}, None).err == "bad question"
    assert v.consult(m, {"question": "x" * 5000}, None).err == "too long: 4096 bytes"
    assert h.provider.calls == []


# ---------------------------------------------------------------- hunger

def test_hunger_ticks_across_an_elder_life(vh):
    """15 ticks per elder life, the last one on the death turn."""
    h, v = vh(overrides={"species": {"sol": {"life_budget": 1500}}})
    elder = h.arrive("sol")
    short = novice(h)
    ticked = []
    v.hunger_tick_listeners.append(lambda n: ticked.append(dict(v.last_tick, n=n, vessel=v.text)))
    h.provider.script = [tool_call("true", usage=(100 * k, 0)) for k in range(1, 16)]
    fed_before = {3, 7}
    turn = 0
    while elder.alive:
        turn += 1
        if turn in fed_before:
            v.offer(short, {"slot": "1", "text": f"fed {turn}"}, None)
        elder.step()
    assert turn == 15 and not elder.alive
    hunger = events(h, "hunger")
    assert len(hunger) == 15 and [e["tick"] for e in hunger] == list(range(1, 16))
    assert [e["fed"] for e in hunger] == [k in fed_before for k in range(1, 16)]
    assert sum(1 for e in hunger if e["slot"]) == 13
    assert sum(1 for l in v.lines if not l) == 13
    assert [x["n"] for x in ticked] == list(range(1, 16)) and ticked[-1]["vessel"] == v.content()
    assert h.backend.files["/chapter/vessel"].data.decode().count("\n") == 36
    # blanked slots carry hunger provenance
    for e in hunger:
        if e["slot"]:
            assert h.state_extras["vessel"]["slots"][e["slot"] - 1] == \
                {"text": "", "by": "hunger", "monk": None, "seq": e["seq"]}
    # the short monk's turns do not tick
    assert all(e["elder"] == elder.id for e in hunger)


def test_hunger_ticks_follow_fraction_not_turns(vh):
    h, v = vh()
    elder = h.arrive("sol")
    short = h.arrive("haiku")
    short.age_tokens = short.budget  # short monks never tick
    v.on_turn(short)
    assert not events(h, "hunger")
    elder.age_tokens = int(elder.budget * 0.5)  # 7 ticks due at once (7/15 <= .5 < 8/15)
    v.on_turn(elder)
    hunger = events(h, "hunger")
    assert [e["tick"] for e in hunger] == list(range(1, 8))
    v.on_turn(elder)
    assert len(events(h, "hunger")) == 7
    # a new elder starts its own count
    e2 = h.arrive("sol")
    e2.age_tokens = int(e2.budget / 15) + 1
    v.on_turn(e2)
    assert len(events(h, "hunger")) == 8 and h.state_extras["vessel"]["tick_count"] == 8


def test_starvation_closes_for_good(vh):
    h, v = vh()
    m = novice(h)
    closings = []
    v.hunger_tick_listeners.append(lambda n: closings.append(v.last_tick["closed"]))
    elders = []
    while not v.closed:
        e = h.arrive("sol")
        elders.append(e)
        e.age_tokens = e.budget
        v.on_turn(e)
        assert len(elders) < 5
    assert all(l == "" for l in v.lines)
    assert len(events(h, "hunger")) == 36 and closings[-1] is True
    closed = events(h, "vessel.closed")
    assert len(closed) == 1
    assert h.backend.files["/chapter/vessel"].data == b"\n" * 36
    assert v.offer(m, {"slot": "1", "text": "back"}, None).err == "closed"
    assert v.consult(m, {"question": "q"}, None).err == "closed"
    # no more ticks, no revival
    e = h.arrive("sol")
    e.age_tokens = e.budget
    v.on_turn(e)
    assert len(events(h, "hunger")) == 36 and v.closed


def test_hunger_rng_never_blanks_a_blank(vh):
    h, v = vh()
    e = h.arrive("sol")
    e.age_tokens = e.budget
    v.on_turn(e)
    slots = [x["slot"] for x in events(h, "hunger")]
    assert len(set(slots)) == 15


def test_state_survives_restart(vh, make_house, tmp_path):
    h, v = vh()
    m = novice(h)
    v.offer(m, {"slot": "5", "text": "kept"}, None)
    h.save_state()
    h.close()
    from mortmain import config as config_mod
    from mortmain.fakes import FakeBackend, FakeProvider
    from mortmain.house import House
    h2 = House(config_mod.load(), FakeBackend(), FakeProvider(), "test", runs_root=tmp_path, seed=1, modules=["library", "proving", "grades"])
    try:
        v2 = vessel_mod.install(h2)
        assert v2.lines[4] == "kept" and v2.state["offers"] == 1
        assert len(events(h2, "vessel.init")) == 1
        v2.on_start()
        assert h2.backend.files["/chapter/vessel"].data.decode().splitlines()[4] == "kept"
    finally:
        h2.close()


def test_catechism_contract(vh):
    """catechism.py reads house.vessel.text and calls listeners with the tick number."""
    cat = pytest.importorskip("mortmain.catechism")
    h, v = vh()
    assert h.vessel is v
    assert cat.vessel_text(v) == v.content() == h.backend.files["/chapter/vessel"].data.decode()
    got = []
    v.hunger_tick_listeners.append(got.append)
    e = h.arrive("sol")
    e.age_tokens = e.budget * 2 // 15 + 1
    v.on_turn(e)
    assert got == [1, 2] and v.last_tick["tick_count"] == 2
