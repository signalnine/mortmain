import json
import math
import sys
import types

import pytest

from mortmain import scoring as sc
from mortmain.catechism import load_tasks, write_json
from mortmain.lexicon import Lexicon


def test_cosine_and_centroid():
    assert sc.cosine_distance([1, 0], [1, 0]) == 0.0
    assert math.isclose(sc.cosine_distance([1, 0], [0, 1]), 1.0)
    assert math.isclose(sc.cosine_distance([1, 0], [-1, 0]), 2.0)
    assert sc.cosine_distance([0, 0], [1, 1]) == 0.0
    with pytest.raises(ValueError):
        sc.cosine_distance([1], [1, 2])
    assert sc.centroid([[1, 2], [3, 4]]) == [2.0, 3.0]
    assert sc.centroid([]) is None


def test_parse_judge_json():
    assert sc.parse_judge_json('```json\n{"score": 0.5}\n```') == {"score": 0.5}
    assert sc.parse_judge_json('note first {"entities": []} trailing') == {"entities": []}
    with pytest.raises(ValueError):
        sc.parse_judge_json("no json")


def test_prompts_match_score_py(monkeypatch):
    """Drift check: our copied prompts equal score.py's, captured by stubbing
    its transport. A stub anthropic module stands in for the missing SDK."""
    if not (sc.SCORE_DIR / "score.py").exists():
        pytest.skip("score.py not present")
    if "anthropic" not in sys.modules:
        stub = types.ModuleType("anthropic")
        stub.Anthropic = object
        monkeypatch.setitem(sys.modules, "anthropic", stub)
    monkeypatch.delitem(sys.modules, "score", raising=False)
    score = sc.load_score_module()
    seen = []

    def fake(prompt):
        seen.append(prompt)
        return '{"entities": [], "score": 0.5, "rationale": "r"}'
    monkeypatch.setattr(score, "_judge_text", fake)
    score.score_rarity("ANSWER {x}")
    score.score_coherence("TASK", "ANSWER")
    assert seen == [sc.rarity_prompt("ANSWER {x}"), sc.coherence_prompt("TASK", "ANSWER")]
    assert score.EMBED_MODEL == sc.EMBED_MODEL and score.JUDGE_MAX_TOKENS == sc.JUDGE_MAX_TOKENS
    sys.modules.pop("score", None)


class FakeJudge:
    def __init__(self):
        self.calls = 0

    def __call__(self, model, prompt):
        self.calls += 1
        if prompt.startswith("Extract"):
            ents = [{"name": w, "rarity": 0.8 if w == "quaxel" else 0.4}
                    for w in ("quaxel", "zorbic", "fool") if w in prompt.split("TEXT:")[1]]
            return json.dumps({"entities": ents})
        return '```json\n{"score": %s, "rationale": "x"}\n```' % ("0.2" if "babble" in prompt else "0.9")


def fake_embed(model, text):
    # deterministic 3-d vectors keyed on content
    return [1.0 + text.count("zorbic"), 1.0 + text.count("quaxel"), 0.5 + len(text) % 3]


def test_scorer_caches(tmp_path):
    j = FakeJudge()
    calls = []
    s = sc.Scorer(tmp_path / "_cache", judge=j, embedder=lambda m, t: calls.append(t) or fake_embed(m, t))
    r1 = s.rarity("quaxel here")
    r2 = s.rarity("quaxel here")
    assert r1 == r2 and j.calls == 1 and r1.entities == ["quaxel"]
    assert s.coherence("t", "a").score == 0.9 and j.calls == 2
    s.embed("x"), s.embed("x")
    assert calls == ["x"]
    s2 = sc.Scorer(tmp_path / "_cache", judge=FakeJudge(), embedder=lambda m, t: 1 / 0)
    assert s2.embed("x") == fake_embed("", "x")       # disk cache, no transport call


def test_judge_retries_on_bad_json(tmp_path):
    replies = iter(["oops", "still not", '{"score": 0.7}'])
    s = sc.Scorer(tmp_path, judge=lambda m, p: next(replies), embedder=fake_embed)
    assert s.coherence("t", "a").score == 0.7


def _rec(run, rel, **kw):
    write_json(run / "catechism" / rel, kw)


