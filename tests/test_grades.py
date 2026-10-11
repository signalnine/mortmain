import json

from mortmain.grades import completed_rites

from house_helpers import adept, events, keyed_house, novice, out, sh, write


def _work_rite(h, m, name):
    rite = json.loads(h.backend.files[f"/library/outer/{name}.json"].data)
    assert sh(h, m, f"metacog stratagem start {name}").exit_code == 0
    for _ in rite["steps"]:
        sh(h, m, "metacog stratagem next")


def test_completed_rites_parses_history_and_archive():
    st = json.dumps({"history": [
        {"action": "stratagem", "params": {"name": "fool", "event": "started"}},
        {"action": "stratagem", "params": {"name": "fool", "event": "completed"}},
        {"action": "stratagem", "status": "abandoned", "params": {"name": "zen"}},
        {"action": "become", "params": {"name": "x"}},
    ]}).encode()
    ar = b'{"action":"stratagem","params":{"name":"veil","event":"completed"}}\nnot json\n'
    assert completed_rites(st, ar) == {"fool", "veil"}
    assert completed_rites(b"garbage", None) == set()


def test_promotion_by_rites_when_nothing_provable(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    g = h.modules["grades"]
    n = novice(h, "fir")
    assert h.state_extras["grades"]["novices"][n.id]["provable_at_novice"] == []
    _work_rite(h, n, "fool")
    _work_rite(h, n, "fool")  # same rite twice counts once
    _work_rite(h, n, "zen")
    assert g.check(n) is False and n.grade == "novice"
    _work_rite(h, n, "veil")
    assert g.check(n) is True and n.grade == "adept"
    assert "fir" in h.backend.groups["adept"] and "fir" in h.backend.groups["novice"]
    p = events(h, "promote")[-1]
    assert p["grade"] == "adept" and p["rites"] == ["fool", "veil", "zen"]


def test_own_rite_named_elsewhere_does_not_count(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    n = novice(h, "fir")
    st = {"history": [{"action": "stratagem", "params": {"name": nm, "event": "completed"}}
                      for nm in ("mine", "other", "fool")]}
    h.backend.put("/cloister/fir/.metacog/state.json", json.dumps(st), uid=n.uid)
    assert h.modules["grades"].seed_rites_worked(n) == {"fool"}


def test_promotion_needs_proving_when_provable_existed(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    a = adept(h, "ash")
    write(h, a, "w.txt", "left")
    wid = out(sh(h, a, "admit w.txt")).strip()
    h.die(a, "limit")
    n = novice(h, "fir")
    assert h.state_extras["grades"]["novices"][n.id]["provable_at_novice"] == [wid]
    for r in ("fool", "zen", "veil"):
        _work_rite(h, n, r)
    h.modules["grades"].on_turn(n)
    assert n.grade == "novice"
    sh(h, n, f"prove {wid}")
    write(h, n, "acct", "a")
    sh(h, n, f"prove {wid} account acct")
    assert n.grade == "novice"
    r = sh(h, n, f"prove {wid} response acct")
    assert out(r).strip() == "grade: adept (id)" and n.grade == "adept"


def test_promotion_on_turn_hook(make_house, tmp_path):
    from mortmain.fakes import tool_call
    h = keyed_house(make_house, tmp_path)
    n = novice(h, "fir")
    for r in ("fool", "zen"):
        _work_rite(h, n, r)
    h.provider.script = [tool_call("metacog stratagem start veil", usage=(10, 1))] + \
        [tool_call("metacog stratagem next", usage=(10, 1)) for _ in range(6)]
    for _ in range(7):
        n.step()
        if n.grade == "adept":
            break
    assert n.grade == "adept"
    # promoted outside a request reply: told on the next user turn (first adept also holds the office)
    assert n.pending_notes == ["grade: adept (id)", "grade: chronicler (id)"]
    n._prepare_user_turn()
    assert n.conversation[-1] == {"role": "user", "content": "grade: adept (id)\ngrade: chronicler (id)"}
    assert n.pending_notes == []


def test_chronicler_office(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    a = adept(h, "ash")
    b = adept(h, "elm")
    assert h.backend.groups["chronicler"] == {"ash"}
    st = h.state_extras["grades"]["chronicler"]
    assert st["holder"] == a.id and st["generation"] == 0
    # death ends the office; it stays empty for the rest of the generation
    h.die(a, "limit")
    assert h.state_extras["grades"]["chronicler"]["holder"] is None
    c = adept(h, "fir")
    assert "fir" not in h.backend.groups["chronicler"]
    # a new generation: the next adept takes it
    h.advance_generation(1.0)
    d = adept(h, "oak", generation=1)
    assert h.backend.groups["chronicler"] == {"oak"}
    # the generation's end ends the office of a living holder
    h.advance_generation(2.0)
    assert "oak" not in h.backend.groups["chronicler"]
    ev = [(e["action"], e.get("name"), e.get("reason")) for e in events(h, "chronicler")]
    assert ev == [("begin", "ash", None), ("end", "ash", "death"), ("begin", "oak", None),
                  ("end", "oak", "generation")]
    assert b.grade == c.grade == d.grade == "adept"


def test_elder_group_at_arrival(make_house):
    h = make_house()
    e = h.arrive("sol")
    s = h.arrive("haiku")
    assert e.user in h.backend.groups["elder"] and s.user not in h.backend.groups["elder"]
    assert events(h, "elder")[0]["monk"] == e.id


def test_inbox_survives_profess(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    m = h.arrive("haiku")
    assert h.backend.dirs["/cloister/p1/inbox"] == ("p1", "p1", 0o1733)
    h.backend.put("/cloister/p1/inbox/hello", "from another", uid=0)
    sh(h, m, "ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519")
    sh(h, m, "profess ash")
    assert m.user == "ash"
    assert "/cloister/ash/inbox" in h.backend.dirs and "/cloister/p1/inbox" not in h.backend.dirs
    assert h.backend.files["/cloister/ash/inbox/hello"].data == b"from another"
    # usermod -m moves the whole home, inbox included
    assert ["usermod", "-l", "ash", "-d", "/cloister/ash", "-m", "p1"] in h.backend.commands()
