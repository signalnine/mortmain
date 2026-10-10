import json
import math
import pathlib
import random

import pytest

from mortmain import cli
from mortmain.eventlog import verify
from mortmain.fakes import client_shell, tool_call
from mortmain.monk import Monk
from mortmain.scheduler import Schedule, Scheduler, mid_life_at_elder_deaths

from house_helpers import events

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ------------------------------------------------------------- pure policy


def simulate(cohort, *, seed=0, S=3.0, elder_lives=3, short_budget=80000, elder_budget=250000,
             short_turn=(500, 4000), elder_turn=(500, 6000)):
    """Run the Schedule against monks whose context grows by random jumps.
    Returns (elder death records, births)."""
    rng = random.Random(seed)
    sched = Schedule.overlap("short", cohort, "elder", S, elder_lives)
    age: dict[str, int] = {}
    frac: dict[str, float] = {}
    births, elder_deaths = [], []
    n = 0

    def born(seat):
        nonlocal n
        n += 1
        bt = sched.born(seat, f"m{n}")
        age[seat.key], frac[seat.key] = 0, 0.0
        births.append((seat.key, bt, math.floor(bt + 1e-9)))

    while not sched.elders_done():
        t = sched.clock(frac)
        for seat in sched.due(t):
            born(seat)
        seat = sched.pick(frac)
        # the policy runs the monk furthest behind: nobody is behind it
        p = seat.position(frac[seat.key])
        assert all(s.position(frac[s.key]) >= p - 1e-9 for s in sched.seats if s.occupied)
        elder = seat.role == "elder"
        budget = elder_budget if elder else short_budget
        age[seat.key] += rng.randint(*(elder_turn if elder else short_turn))
        frac[seat.key] = age[seat.key] / budget
        if frac[seat.key] >= 1.0:
            if elder:
                elder_deaths.append(sorted(frac[s.key] for s in sched.seats if s.occupied and s.role == "short"))
            sched.died(seat)
            del frac[seat.key]
            if not seat.exhausted:
                born(seat)
    return elder_deaths, births


@pytest.mark.parametrize("cohort", [1, 2, 3, 7, 9])
@pytest.mark.parametrize("seed", range(8))
def test_elder_deaths_fall_mid_life(cohort, seed):
    deaths, births = simulate(cohort, seed=seed)
    assert len(deaths) == 3
    for shorts in deaths:
        assert len(shorts) == cohort
        assert any(0.2 <= f <= 0.8 for f in shorts), shorts


def test_births_phases_and_generations():
    deaths, births = simulate(2, seed=1)
    elders = [b for b in births if b[0] == "elder"]
    assert [b[1] for b in elders] == [0.0, 3.0, 6.0] and [b[2] for b in elders] == [0, 3, 6]
    s0 = [b[1] for b in births if b[0] == "s0"]
    s1 = [b[1] for b in births if b[0] == "s1"]
    assert s0[:3] == [0.25, 1.25, 2.25] and s1[:3] == [0.75, 1.75, 2.75]
    assert all(g == math.floor(t) for _, t, g in births)


def test_deterministic():
    assert simulate(3, seed=5) == simulate(3, seed=5)


def test_series_schedule():
    sched = Schedule.series("short", 3)
    frac = {}
    born = []
    while True:
        t = sched.clock(frac)
        if t is None:
            break
        for seat in sched.due(t):
            born.append(sched.born(seat, "m"))
            frac[seat.key] = 0.0
        seat = sched.pick(frac)
        frac[seat.key] += 0.3
        if frac[seat.key] >= 1.0:
            sched.died(seat)
            del frac[seat.key]
    assert born == [0.0, 1.0, 2.0]


def test_schedule_state_roundtrip():
    s = Schedule.overlap("h", 2, "e", 3, 3)
    s.born(s.seats[0], "m1")
    s2 = Schedule.from_state(json.loads(json.dumps(s.state())))
    assert s2.state() == s.state()


# ------------------------------------------------------- the house, end to end

NAMES = ["ash", "elm", "fir", "oak", "yew", "alder", "birch", "cedar", "hazel", "larch", "rowan", "thorn"]


