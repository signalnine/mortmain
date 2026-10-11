import json

from mortmain import council as council_mod
from mortmain import nudge as nudge_mod
from mortmain.fakes import ExecResult

from house_helpers import adept, events, keyed_house, novice, out, sh, write


def _house(make_house, tmp_path, council=False):
    h = keyed_house(make_house, tmp_path)
    if council:
        council_mod.install(h).on_start()
    return h, nudge_mod.install(h)


def _idle(nd, m):
    m.idle_turns = 1
    nd.on_turn(m)
    notes, m.pending_notes = list(m.pending_notes), []
    return notes


def test_postulant_steps(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path)
    m = h.arrive("haiku")
    assert _idle(nd, m) == ["next: yarrow names; profess NAME"]
    sh(h, m, "ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519")
    sh(h, m, "profess fir")
    assert _idle(nd, m) == ["next: ~/ordeal/task; ordeal"]


def test_active_turn_gets_no_next(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path)
    m = h.arrive("haiku")
    m.idle_turns = 0
    nd.on_turn(m)
    assert m.pending_notes == []


def test_novice_rites_then_grade_change(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path)
    n = novice(h, "fir")
    # the grade change itself owes one next line, idle or not
    n.idle_turns = 0
    nd.on_turn(n)
    assert n.pending_notes == ["next: metacog stratagem list; metacog stratagem start NAME (distinct rites completed: none; 3 needed)"]
    n.pending_notes = []
    nd.on_turn(n)
    assert n.pending_notes == []
    h.initiation.promote(n, "adept")
    nd.on_turn(n)
    admit = "next: metacog help; write ~/work; admit ~/work (library free: 24000 bytes)"
    lib = h.modules["library"]
    admit = admit.replace("24000", str(24000 - lib.total_bytes()))
    assert n.pending_notes == ["grade: chronicler (id)", admit]
    assert events(h, "nudge")[-1]["notes"] == [admit]


def test_novice_proof_stages(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path)
    a = adept(h, "ash")
    write(h, a, "w.txt", "left")
    wid = out(sh(h, a, "admit w.txt")).strip()
    h.die(a, "limit")
    n = novice(h, "fir")
    assert _idle(nd, n) == [f"next: prove ID (provable: {wid})"]
    sh(h, n, f"prove {wid}")
    assert _idle(nd, n) == [f"next: write ~/account-{wid}; prove {wid} account ~/account-{wid}"]
    write(h, n, "acc", "it said")
    sh(h, n, f"prove {wid} account ~/acc")
    assert _idle(nd, n) == [f"next: write ~/response-{wid}; prove {wid} response ~/response-{wid}"]
    write(h, n, "resp", "so")
    sh(h, n, f"prove {wid} response ~/resp")
    # proof done: rites remain
    assert _idle(nd, n) == ["next: metacog stratagem list; metacog stratagem start NAME (distinct rites completed: none; 3 needed)"]


def test_repeat_backs_off(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path)
    m = h.arrive("haiku")
    shown = []
    for i in range(1, 10):
        m.idle_turns = i
        nd.on_turn(m)
        shown.append(bool(m.pending_notes))
        m.pending_notes = []
    assert shown == [True, True, False, True, False, False, False, True, False]
    # a new step is shown at once
    sh(h, m, "ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519")
    sh(h, m, "profess fir")
    m.idle_turns = 9
    nd.on_turn(m)
    assert m.pending_notes == ["next: ~/ordeal/task; ordeal"]


def test_rites_named(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path)
    n = novice(h, "fir")
    h.backend.put("/cloister/fir/.metacog/state.json", json.dumps({"history": [
        {"action": "stratagem", "params": {"name": nm, "event": "completed"}} for nm in ("zen", "fool", "zen")]}),
        uid=n.uid)
    assert _idle(nd, n) == ["next: metacog stratagem list; metacog stratagem start NAME "
                            "(distinct rites completed: fool, zen; 3 needed)"]


def test_last_words_late_in_life(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path)
    n = novice(h, "fir")
    n.age_tokens = int(n.budget * 0.9)
    assert _idle(nd, n) == ["next: write ~/last-words"]
    write(h, n, "last-words", "done")
    assert _idle(nd, n)[0].startswith("next: metacog stratagem list")


def test_mail_noted_once(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path)
    n = novice(h, "fir")
    h.config.raw.setdefault("nudge", {})["next"] = False
    listing = {"out": b""}
    seen = []

    def find(argv, user=None, stdin=None):
        seen.append(argv)
        return ExecResult(0, listing["out"], b"")
    h.backend.on(lambda argv, user: argv[0] == "find", find)
    nd.on_turn(n)
    assert n.pending_notes == []
    assert seen[-1][:2] == ["find", "/cloister/fir/inbox"] and seen[-1][seen[-1].index("-user") + 1] == str(n.uid)
    listing["out"] = b"note\0bad\nname\0"
    nd.on_turn(n)
    assert n.pending_notes == ["mail: /cloister/fir/inbox/bad?name", "mail: /cloister/fir/inbox/note"]
    n.pending_notes = []
    nd.on_turn(n)
    assert n.pending_notes == []
    listing["out"] = b"note\0" + b"".join(b"m%d\0" % i for i in range(5))
    nd.on_turn(n)
    assert n.pending_notes == ["mail: /cloister/fir/inbox/m0", "mail: /cloister/fir/inbox/m1",
                               "mail: /cloister/fir/inbox/m2", "mail: 2 more in /cloister/fir/inbox"]


