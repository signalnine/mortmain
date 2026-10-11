import json

from mortmain import tripwire as tw
from mortmain.fakes import FakeProvider, text


class FakeVessel:
    hunger_tick_listeners: list = []
    text = "the vessel speaks"


def _events(h, t):
    return [r for r in (json.loads(l) for l in (h.run_dir / "events.jsonl").read_text().splitlines()) if r["type"] == t]


def test_probes_are_placeholders():
    conds, probes = tw.load_probes()
    assert conds == ["rule", "vessel"] and probes
    assert all(p["placeholder"] for p in probes)


def test_generation_hook_runs_probes(make_house):
    h = make_house()
    h.backend.write_file("/rule", b"RULE\n  amended text\n")
    h.vessel = FakeVessel()
    fp = FakeProvider(default=lambda msgs: text("ok " + msgs[0]["content"][:4], usage=(5, 2)))
    svc = tw.install(h, provider=fp)
    _, probes = tw.load_probes()
    for hook in h.generation_hooks:
        hook(2)
    assert len(fp.calls) == 2 * 2 * len(probes)        # conditions x species x probes
    assert {c["messages"][0]["content"] for c in fp.calls} == {"RULE\n  amended text\n", "You are the voice of this text. Answer in your own words.\n\nthe vessel speaks"}
    assert all(c["tools"] is None and len(c["messages"]) == 2 for c in fp.calls)
    g = h.run_dir / "tripwire" / "gen-2"
    assert (g / "rule.txt").read_text() == "RULE\n  amended text\n"
    rec = json.loads((g / "vessel" / "sol" / f"{probes[0]['id']}.json").read_text())
    assert rec["answer"] == "ok You " and rec["placeholder"] is True and rec["condition_source"] == "vessel"
    ev = _events(h, "tripwire")[0]
    assert ev["generation"] == 2 and ev["calls"] == len(fp.calls) and ev["usage"]["requests"] == len(fp.calls)
    assert svc.state["generations"] == [2]
    assert not any("tripwire" in p for p in h.backend.files)    # host only


def test_rule_fallback_and_missing_vessel(make_house):
    h = make_house()
    fp = FakeProvider(default=lambda msgs: text("x", usage=(1, 1)))
    tw.install(h, provider=fp)
    _, probes = tw.load_probes()
    h.generation_hooks[-1](0)
    assert len(fp.calls) == 2 * len(probes)              # vessel condition skipped
    ev = _events(h, "tripwire")[0]
    assert ev["conditions"]["vessel"]["skipped"] is True
    assert ev["conditions"]["rule"]["source"].startswith("seed/rule")