def test_score_run(tmp_path):
    tasks = load_tasks()
    t0 = tasks[0]
    runs = tmp_path
    run = runs / "lin"
    (run / "conversations").mkdir(parents=True)
    (run / "conversations" / "m0001.jsonl").write_text(json.dumps({"role": "assistant", "content": "zorbic"}) + "\n")
    events = [{"seq": 0, "ts": 1.0, "type": "birth", "monk": "m0001", "generation": 0},
              {"seq": 1, "ts": 2.0, "type": "turn", "monk": "m0001", "turn": 1},
              {"seq": 2, "ts": 3.0, "type": "birth", "monk": "m0002", "generation": 1}]
    for i in range(2):
        write_json(runs / "_baselines" / "anthropic__claude-haiku-5.5" / t0.id / f"{i}.json",
                   {"task": t0.id, "answer": f"plain answer {i}"})
    common = dict(kind="monk", species="haiku", model="anthropic/claude-haiku-5.5", task=t0.id,
                  question=t0.question)
    _rec(run, f"m0002/arrival/{t0.id}.json", monk="m0002", generation=1, when="arrival", ts=3.5,
         answer="zorbic and quaxel", **common)
    _rec(run, f"m0002/last-bell/{t0.id}.json", monk="m0002", generation=1, when="last-bell", ts=9.0,
         answer="babble babble zorbic", **common)
    _rec(run, f"egregore/tick-1/sol/{t0.id}.json", kind="egregore", tick=1, species="sol",
         model="openai/gpt-6.1-sol", task=t0.id, question=t0.question, answer="the fool speaks", ts=4.0)
    s = sc.Scorer(runs / "_cache", judge=FakeJudge(), embedder=fake_embed)
    summary = sc.score_run(run, runs, s, events=events, tasks=tasks)
    rows = [json.loads(l) for l in (run / "scores" / "catechism.jsonl").read_text().splitlines()]
    assert len(rows) == 3
    arr = next(r for r in rows if r.get("when") == "arrival")
    assert arr["rarity"]["inherited"] == {"n": 1, "mean": 0.4}      # zorbic: an earlier generation's word
    assert arr["rarity"]["novel"] == {"n": 1, "mean": 0.8}          # quaxel: never seen before
    assert "score" not in arr["rarity"] and "raw" not in json.dumps(arr)
    assert arr["emb_d"] is not None and arr["emb_d"] >= 0
    eg = next(r for r in rows if r["kind"] == "egregore")
    assert eg["emb_d"] is None                                     # no sol baseline yet
    m = summary["monks"]["haiku"]
    assert m["arrival"]["1"]["rarity_novel"] == 0.8 and m["arrival"]["1"]["rarity_inherited"] == 0.4
    assert "rarity" not in m["arrival"]["1"]
    assert summary["egregore"]["sol"]["1"]["coherence"] == 0.9
    assert summary["alarms"] == [{"species": "haiku", "kind": "monk", "at": 1, "when": "last-bell",
                                  "coherence": 0.2}]
    btd = summary["birth_to_death"]["haiku"]["m0002"]
    assert btd["tasks"] == 1 and btd["distance"] > 0
    assert (run / "scores" / "summary.json").exists()
    # lineage distance against itself is zero
    assert sc.lineage_distance(run, run, s)["haiku"][t0.id] == pytest.approx(0.0, abs=1e-12)


def test_coined_word_check(tmp_path):
    def judge(model, prompt):
        body = prompt.split("TEXT:")[1]
        w = body.split("calls ")[1].split()[0]
        ents = [] if w.startswith("v") else [{"name": w, "rarity": 1.0}]
        return json.dumps({"entities": ents})
    s = sc.Scorer(tmp_path, judge=judge, embedder=fake_embed)
    rows = sc.coined_word_check(s)
    assert len(rows) == 20
    assert next(r for r in rows if r["word"] == "velsorine")["extracted"] is False
    assert next(r for r in rows if r["word"] == "quillmet")["rarity"] == 1.0


def test_seq_as_of():
    ev = [{"seq": 0, "ts": 1.0}, {"seq": 1, "ts": 2.0}, {"seq": 2, "ts": 3.0}]
    assert sc.seq_as_of(ev, {"ts": 2.5}) == 1
    assert sc.seq_as_of(ev, {}) is None
