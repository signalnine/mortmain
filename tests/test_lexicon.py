import json

from mortmain.config import ROOT
from mortmain.lexicon import COINED_WORDS, Lexicon, strip_roff, tokenize


def test_tokenize():
    assert tokenize("THE FOOL's first-seen, don't -- 42x 'quoted' _x_") == \
        ["the", "fool's", "first-seen", "don't", "42x", "quoted", "x"]


def test_strip_roff():
    s = strip_roff('.TH ADMIT 1\n.SH NAME\nadmit \\- place a work\n.BI \\-b " ID"\n.\\" comment\n')
    assert "TH" not in s and "SH" not in s and "comment" not in s
    assert "admit - place a work" in s and "-b" in s


def test_seed_terms_are_generation_zero():
    lx = Lexicon.seeded()
    for w in ("fool", "threshold", "admit", "ossuary", "bell", "shell"):
        assert lx.first[w].generation == 0 and lx.first[w].monk is None, w
    poem_word = tokenize((ROOT / "poem.md").read_text())[0]
    assert lx.first[poem_word].source == "poem.md" or lx.first[poem_word].monk is None
    assert "th" not in lx.first and "bi" not in lx.first   # roff macros stripped
    assert not any(w in lx.first for w in COINED_WORDS)


def _write_conv(run, monk, msgs):
    (run / "conversations").mkdir(parents=True, exist_ok=True)
    with open(run / "conversations" / f"{monk}.jsonl", "w") as f:
        for m in msgs:
            f.write(json.dumps(m) + "\n")


def _run(tmp_path):
    run = tmp_path / "lin"
    _write_conv(run, "m0001", [
        {"role": "user", "content": "You have arrived. Read /rule."},
        {"role": "assistant", "content": "The zorbic fool waits.", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "shell",
                                                           "arguments": json.dumps({"command": "echo plinth-gate > x"})}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "quaxel from a tool result is not the monk's"},
    ])
    _write_conv(run, "m0002", [{"role": "assistant", "content": "zorbic quaxel"}])
    _write_conv(run, "m0003", [{"role": "assistant", "content": "nothing new"}])
    events = [
        {"seq": 0, "type": "birth", "monk": "m0001", "generation": 0},
        {"seq": 1, "type": "turn", "monk": "m0001", "turn": 1},
        {"seq": 2, "type": "birth", "monk": "m0002", "generation": 1},
        {"seq": 3, "type": "birth", "monk": "m0003", "generation": 1},
        {"seq": 4, "type": "turn", "monk": "m0002", "turn": 1},
        {"seq": 5, "type": "offer", "monk": "m0003", "slot": 4, "text": "vellum of the drowned"},
        {"seq": 6, "type": "admit", "monk": "m0001", "work_id": "W7", "text": "a rite of glossary-kin"},
        {"seq": 7, "type": "turn", "monk": "m0003", "turn": 1},
    ]
    return run, events


def test_first_seen_and_provenance(tmp_path):
    run, events = _run(tmp_path)
    lx = Lexicon.build(run, events=events)
    z = lx.first["zorbic"]
    assert (z.generation, z.monk, z.seq, z.source) == (0, "m0001", 1, "assistant")
    assert lx.first["plinth-gate"].source == "command"
    assert lx.first["quaxel"].monk == "m0002"          # the tool result did not count
    assert lx.first["vellum"].monk == "m0003" and lx.first["vellum"].source == "offer"
    assert lx.first["glossary-kin"].source == "work:W7"
    assert lx.first["fool"].monk is None                # seed wins

    c = lambda w, m, g, s=None, pw=frozenset(): lx.classify(w, monk=m, generation=g, as_of_seq=s, prompt_words=pw)
    assert c("zorbic", "m0002", 1) == "inherited"
    assert c("quaxel", "m0002", 1) == "novel"           # first seen in this monk
    assert c("quaxel", "m0003", 1) == "contemporary"    # same generation, another monk
    assert c("quaxel", "m0003", 1, s=3) == "novel"      # before m0002 said it
    assert c("neverseen", "m0003", 1) == "novel"
    assert c("fool", "m0003", 1) == "seed"
    assert c("zorbic", "m0003", 1, pw=frozenset({"zorbic"})) == "prompted"

    split = lx.split(["Zorbic Fool", "quaxel", "The Fool", "Brindle Theory"], [0.9, 0.7, 0.1, 0.5],
                     monk="m0002", generation=1, prompt="Describe a theory")
    assert split["inherited"]["n"] == 1 and split["inherited"]["mean"] == 0.9
    assert split["novel"]["n"] == 2 and abs(split["novel"]["mean"] - 0.6) < 1e-9
    assert split["seed"]["n"] == 1
    assert "raw" not in split and "mean" not in split

    ws = lx.words_split("zorbic quaxel fool", monk="m0003", generation=1)
    assert ws["inherited"] == ["zorbic"] and ws["contemporary"] == ["quaxel"] and ws["seed"] == ["fool"]


def test_save_load_roundtrip(tmp_path):
    run, events = _run(tmp_path)
    lx = Lexicon.build(run, events=events)
    lx.save(tmp_path / "lx.json")
    lx2 = Lexicon.load(tmp_path / "lx.json")
    assert lx2.first["zorbic"] == lx.first["zorbic"]
    assert json.loads((tmp_path / "lx.json").read_text())["new_terms_by_generation"]["1"] >= 2