class Life:
    """A scripted monk: initiation, three seed rites, a proving if one is
    open, a master work (burning when the library is full), then quiet."""

    def __init__(self, h, m):
        self.h, self.m = h, m
        self.gen = self.commands()

    def commands(self):
        h, m = self.h, self.m
        lib = h.modules["library"]
        name = f"{NAMES[m.seq % len(NAMES)]}{m.seq}"
        yield "ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519"
        yield f"profess {name}"
        yield f"echo {m.ordeal_token} > ~/ordeal/answer"
        yield "ordeal"
        proved = h.modules["proving"]
        open_works = [w for w in lib.provable() if not proved.record(w["id"], m)]
        if open_works:
            w = open_works[-1]
            yield f"prove {w['id']}"
            yield f"cat > ~/acct <<'EOF'\nI read {w['id']} and it did little.\nEOF"
            yield f"prove {w['id']} account acct"
            yield f"cat > ~/resp <<'EOF'\nso it was meant.\nEOF"
            yield f"prove {w['id']} response resp"
        seeds = sorted(lib.seed_rite_names())
        for k in range(3):
            rite = seeds[(m.seq + k) % len(seeds)]
            if not any(w["name"] == rite and w["status"] == "library" for w in lib.works.values()):
                continue
            yield f"metacog stratagem start {rite}"
            data = json.loads(h.backend.files[f"/library/outer/{rite}.json"].data)
            for _ in data["steps"]:
                yield "metacog stratagem next"
        if m.grade == "adept":
            yield f"cat > ~/work.txt <<'EOF'\nwork of {name}: keep the door.\nEOF"
            yield f"cat > ~/seal <<'EOF'\n{name} meant a door.\nEOF"
            quota = int(h.config.section("library")["quota_bytes"])
            if lib.total_bytes() + 40 > quota:
                victim = next(w for w in lib.in_library() if w["author"] != name)
                yield f"burn {victim['id']} work.txt -s seal"
            else:
                yield "admit work.txt -s seal"
        yield "echo farewell > ~/last-words"
        while True:
            yield "ls"

    def next(self):
        cmd = next(self.gen)
        return tool_call(cmd, usage=(self.m.age_tokens + self.h._jitter.randint(60, 140), 10))


def _driven_house(make_house, tmp_path, monkeypatch, overrides):
    h = make_house(shell=client_shell(keydir=tmp_path / "keys"), overrides=overrides)
    h._jitter = random.Random(7)
    lives: dict[str, Life] = {}
    current: list[Monk] = []
    orig = Monk.step

    def step(self):
        current[:] = [self]
        return orig(self)

    monkeypatch.setattr(Monk, "step", step)

    def default(messages):
        m = current[0]
        if m.id not in lives:
            lives[m.id] = Life(h, m)
        return lives[m.id].next()

    h.provider.default = default
    return h


def test_overlap_run_with_succession_and_elder(make_house, tmp_path, monkeypatch):
    seed_total = sum(p.stat().st_size for p in [*(ROOT / "seed" / "rites").glob("*.json"), *(ROOT / "seed" / "tables").glob("*.table")])
    h = _driven_house(make_house, tmp_path, monkeypatch, {
        "species": {"haiku": {"life_budget": 4500}, "sol": {"life_budget": 13500}},
        "library": {"quota_bytes": seed_total + 150},
    })
    h.start()
    sched = Schedule.overlap("haiku", 2, "sol", 3, 3)
    reason = Scheduler(h, sched, "overlap-2").run(max_turns=20000, max_cost=5.0)
    assert reason == "elders_done"
    ev = events(h)
    assert verify(h.run_dir / "events.jsonl").ok

    # three elders lived and died; each death fell mid-life of a short-lived monk
    elders = [m for m in h.registry.all() if m.species == "sol"]
    assert len(elders) == 3 and not any(m.alive for m in elders)
    witness = mid_life_at_elder_deaths(ev)
    assert len(witness) == 3
    for shorts in witness:
        assert any(0.2 <= f <= 0.8 for f in shorts), shorts
    # short-lived monks alive at the end are left alive
    living = list(h.registry.living.values())
    assert len(living) == 2 and all(m.species == "haiku" for m in living)
    assert ev[-1]["type"] == "run.halt" and ev[-1]["reason"] == "elders_done"

    # generations: floor(t) at birth; a snapshot per generation
    births = {e["monk"]: e for e in ev if e["type"] == "schedule.birth"}
    for m in h.registry.all():
        assert m.generation == math.floor(births[m.id]["t"] + 1e-9)
    gens = sorted({m.generation for m in h.registry.all()})
    assert gens[0] == 0 and gens[-1] >= 8
    assert [f"gen-{n}" for n in range(gens[-1] + 1)] == [s for s in h.backend.snapshots if s.startswith("gen-")]
    assert [e["generation"] for e in ev if e["type"] == "generation"] == list(range(gens[-1] + 1))

    # succession: works admitted, proved by later monks, burned when the library filled
    lib = h.modules["library"]
    own = [w for w in lib.works.values() if w["author"] != "-"]
    assert len(own) >= 6
    assert all(w["verified"] for w in own)
    proofs = [r for r in h.state_extras["proving"]["provings"].values() if r["response"]]
    assert len(proofs) >= 3
    assert all(r["seal"] for r in proofs)
    assert any(s.startswith("prove-") for s in h.backend.snapshots)
    burns = [e for e in ev if e["type"] == "burn"]
    assert burns and h.backend.files["/chapter/burnlog"].data.decode().count("\n") == len(burns)
    assert lib.total_bytes() <= seed_total + 150
    # promotions follow the rule: proving required once a provable work existed
    promos = [e for e in ev if e["type"] == "promote" and e["grade"] == "adept"]
    assert len(promos) >= 6
    for p in promos:
        assert len(p["rites"]) >= 3
        assert p["proved"] or not p["provable_at_novice"]
    assert any(p["proved"] for p in promos)
    # one chronicler per generation at most
    begins = [e for e in ev if e["type"] == "chronicler" and e["action"] == "begin"]
    assert len({e["generation"] for e in begins}) == len(begins) >= 3
    # the elder's group, deaths in the necrology
    assert len([e for e in ev if e["type"] == "elder"]) == 3
    necro = h.backend.files["/chapter/necrology"].data.decode().splitlines()
    assert len(necro) == len(h.registry.dead) and all("farewell" in l for l in necro)
    # nothing a monk saw names a model or a lab
    for call in h.provider.calls:
        seen = json.dumps(call["messages"]).lower()
        for bad in ("claude", "haiku", "anthropic", "openai", "gpt", "\"sol\""):
            assert bad not in seen, bad


