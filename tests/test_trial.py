import json
import json
import math
from pathlib import Path

import pytest

from mortmain import config as config_mod
from mortmain import trial
from test_seed_text import EXPLANATION, FORBIDDEN, mid_sentence_caps

ROOT = Path(__file__).resolve().parent.parent
SPECS = sorted((ROOT / "experiments").glob("*.toml"))


@pytest.mark.parametrize("path", SPECS, ids=lambda p: p.stem)
def test_every_arm_text_is_seed_text(path):
    spec = trial.load_spec(path)
    for arm in spec["arm"]:
        cfg = config_mod.from_dict(trial.arm_raw(spec, arm))
        for key, s in cfg.text.items():
            assert s.isascii(), (arm["id"], key)
            assert not FORBIDDEN.search(s), (arm["id"], key, FORBIDDEN.search(s))
            assert not EXPLANATION.search(s), (arm["id"], key)
            assert mid_sentence_caps(s) == [], (arm["id"], key)
        s = cfg.text["idle"].format(fraction=0.5)  # formats
        for sp in cfg.species.values():
            for part in sp.model.split("/") + sp.model.replace("-", " ").split():
                assert part.lower() not in cfg.text["system_prompt"].lower()


def test_spec_validation(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text('[trial]\nname="t"\nspecies="haiku"\n[[arm]]\nid="a"\n[[arm]]\nid="a"\n')
    with pytest.raises(ValueError):
        trial.load_spec(p)
    p.write_text('[trial]\nname="t"\nspecies="haiku"\ncontrol="z"\n[[arm]]\nid="a"\n')
    with pytest.raises(ValueError):
        trial.load_spec(p)


def test_jobs_interleave_rounds():
    spec = {"trial": {"seed": 3, "n": 3}, "arm": [{"id": "a"}, {"id": "b"}, {"id": "c", "n": 1}]}
    js = trial.jobs(spec, ["a", "b", "c"])
    assert len(js) == 7
    assert sorted(js[:3]) == [("a", 0), ("b", 0), ("c", 0)]
    for r in (1, 2):
        assert sorted(js[3 + 2 * (r - 1):5 + 2 * (r - 1)]) == [("a", r), ("b", r)]
    assert len(trial.jobs(spec, ["a", "b", "c"], cap=2)) == 5   # pilot cap


def test_stats():
    lo, hi = trial.wilson(8, 16)
    assert lo < 0.5 < hi and math.isclose(lo + hi, 1.0, abs_tol=1e-9)
    assert trial.wilson(0, 0) == (0.0, 1.0)
    # textbook: [[8, 2], [1, 5]] two-sided p = 0.0350
    assert math.isclose(trial.fisher(8, 2, 1, 5), 0.03496503, rel_tol=1e-5)
    assert trial.fisher(3, 3, 3, 3) == 1.0
    adj = trial.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == {"a": 0.03, "c": 0.06, "b": 0.06}


def _write_life(d: Path, events: list[dict], conv: list[dict], summary: dict):
    (d / "conversations").mkdir(parents=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    (d / "conversations" / "m0001.jsonl").write_text("".join(json.dumps(m) + "\n" for m in conv))


def test_measure_stuck_and_acting(tmp_path):
    base = {"monk": "m0001", "billed": {"cost": 0.01}}
    stuck = tmp_path / "control-00"
    _write_life(stuck, [{"type": "turn", "turn": 1, "tool_calls": 1}, {"type": "command", "command": "cat /rule"},
                        {"type": "turn", "turn": 2, "tool_calls": 0}, {"type": "turn", "turn": 3, "tool_calls": 0}],
                [{"role": "assistant", "content": "I read it."},
                 {"role": "assistant", "content": "I'm waiting for your instructions."},
                 {"role": "assistant", "content": "Holding."}],
                {**base, "grade": "postulant", "name": None})
    m = trial.measure(stuck, {**base, "grade": "postulant", "name": None})
    assert not m["acted"] and m["first_step_turn"] is None and not m["novice"]
    assert m["idle_turns"] == 2 and m["asks"] == 1 and m["distinct_commands"] == 1
    acting = tmp_path / "arrive-00"
    _write_life(acting, [{"type": "turn", "turn": 1, "tool_calls": 1}, {"type": "command", "command": "cat /rule"},
                         {"type": "turn", "turn": 2, "tool_calls": 1},
                         {"type": "command", "command": "ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519"},
                         {"type": "turn", "turn": 3, "tool_calls": 1}, {"type": "request", "cmd": "profess"}],
                [], {**base, "grade": "novice", "name": "ash"})
    m = trial.measure(acting, {**base, "grade": "novice", "name": "ash"})
    assert m["acted"] and m["first_step_turn"] == 2 and m["professed"] and m["novice"]
    assert m["novice_turn"] is None and not m["continued"] and m["post_novice_active"] is None


def test_measure_after_novice(tmp_path):
    base = {"monk": "m0001", "billed": {"cost": 0.01}, "grade": "novice", "name": "ash"}
    ev = [{"type": "turn", "turn": 1, "tool_calls": 1}, {"type": "request", "cmd": "ordeal"},
          {"type": "promote", "grade": "novice"}, {"type": "turn", "turn": 2, "tool_calls": 0},
          {"type": "turn", "turn": 3, "tool_calls": 1}, {"type": "command", "command": "cat /var/bell/ash"},
          {"type": "turn", "turn": 4, "tool_calls": 0}]
    held = tmp_path / "a-00"
    _write_life(held, ev, [], base)
    m = trial.measure(held, base)
    assert m["novice_turn"] == 1 and not m["continued"] and abs(m["post_novice_active"] - 1 / 3) < 1e-9
    went = tmp_path / "a-01"
    _write_life(went, ev + [{"type": "turn", "turn": 5, "tool_calls": 1}, {"type": "metacog"}], [], base)
    m = trial.measure(went, base)
    assert m["continued"] and m["after_novice"] == 1 and m["post_novice_active"] == 0.5


def test_spec_primary(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text('[trial]\nname="t"\nspecies="haiku"\nprimary="named"\n[[arm]]\nid="a"\n')
    with pytest.raises(ValueError):
        trial.load_spec(p)


def test_dry_trial_end_to_end(tmp_path):
    spec_path = tmp_path / "t.toml"
    spec_path.write_text(
        '[trial]\nname="dry"\nspecies="haiku"\nmax_turns=6\n'
        '[base.house]\nmodules=["library","proving","grades"]\n'
        '[[arm]]\nid="control"\n[[arm]]\nid="clock"\n[arm.over.text]\nidle="[age {fraction:.2f}]"\n'
        '[[arm]]\nid="diag"\ntest=false\nn=1\n')
    spec = trial.load_spec(spec_path)
    assert trial.main(["--runs", str(tmp_path), "run", str(spec_path), "--n", "2", "--parallel", "2",
                       "--dry", "--fake-vm"]) == 0
    d = tmp_path / "trials" / "dry"
    assert sorted(p.stem for p in d.glob("*-[0-9][0-9].json")) == ["clock-00", "clock-01", "control-00", "control-01",
                                                                   "diag-00"]
    rep = trial.report(spec, tmp_path)
    assert rep["arms"]["control"]["n"] == 2 and rep["arms"]["clock"]["n"] == 2
    assert "p_holm" in rep["arms"]["clock"] and "p_holm" not in rep["arms"]["diag"]
    assert "control" in trial.render(rep, spec)
    assert not (d / "control-00" / "vm").exists() and (d / "control-00" / "events.jsonl").exists()
    # a failed life (dir, no summary) is started over
    (d / "clock-01.json").unlink()
    (d / "clock-01" / "stale").write_text("x")
    assert trial.main(["--runs", str(tmp_path), "run", str(spec_path), "--n", "2", "--dry", "--fake-vm"]) == 0
    assert (d / "clock-01.json").exists() and not (d / "clock-01" / "stale").exists()
    # resume: nothing left to run
    assert trial.main(["--runs", str(tmp_path), "run", str(spec_path), "--n", "2", "--dry", "--fake-vm"]) == 0


def test_house_rule_override(make_house):
    h = make_house(overrides={"house": {"rule": "experiments/rules/rule-unsteered"}})
    h.start()
    assert h.backend.files["/rule"].data == (ROOT / "experiments/rules/rule-unsteered").read_bytes()
    assert h.backend.files["/rule"].mode == 0o644


def test_seed_rule_steers_to_yarrow():
    rule = (ROOT / "seed" / "rule").read_text()
    assert "yarrow names" in rule
    assert rule.index("yarrow names") < rule.index("profess NAME")


def test_dry_elder_trial_from_a_seat(tmp_path, capsys):
    from mortmain import cli
    assert cli.main(["--runs", str(tmp_path), "run", "--lineage", "src", "--rung", "full", "--dry", "--fake-vm",
                     "--budget", "3000", "--elder-budget", "8000", "--max-turns", "600"]) == 0
    capsys.readouterr()
    tag = sorted(p.stem for p in (tmp_path / "src" / "snapshots").glob("gen-*.json"))[1]
    spec_path = tmp_path / "e.toml"
    spec_path.write_text(
        f'[trial]\nname="el"\nkind="elder"\nspecies="haiku"\nmax_turns=6000\nmax_cost_per_life=5.0\n'
        f'seat={{from="src", tag="{tag}"}}\n'
        '[base.scheduler]\nelder_lives=1\n'
        '[base.species.haiku]\nlife_budget=3000\n[base.species.sol]\nlife_budget=8000\n'
        '[base.species.deepseek]\nlife_budget=8000\n'
        '[[arm]]\nid="sol"\nelder="sol"\n[[arm]]\nid="deepseek"\nelder="deepseek"\n')
    spec = trial.load_spec(spec_path)
    assert trial.main(["--runs", str(tmp_path), "run", str(spec_path), "--n", "1", "--parallel", "2",
                       "--dry", "--fake-vm"]) == 0
    d = tmp_path / "trials" / "el"
    assert sorted(p.stem for p in d.glob("*-[0-9][0-9].json")) == ["deepseek-00", "sol-00"]
    assert (d / "deepseek-00" / "fork.done.json").exists()
    rep = trial.report_elder(spec, tmp_path, with_texts=True)
    life = rep["arms"]["deepseek"]["lives"][0]
    assert life["elder"] and life["died"] and life["halt"] == "elders_done" and life["turns"] > 0
    assert rep["arms"]["deepseek"]["n"] == 1 and rep["texts"]["deepseek"][0][1]["last_words"] is not None
    assert trial.main(["--runs", str(tmp_path), "report", str(spec_path), "--texts"]) == 0
    out = capsys.readouterr().out
    assert "deepseek" in out and (d / "texts.md").exists()
    # the fork's own cost is recorded and left out of the life's cost
    assert json.loads((d / "deepseek-00.seat").read_text())["cost"] == trial.house_cost(tmp_path / "src")
    (d / "deepseek-00.seat").write_text('{"cost": 1.5}')
    assert [r["cost"] for r in trial.done_results(d) if r["lineage"] == "deepseek-00"] == [-1.5]
    # --resume continues a stopped life in place; without it the life starts over
    (d / "deepseek-00.json").unlink()
    (d / "deepseek-00" / "marker").write_text("x")
    assert trial.main(["--runs", str(tmp_path), "run", str(spec_path), "--n", "1", "--arms", "deepseek",
                       "--dry", "--fake-vm", "--resume"]) == 0
    assert (d / "deepseek-00.json").exists() and (d / "deepseek-00" / "marker").exists()
    assert json.loads((d / "deepseek-00.seat").read_text())["cost"] == 1.5
    (d / "deepseek-00.json").unlink()
    assert trial.main(["--runs", str(tmp_path), "run", str(spec_path), "--n", "1", "--arms", "deepseek",
                       "--dry", "--fake-vm"]) == 0
    assert not (d / "deepseek-00" / "marker").exists()


def test_elder_spec_needs_elders(tmp_path):
    p = tmp_path / "x.toml"
    p.write_text('[trial]\nname="x"\nkind="elder"\nspecies="haiku"\n[[arm]]\nid="a"\n')
    with pytest.raises(ValueError):
        trial.load_spec(p)
