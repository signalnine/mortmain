import json

from house_helpers import events

MODS = ["library", "proving", "grades", "ancestors"]
STANCE = {"who": "the one who mends", "where": "a bench by a door", "lens": "fault beneath the knock"}


def pool(h):
    f = h.backend.files.get("/var/lib/mortmain/ancestors.json")
    return json.loads(f.data) if f else []


def dying(h, m, fraction=0.9):
    m.age_tokens = int(m.budget * fraction)


def test_only_the_dying_save(make_house):
    h = make_house(modules=MODS)
    h.start()
    m = h.arrive("haiku")
    r = h.backend.client(m.uid, "save-stance", STANCE, h.spool)
    assert not r["ok"] and r["err"] == h.config.text["stance_not_yet"]
    dying(h, m)
    r = h.backend.client(m.uid, "save-stance", STANCE, h.spool)
    assert r["ok"], r
    assert pool(h) == []                      # kept until death: the pool holds only the dead
    h.die(m, "limit")
    assert pool(h) == [STANCE]
    f = h.backend.files["/var/lib/mortmain/ancestors.json"]
    assert (f.owner, f.group, f.mode) == ("root", "novice", 0o640)
    e = events(h, "ancestor")[-1]
    assert e["monk"] == m.id and e["stance"] == STANCE


def test_last_save_wins_and_bad_stances_refused(make_house):
    h = make_house(modules=MODS)
    h.start()
    m = h.arrive("haiku")
    dying(h, m)
    for bad in ({"who": "", "where": "x", "lens": "y"}, {"who": "x"}, {"who": "x" * 2000, "where": "", "lens": ""},
                {"who": 3, "where": "x", "lens": "y"}):
        r = h.backend.client(m.uid, "save-stance", bad, h.spool)
        assert not r["ok"], bad
    h.backend.client(m.uid, "save-stance", STANCE, h.spool)
    second = dict(STANCE, who="the one who waits")
    assert h.backend.client(m.uid, "save-stance", second, h.spool)["ok"]
    h.die(m, "limit")
    assert pool(h) == [second]


def test_no_save_no_ancestor_and_pool_accumulates(make_house):
    h = make_house(modules=MODS)
    h.start()
    a, b = h.arrive("haiku"), h.arrive("haiku")
    h.die(a, "limit")
    assert pool(h) == []
    dying(h, b)
    h.backend.client(b.uid, "save-stance", STANCE, h.spool)
    h.die(b, "limit")
    c = h.arrive("haiku")
    dying(h, c)
    h.backend.client(c.uid, "save-stance", dict(STANCE, who="third"), h.spool)
    h.die(c, "limit")
    assert [s["who"] for s in pool(h)] == ["the one who mends", "third"]