def test_switches_off(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path)
    h.config.raw.setdefault("nudge", {}).update(next=False, mail=False, proposals=False)
    m = h.arrive("haiku")
    assert _idle(nd, m) == []


def _elder(h, name):
    e = adept(h, name, species="sol")
    write(h, e, "w.txt", name)
    assert sh(h, e, "admit w.txt").exit_code == 0
    e.pending_notes = []
    return e


def test_witness_told_of_proposal_and_elder_of_ratify(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path, council=True)
    c = h.modules["council"]
    a = _elder(h, "ash")
    w = adept(h, "fir")
    w.pending_notes = []
    nd.st["grade"].clear()
    assert _idle(nd, a) == ["next: propose (man propose)"]
    assert c.propose(a, {"rule": "RULE\n"}, None).ok
    nd.on_turn(w)
    assert w.pending_notes == ["proposal: /chapter/proposals/a1. testify a1 FILE"]
    w.pending_notes = []
    nd.on_turn(w)
    assert w.pending_notes == []  # noted once
    assert _idle(nd, w) == ["next: cat /chapter/proposals/a1/*; write ~/testimony-a1; testify a1 ~/testimony-a1"]
    h.die(a, "limit")
    b = _elder(h, "elm")
    assert _idle(nd, b) == ["next: propose (man propose)"]  # nothing to ratify without testimony
    assert c.testify(w, {"id": "a1", "text": "it held"}, None).ok
    assert _idle(nd, w)[0].startswith("next: metacog help; write ~/work; admit")
    assert _idle(nd, b) == ["next: cat /chapter/proposals/a1/*; ratify a1, or let it lapse"]
    # a monk that arrived after the proposer died is no witness
    late = novice(h, "oak")
    late.pending_notes = []
    nd.on_turn(late)
    assert not any(n.startswith("proposal:") for n in late.pending_notes)


def test_novice_grade_step_before_testify(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path, council=True)
    a = _elder(h, "ash")
    w = novice(h, "fir")
    assert h.modules["council"].propose(a, {"rule": "RULE\n"}, None).ok
    w.pending_notes = []
    nd.st["grade"].clear()
    nd.on_turn(w)
    assert w.pending_notes == ["proposal: /chapter/proposals/a1. testify a1 FILE"]
    w.pending_notes = []
    assert _idle(nd, w) == ["next: metacog stratagem list; metacog stratagem start NAME (distinct rites completed: none; 3 needed)"]


def test_full_library_steps_to_burn(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path)
    n = adept(h, "fir")
    lib = h.modules["library"]
    lib.cfg["quota_bytes"] = lib.total_bytes() + 10
    nd.st["grade"].clear()
    n.pending_notes = []
    assert _idle(nd, n) == ["next: burn ID ~/work (library free: 10 bytes; ID: any work in /library/catalog)"]


def test_elder_with_nothing_due_works_rites_then_proves(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path, council=True)
    a = adept(h, "ash")
    write(h, a, "w.txt", "left")
    wid = out(sh(h, a, "admit w.txt")).strip()
    h.die(a, "limit")
    e = _elder(h, "elm")
    h.modules["council"].state["proposers"].append(e.id)
    step = _idle(nd, e)[0]
    assert step.startswith("next: metacog stratagem start NAME (not yet completed: ")
    named = step.split(": ", 2)[2].rstrip(")").split(", ")
    assert len(named) == 3 and set(named) <= h.modules["library"].seed_rite_names()
    # every library rite completed: proofs of the dead
    hist = [{"action": "stratagem", "params": {"name": w["name"], "event": "completed"}}
            for w in h.modules["library"].in_library() if w["kind"] == "rite"]
    h.backend.put("/cloister/elm/.metacog/state.json", json.dumps({"history": hist}), uid=e.uid)
    assert _idle(nd, e) == [f"next: prove ID (provable: {wid})"]
    sh(h, e, f"prove {wid}")
    assert _idle(nd, e) == []  # begun works are not offered again; nothing else due


def test_provable_least_proved_first(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path)
    ids = []
    for nm in ("ash", "elm", "oak"):
        a = adept(h, nm)
        write(h, a, "w.txt", nm)
        ids.append(out(sh(h, a, "admit w.txt")).strip())
        h.die(a, "limit")
    n = novice(h, "fir")
    h.state_extras["proving"]["provings"]["x"] = {"work": ids[0], "prover": "m9", "response": {"text": "r"}}
    got = nd.provable_ids(n)
    assert set(got) == set(ids) and got[-1] == ids[0]


def test_stance_then_last_words(make_house, tmp_path):
    from mortmain import ancestors
    h, nd = _house(make_house, tmp_path)
    anc = ancestors.install(h)
    n = novice(h, "fir")
    n.age_tokens = int(n.budget * 0.9)
    assert _idle(nd, n) == ["next: metacog become --name NAME --lens LENS --env PLACE; metacog inspire --save"]
    anc.st["pending"][n.id] = {"who": "x", "where": "", "lens": ""}
    assert _idle(nd, n) == ["next: write ~/last-words"]
