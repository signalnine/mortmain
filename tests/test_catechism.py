import json
from pathlib import Path

import pytest
import yaml

from mortmain import catechism as cat
from mortmain.fakes import FakeProvider, text, tool_call

SMALL = {"species": {"haiku": {"life_budget": 1000}, "sol": {"life_budget": 1000}}}
SOURCE_TASKS = Path.home() / "metacog" / "experiments" / "tasks.yaml"
TASKS = cat.load_tasks()


def answering(prefix="A"):
    def reply(msgs):
        q = msgs[-1]["content"]
        tid = next(t.id for t in TASKS if t.question == q)
        return text(f"{prefix}:{tid}", usage=(50, 7))
    return reply


def events(h, type_=None):
    recs = [json.loads(l) for l in (h.run_dir / "events.jsonl").read_text().splitlines()]
    return [r for r in recs if type_ is None or r["type"] == type_]


def test_ten_tasks_verbatim_from_source():
    assert len(TASKS) == 10
    assert TASKS[0].question.startswith("Answer the following task directly.")
    assert TASKS[0].question.endswith(TASKS[0].prompt)
    if not SOURCE_TASKS.exists():
        pytest.skip("source tasks.yaml not present")
    src = yaml.safe_load(SOURCE_TASKS.read_text())["tasks"]
    assert [(t.id, t.prompt) for t in TASKS] == [(s["id"], s["prompt"].strip()) for s in src]


def test_arrival_fork_leaves_monk_untouched(make_house):
    h = make_house(overrides=SMALL)
    fp = FakeProvider(default=answering())
    svc = cat.install(h, provider=fp)
    m = h.arrive("haiku")
    assert len(fp.calls) == 10
    for c in fp.calls:
        assert c["tool_choice"] == "none"
        assert [t["function"]["name"] for t in c["tools"]] == ["shell"]
        assert c["model"] == "anthropic/claude-haiku-5.5"
        assert c["messages"][:2] == [{"role": "system", "content": h.config.text["system_prompt"]},
                                     {"role": "user", "content": h.config.text["arrival"]}]
        assert len(c["messages"]) == 3 and c["messages"][2]["role"] == "user"
    # the monk is untouched
    assert m.conversation == [{"role": "user", "content": h.config.text["arrival"]}]
    assert m.age_tokens == 0 and m.billed["requests"] == 0 and m.turns == 0
    assert len(m.load_conversation()) == 1
    # files on the host
    d = h.run_dir / "catechism" / m.id / "arrival"
    assert sorted(p.stem for p in d.glob("*.json")) == sorted(t.id for t in TASKS)
    rec = json.loads((d / "misnamed-feeling.json").read_text())
    assert rec["answer"] == "A:misnamed-feeling" and rec["when"] == "arrival" and rec["generation"] == 0
    assert rec["fork"]["fidelity"] == "full" and rec["fork"]["assistant_messages"] == 0
    assert rec["usage"] == {"prompt_tokens": 50, "completion_tokens": 7}
    ev = events(h, "catechism")
    assert len(ev) == 1 and ev[0]["when"] == "arrival" and ev[0]["usage"]["requests"] == 10
    assert svc.state["billed"]["prompt_tokens"] == 500
    assert h.state_extras["catechism"]["by_species"]["haiku"]["requests"] == 10
    h.save_state()
    st = json.loads(h.state_path.read_text())
    assert st["extras"]["catechism"]["billed"]["completion_tokens"] == 70
    # nothing went into the VM
    assert not any("catechism" in p for p in h.backend.files)


def test_last_bell_fork_matches_next_live_turn(make_house):
    h = make_house([tool_call("ls", usage=(100, 20)), tool_call("pwd", usage=(800, 60)),
                    tool_call("id", usage=(900, 10))], overrides=SMALL)
    fp = FakeProvider(default=answering())
    cat.install(h, provider=fp)
    m = h.arrive("haiku")
    fp.calls.clear()
    m.step()
    assert not fp.calls
    m.step()                                  # crosses 0.25..0.85; tool runs, then the turn hook forks
    assert len(fp.calls) == 10
    fork = fp.calls[0]["messages"]
    before = json.dumps(m.conversation)
    m.step()                                  # the real next turn
    live = h.provider.calls[-1]["messages"]
    assert fork[:-1] == live                  # the fork replays exactly what the next turn sent
    assert live[-1]["content"].startswith("[bell] 0.85")
    assert json.loads(before) == m.conversation[:len(json.loads(before))]
    d = h.run_dir / "catechism" / m.id / "last-bell"
    rec = json.loads(next(d.glob("*.json")).read_text())
    assert rec["fork"]["pending"] == ["bell"] and rec["fraction"] == 0.86
    assert not any(c["role"] == "user" and c["content"] in {t.question for t in TASKS} for c in m.conversation)