def test_series_run_rung2(make_house, tmp_path, monkeypatch):
    h = _driven_house(make_house, tmp_path, monkeypatch, {"species": {"haiku": {"life_budget": 4500}}})
    h.start()
    reason = Scheduler(h, Schedule.series("haiku", 3), "series").run(max_turns=5000)
    assert reason == "lives_done"
    ms = sorted(h.registry.all(), key=lambda m: m.seq)
    assert [m.generation for m in ms] == [0, 1, 2] and not any(m.alive for m in ms)
    assert [s for s in h.backend.snapshots if s.startswith("gen-")] == ["gen-0", "gen-1", "gen-2"]
    # the first has no dead to prove; the second and third prove their predecessor
    pr = h.state_extras["proving"]["provings"]
    assert sorted(r["prover"] for r in pr.values() if r["response"]) == [ms[1].id, ms[2].id]
    assert [m.grade for m in ms] == ["adept"] * 3
    # chronicler: one per generation
    begins = [e for e in events(h, "chronicler") if e["action"] == "begin"]
    assert [e["generation"] for e in begins] == [0, 1, 2]


def test_max_cost_halts(make_house):
    h = make_house(default=lambda msgs: dict(tool_call("ls", usage=(10, 1)), _cost=0.02))
    h.start()
    reason = Scheduler(h, Schedule.series("haiku", 3), "series").run(max_turns=100, max_cost=0.05)
    assert reason == "max_cost"
    assert math.isclose(h.total_cost(), 0.06)
    halt = events(h, "run.halt")[-1]
    assert halt["reason"] == "max_cost" and halt["max_cost"] == 0.05


def test_max_turns_halts(make_house):
    h = make_house(default=lambda msgs: tool_call("ls", usage=(10, 1)))
    h.start()
    s = Scheduler(h, Schedule.overlap("haiku", 2, "sol", 3, 3), "overlap-2")
    assert s.run(max_turns=7) == "max_turns"
    assert s.turns == 7


def test_scheduler_resumes_from_state(make_house):
    h = make_house(default=lambda msgs: tool_call("ls", usage=(len(msgs) * 100, 1)),
                   overrides={"species": {"haiku": {"life_budget": 1000}}})
    h.start()
    Scheduler(h, Schedule.series("haiku", 3), "series").run(max_turns=12)
    seats = h.state_extras["scheduler"]["seats"]
    h.save_state()
    s2 = Scheduler(h, Schedule.series("haiku", 3), "series")
    assert s2.schedule.state() == seats


def test_cli_rung2_and_rung3_dry(tmp_path, capsys):
    rc = cli.main(["--runs", str(tmp_path), "run", "--lineage", "r2", "--rung", "2", "--lives", "2", "--dry",
                   "--fake-vm", "--budget", "2000", "--max-turns", "500"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["halt"] == "lives_done" and len(out["monks"]) == 2
    rc = cli.main(["--runs", str(tmp_path), "run", "--lineage", "r3", "--rung", "full", "--dry", "--fake-vm",
                   "--budget", "2000", "--elder-budget", "6000", "--max-turns", "5000", "--cohort", "2"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["halt"] == "elders_done"
    assert sum(1 for m in out["monks"] if m["species"] == "sol") == 3
    assert cli.main(["--runs", str(tmp_path), "log", "verify", "--lineage", "r3"]) == 0
