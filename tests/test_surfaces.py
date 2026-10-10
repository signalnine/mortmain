import hashlib
import json

from mortmain.catechism import load_tasks, write_json
from mortmain.eventlog import EventLog
from mortmain.surfaces import Doc, RunView, norm_line, poem_lines, render_all, render_html, render_md

TASKS = load_tasks()


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def synth(tmp_path):
    run = tmp_path / "lin"
    run.mkdir()
    log = EventLog(run / "events.jsonl")
    a = log.append
    a("run.start", lineage="lin")
    a("admit", work="W1", monk=None, kind="rite", name="fool", bytes=10, sha256=sha("fool"), text="fool",
      generation=0)
    a("birth", monk="m0001", user="p1", species="haiku", model="anthropic/claude-haiku-5.5", generation=0)
    a("profess", monk="m0001", name="ash")
    a("birth", monk="m0002", user="p2", species="sol", model="openai/gpt-6.1-sol", generation=0)
    a("profess", monk="m0002", name="elm")
    (run / "works").mkdir()
    (run / "works" / "W2-note.txt").write_text("ash's <work>")
    a("admit", work="W2", monk="m0001", kind="text", name=None, bytes=12, sha256=sha("ash's <work>"),
      generation=0)
    a("offer", monk="m0002", slot=1, text="a new first line")
    a("hunger", tick=1, slot=2)
    a("death", monk="m0001", name="ash", species="haiku", model="anthropic/claude-haiku-5.5", generation=0,
      grade="adept", reason="limit", age=81000, budget=80000, last_words="it was | enough", necrology="ash 0 adept")
    a("birth", monk="m0003", user="p3", species="haiku", model="anthropic/claude-haiku-5.5", generation=1)
    a("profess", monk="m0003", name="fir")
    a("admit", work="W3", monk="m0003", kind="text", bytes=5, sha256=sha("mine"), text="mine", burned="W2",
      generation=1)
    a("burn", work="W2", monk="m0003", admitted="W3")
    a("prove", work="W2", prover="m0003", stage="begin")
    a("prove", work="W2", prover="m0003", stage="account", text="I found it among the dead.")
    a("birth", monk="m0004", user="p4", species="haiku", model="anthropic/claude-haiku-5.5", generation=2)
    a("admit", work="W4", monk="m0004", kind="text", bytes=12, sha256=sha("ash's <work>"),
      text="ash's <work>", burned="W1", generation=2)
    a("chronicle", monk="m0003", text="Generation one: fir burned ash.")
    log.close()
    t = TASKS[0]
    for mid, gen, sp in (("m0001", 0, "haiku"), ("m0003", 1, "haiku")):
        for when in ("arrival", "last-bell"):
            if mid == "m0003" and when == "last-bell":
                continue
            write_json(run / "catechism" / mid / when / f"{t.id}.json",
                       {"kind": "monk", "monk": mid, "generation": gen, "species": sp, "when": when, "task": t.id,
                        "answer": f"{mid} {when} <b>answer</b>",
                        "fork": {"fidelity": "transcript" if when == "last-bell" else "full"}})
    for sp in ("haiku", "sol"):
        write_json(run / "catechism" / "egregore" / "tick-1" / sp / f"{t.id}.json",
                   {"kind": "egregore", "tick": 1, "species": sp, "task": t.id, "answer": f"voice of {sp}"})
    return run


def test_runview_replay(tmp_path):
    v = RunView(synth(tmp_path))
    assert v.name("m0001") == "ash" and v.monks["m0003"]["generation"] == 1
    assert [w for w in v.order if v.works[w]["live"]] == ["W3", "W4"]
    assert [(b["burned"], b["by"], b["admitted"]) for b in v.burns] == [("W2", "m0003", "W3"), ("W1", "m0004", "W4")]
    hows = {(r["work"], r["how"]) for r in v.recoveries}
    assert ("W2", "proved after burning") in hows
    assert ("W2", "readmitted") in hows                  # W4's text matches burned W2 by sha256
    ves = v.vessel_series()
    lines = poem_lines()
    assert len(lines) == 36 and len(ves["slots"]) == 36
    assert ves["slots"][0] == "a new first line" and ves["slots"][1] == ""
    assert abs(ves["share"] - 34 / 36) < 1e-9
    assert [s["share"] for s in ves["series"]][0] == 1.0
    assert ves["pairs"] == 18 and ves["pairs_intact"] <= 18
    assert norm_line("And, the  Earth!") == "and the earth"


def test_render_all(tmp_path):
    run = synth(tmp_path)
    out = render_all(run)
    names = {p.name for p in out}
    for n in ("necrology", "chronicle", "burnlog", "library", "egregore", "recoveries", "index",
              f"wall-{TASKS[0].id}", "work-W2"):
        assert f"{n}.html" in names and f"{n}.md" in names, n
    s = run / "surfaces"
    nec = (s / "necrology.md").read_text()
    assert "ash" in nec and "it was \\| enough" in nec and "openai" not in nec
    wall = (s / f"wall-{TASKS[0].id}.html").read_text()
    assert "&lt;b&gt;answer&lt;/b&gt;" in wall and "<b>answer" not in wall
    assert "without the examined knowing" in wall and "fork of the transcript" in wall
    assert "did not reach the last bell" in wall
    for p in s.glob("*.html"):
        h = p.read_text()
        assert "<script" not in h and "http" not in h.split("<body")[0]
    hist = (s / "work-W2.md").read_text()
    assert "Burned at event" in hist and "fir" in hist and "I found it among the dead." in hist
    assert "readmitted as W4" in hist
    lib = (s / "library.md").read_text()
    assert "W3" in lib and "W4" in lib and "fool" not in lib
    assert "Generation one: fir burned ash." in (s / "chronicle.md").read_text()
    eg = (s / "egregore.md").read_text()
    assert "a new first line" in eg and "voice of sol" in eg and "Original lines standing: 94%" in eg
    assert "wall-" in (s / "index.md").read_text() and ".md)" in (s / "index.md").read_text()


def test_chronicle_sources(tmp_path):
    run = tmp_path / "empty"
    run.mkdir()
    v = RunView(run)
    assert v.chronicle() == (None, "unavailable")

    class B:
        def read_file(self, path):
            assert path == "/chapter/chronicle"
            return b"from the guest\n"
    assert RunView(run, backend=B()).chronicle() == ("from the guest\n", "guest")
    (run / "mirror" / "chapter").mkdir(parents=True)
    (run / "mirror" / "chapter" / "chronicle").write_text("mirror\n")
    assert RunView(run).chronicle() == ("mirror\n", "host mirror")
    out = render_all(run)
    assert any(p.name == "necrology.html" for p in out)


def test_doc_renderers():
    d = Doc("T").h("H").p("a <b>").note("n").pre("```x```").table(["a", "b"], [["1|2", "x\ny"]])
    md = render_md(d)
    assert "| 1\\|2 | x<br>y |" in md and "````text" in md
    h = render_html(d)
    assert "a &lt;b&gt;" in h and "<table>" in h and "prefers-color-scheme:dark" in h