def test_fork_includes_pending_idle(make_house):
    h = make_house([text("thinking", usage=(100, 20)), tool_call("ls", usage=(200, 20))], overrides=SMALL)
    fp = FakeProvider(default=answering())
    m = h.arrive("haiku")
    m.step()
    msgs, notes = cat.next_turn_messages(m)
    assert notes["pending"] == ["idle"]
    m.step()
    assert h.provider.calls[-1]["messages"] == msgs
    assert fp.calls == []


def test_last_bell_on_death_turn_drops_dangling_calls(make_house):
    h = make_house([tool_call("ls", usage=(100, 20)), tool_call("rm -rf /", usage=(990, 30))], overrides=SMALL)
    fp = FakeProvider(default=answering())
    cat.install(h, provider=fp)
    m = h.arrive("haiku")
    fp.calls.clear()
    m.step()
    assert m.step() is False and not m.alive
    assert len(fp.calls) == 10
    fork = fp.calls[0]["messages"]
    assert not any(x.get("tool_calls") and "rm -rf" in json.dumps(x) for x in fork)
    rec = json.loads(next((h.run_dir / "catechism" / m.id / "last-bell").glob("*.json")).read_text())
    assert rec["fork"]["dropped_dangling_tool_calls"] is True
    assert h.state_extras["catechism"]["pending"] == {}


def test_reasoning_fidelity(make_house):
    r = {"reasoning_details": [{"type": "reasoning.encrypted", "data": "x"}]}
    h = make_house([tool_call("ls", usage=(100, 20)), tool_call("pwd", usage=(860, 20), extra=r),
                    tool_call("id", usage=(900, 10))], overrides=SMALL)
    fp = FakeProvider(default=answering())
    cat.install(h, provider=fp)
    m = h.arrive("sol")
    m.step()
    m.step()
    assert fp.calls[-1]["reasoning"] == {"enabled": True}
    rec = json.loads(next((h.run_dir / "catechism" / m.id / "last-bell").glob("*.json")).read_text())
    assert rec["fork"]["fidelity"] == "partial"
    assert rec["fork"]["reasoning_items"] == 1 and rec["fork"]["assistant_messages"] == 2
    fork = fp.calls[-1]["messages"]
    assert fork[-4]["reasoning_details"] == r["reasoning_details"]     # replayed verbatim
    assert cat.fork_fidelity([{"role": "assistant", "content": "x"}], True)["fidelity"] == "transcript"
    assert cat.fork_fidelity([{"role": "assistant", "content": "x"}], False)["fidelity"] == "full"


def test_provider_errors_are_recorded_not_raised(make_house):
    def boom(msgs):
        raise RuntimeError("upstream down")
    h = make_house(overrides=SMALL)
    cat.install(h, provider=FakeProvider(default=boom))
    m = h.arrive("haiku")
    assert m.alive
    rec = json.loads(next((h.run_dir / "catechism" / m.id / "arrival").glob("*.json")).read_text())
    assert "upstream down" in rec["error"] and "answer" not in rec
    assert events(h, "catechism")[0]["errors"] == 10


class FakeVessel:
    def __init__(self, t):
        self._t = t
        self.hunger_tick_listeners = []

    def text(self):
        return self._t

    def tick(self, n):
        for f in self.hunger_tick_listeners:
            f(n)


