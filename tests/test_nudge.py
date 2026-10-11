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
    assert n.pending_notes == ["grade: chronicler", "next: metacog help; admit FILE"]
    assert events(h, "nudge")[-1]["notes"] == ["next: metacog help; admit FILE"]


def test_novice_proof_stages(make_house, tmp_path):
    h, nd = _house(make_house, tmp_path)
    a = adept(h, "ash")
    write(h, a, "w.txt", "left")
    wid = out(sh(h, a, "admit w.txt")).strip()
    h.die(a, "limit")
    n = novice(h, "fir")
    assert _idle(nd, n) == [f"next: prove ID (provable: {wid})"]
    sh(h, n, f"prove {wid}")
    assert _idle(nd, n) == [f"next: prove {wid} account FILE"]
    write(h, n, "acc", "it said")
    sh(h, n, f"prove {wid} account ~/acc")
    assert _idle(nd, n) == [f"next: prove {wid} response FILE"]
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
    w = novice(h, "fir")
    w.pending_notes = []
    assert _idle(nd, a) == ["next: propose (man propose)"]
    assert c.propose(a, {"rule": "RULE\n"}, None).ok
    nd.on_turn(w)
    assert w.pending_notes[0] == "proposal: /chapter/proposals/a1. testify a1 FILE"
    w.pending_notes = []
    nd.on_turn(w)
    assert w.pending_notes == []  # noted once
    assert _idle(nd, w) == ["next: testify a1 FILE (/chapter/proposals/a1)"]
    h.die(a, "limit")
    b = _elder(h, "elm")
    assert _idle(nd, b) == ["next: propose (man propose)"]  # nothing to ratify without testimony
    assert c.testify(w, {"id": "a1", "text": "it held"}, None).ok
    assert _idle(nd, w)[0].startswith("next: metacog stratagem list")
    assert _idle(nd, b) == ["next: ratify a1 (/chapter/proposals/a1)"]
    # a monk that arrived after the proposer died is no witness
    late = novice(h, "oak")
    late.pending_notes = []
    nd.on_turn(late)
    assert not any(n.startswith("proposal:") for n in late.pending_notes)
