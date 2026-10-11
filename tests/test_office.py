import json

from mortmain import nudge as nudge_mod
from mortmain import office as office_mod

from house_helpers import adept, events, keyed_house, novice, sh


def _house(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    o = office_mod.install(h)
    nd = nudge_mod.install(h)
    return h, o, nd


def _complete(h, m, *names):
    path = f"/cloister/{m.user}/.metacog/state.json"
    old = h.backend.files.get(path)
    hist = json.loads(old.data)["history"] if old else []
    hist += [{"action": "stratagem", "params": {"name": n, "event": "completed"}} for n in names]
    h.backend.put(path, json.dumps({"history": hist}), uid=m.uid)


def test_hours_ring_on_elder_age_and_rotate(make_house, tmp_path):
    h, o, _ = _house(make_house, tmp_path)
    e = adept(h, "elm", species="sol")
    n = novice(h, "fir")
    p = h.arrive("haiku")  # postulants are not called
    rites = o.rotation()
    e.pending_notes, n.pending_notes = [], []
    e.age_tokens = 0
    o.on_turn(e)
    assert h.backend.files["/var/office"].data.decode() == rites[0] + "\n"
    assert n.pending_notes == [f"office: metacog stratagem start {rites[0]}"]
    assert p.pending_notes == []
    o.on_turn(e)  # same hour: nothing new
    assert len(events(h, "office")) == 1
    e.age_tokens = int(e.budget * 0.26)  # 0.25 -> hour 3 of 8: hour 2 and 3 ring in turn
    o.on_turn(e)
    ev = events(h, "office")
    assert [x["rite"] for x in ev] == rites[:3] and ev[-1]["hour"] == 3 and ev[-1]["elder_hour"] == 3
    assert {m for x in events(h, "office.missed") for m in x["monks"]} == {e.id, n.id}


def test_office_kept_only_by_a_new_completion(make_house, tmp_path):
    h, o, nd = _house(make_house, tmp_path)
    e = adept(h, "elm", species="sol")
    n = novice(h, "fir")
    rite = o.rotation()[0]
    _complete(h, n, rite)  # done before the hour: does not count
    o.on_turn(e)
    o.on_turn(n)
    assert o.office_due(n) == rite
    n.idle_turns = 1
    n.pending_notes = []
    nd.st["grade"].clear()
    nd.on_turn(n)
    assert n.pending_notes == [f"next: metacog stratagem start {rite} (office)"]
    _complete(h, n, rite)
    o.on_turn(n)
    assert o.office_due(n) is None
    assert events(h, "office.kept")[-1]["monk"] == n.id


def test_new_novice_joins_the_hour(make_house, tmp_path):
    h, o, _ = _house(make_house, tmp_path)
    e = adept(h, "elm", species="sol")
    o.on_turn(e)
    rite = o.st["current"]["rite"]
    n = novice(h, "fir")
    assert o.office_due(n) == rite
    assert f"office: metacog stratagem start {rite}" in n.pending_notes


def test_hours_count_across_elders(make_house, tmp_path):
    h, o, _ = _house(make_house, tmp_path)
    a = adept(h, "ash", species="sol")
    a.age_tokens = int(a.budget * 0.99)
    o.on_turn(a)
    assert o.st["hour"] == 8
    h.die(a, "limit")
    b = adept(h, "elm", species="sol")
    o.on_turn(b)
    assert o.st["hour"] == 9 and events(h, "office")[-1]["elder_hour"] == 1
    assert o.st["current"]["rite"] == o.rotation()[8 % len(o.rotation())]