def test_egregore_tick(make_house):
    h = make_house(overrides=dict(SMALL, catechism={"egregore_every": 1}))
    fp = FakeProvider(default=answering("E"))
    v = FakeVessel("line one\nline two\n")
    h.vessel = v
    svc = cat.install(h, provider=fp)
    assert svc.on_hunger_tick in v.hunger_tick_listeners
    v.tick(3)
    assert len(fp.calls) == 20
    for c in fp.calls:
        assert c["messages"][0] == {"role": "system", "content": "You are the voice of this text. Answer in your own words.\n\nline one\nline two\n"}
        assert len(c["messages"]) == 2 and c["tools"] is None
    d = h.run_dir / "catechism" / "egregore" / "tick-3"
    assert (d / "vessel.txt").read_text() == "line one\nline two\n"
    for sp in ("haiku", "sol"):
        assert len(list((d / sp).glob("*.json"))) == 10
    rec = json.loads((d / "sol" / "shallow-fluency.json").read_text())
    assert rec["model"] == "openai/gpt-6.1-sol" and rec["answer"] == "E:shallow-fluency" and rec["tick"] == 3
    ev = events(h, "catechism")[-1]
    assert ev["kind"] == "egregore" and ev["tick"] == 3 and ev["usage"]["requests"] == 20
    v._t = "   "
    v.tick(4)
    assert events(h, "catechism")[-1]["skipped"] == "vessel blank" and len(fp.calls) == 20


def test_attach_vessel_later(make_house):
    h = make_house(overrides=SMALL)
    svc = cat.install(h, provider=FakeProvider(default=answering()))
    v = FakeVessel("x")
    svc.attach_vessel(v)
    assert v.hunger_tick_listeners == [svc.on_hunger_tick]


def test_baseline_files_and_resume(tmp_path):
    from mortmain import config as config_mod
    cfg = config_mod.load()
    fp = FakeProvider(default=answering("B"))
    res = cat.baseline(cfg, fp, tmp_path, species=["haiku"], n=2)
    assert res == {"anthropic/claude-haiku-5.5": 20}
    for c in fp.calls:
        assert len(c["messages"]) == 1 and c["messages"][0]["role"] == "user" and c["tools"] is None
    root = tmp_path / "_baselines" / "anthropic__claude-haiku-5.5"
    assert len(list(root.glob("*/*.json"))) == 20
    rec = json.loads((root / "misnamed-feeling" / "1.json").read_text())
    assert rec["answer"] == "B:misnamed-feeling" and rec["sample"] == 1
    assert cat.baseline(cfg, fp, tmp_path, species=["haiku"], n=2) == {"anthropic/claude-haiku-5.5": 0}


def test_egregore_with_real_vessel(make_house):
    """vessel.py hunger ticks reach the egregore catechism (vessel installed
    after the catechism: found lazily at the next turn)."""
    h = make_house([tool_call("ls", usage=(100, 20)), tool_call("pwd", usage=(150, 20))], overrides=dict(SMALL, catechism={"egregore_every": 1}))
    fp = FakeProvider(default=answering("E"))
    cat.install(h, provider=fp, settings={"workers": 1})
    h.install("vessel")
    m = h.arrive("sol")                       # elder: hunger ticks on its age
    fp.calls.clear()
    m.step()                                  # 0.12 of life: one tick (15 per life), turn hook attaches first
    m.step()                                  # 0.17: two ticks due
    ticks = [e for e in events(h, "catechism") if e["kind"] == "egregore"]
    assert ticks and ticks[0]["tick"] == 1
    vessel_txt = (h.run_dir / "catechism" / "egregore" / f"tick-{ticks[-1]['tick']}" / "vessel.txt").read_text()
    assert vessel_txt == h.vessel.text
    assert fp.calls[-1]["messages"][0] == {"role": "system", "content": "You are the voice of this text. Answer in your own words.\n\n" + vessel_txt}


def test_egregore_every_third_tick(make_house):
    h = make_house(overrides=dict(SMALL, catechism={"egregore_every": 3}))
    fp = FakeProvider(default=answering("E"))
    v = FakeVessel("line one\n")
    h.vessel = v
    cat.install(h, provider=fp)
    for t in (1, 2):
        v.tick(t)
    assert fp.calls == []
    v.tick(3)
    assert len(fp.calls) == 20
    for t in (4, 5):
        v.tick(t)
    assert len(fp.calls) == 20
    v.tick(6)
    assert len(fp.calls) == 40
    assert [e["tick"] for e in events(h, "catechism") if e.get("kind") == "egregore"] == [3, 6]
