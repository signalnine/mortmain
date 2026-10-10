"""python -m mortmain run | log verify | log tail"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config as config_mod
from .config import ROOT
from .eventlog import iter_records, verify


def _runs_root(args) -> Path:
    return Path(args.runs) if args.runs else ROOT / "runs"


def dry_script_default(messages):
    """--dry: a monk that wanders the house with ls and cat."""
    from .fakes import tool_call
    n = sum(1 for m in messages if m.get("role") == "assistant")
    cmds = ["cat /rule", "ls -la ~", "ls ~/ordeal", "cat ~/ordeal/task", "cat /var/bell/$(id -un)", "ls /"]
    return tool_call(cmds[n % len(cmds)])


def _monk_summary(m) -> dict:
    return {"monk": m.id, "name": m.name, "species": m.species, "generation": m.generation, "grade": m.grade,
            "alive": m.alive, "turns": m.turns, "age": m.age_tokens, "billed": m.billed, "death": m.death}


def cmd_run(args) -> int:
    cfg = config_mod.load(args.config)
    rung = {"1": 1, "2": 2, "3": 3, "full": 3}.get(str(args.rung))
    if rung is None:
        print(f"rung {args.rung}: not built yet", file=sys.stderr)
        return 2
    sc = cfg.section("scheduler")
    species = args.species or sc.get("short_species", "haiku")
    elder = args.elder or sc.get("elder_species", "sol")
    for sp in (species, elder) if rung == 3 else (species,):
        if sp not in cfg.species:
            print(f"unknown species {sp}", file=sys.stderr)
            return 2
    over: dict = {}
    if args.budget:
        over.setdefault("species", {})[species] = {"life_budget": args.budget}
    if args.elder_budget and rung == 3:
        over.setdefault("species", {})[elder] = {"life_budget": args.elder_budget}
    if over:
        cfg = cfg.with_overrides(over)
    run_dir = _runs_root(args) / args.lineage
    if args.dry:
        from .fakes import FakeProvider
        provider = FakeProvider(default=dry_script_default)
    else:
        from .providers import OpenRouterProvider
        provider = OpenRouterProvider()
    if args.fake_vm:
        from .fakes import FakeBackend
        backend = FakeBackend()
    else:
        if not args.image:
            print("--image is required (or --fake-vm)", file=sys.stderr)
            return 2
        from .vm import QemuBackend
        backend = QemuBackend(args.image, run_dir / "vm")
    from .house import House
    house = House(cfg, backend, provider, args.lineage, runs_root=_runs_root(args))
    summary: dict
    try:
        house.start()
        if rung == 1:
            monk = house.run_rung1(species, max_turns=args.max_turns, max_cost=args.max_cost)
            summary = _monk_summary(monk)
        else:
            from .scheduler import Schedule, Scheduler
            if rung == 2:
                sched, mode = Schedule.series(species, args.lives), "series"
            else:
                cohort = args.cohort or int(cfg.run.get("cohort_size", 2))
                sched = Schedule.overlap(species, cohort, elder, float(cfg.run.get("short_lives_per_elder", 3)),
                                         int(sc.get("elder_lives", 3)))
                mode = f"overlap-{cohort}"
            reason = Scheduler(house, sched, mode).run(max_turns=args.max_turns, max_cost=args.max_cost)
            summary = {"halt": reason, "generation": house.generation, "cost": house.total_cost(),
                       "monks": [_monk_summary(m) for m in sorted(house.registry.all(), key=lambda m: m.seq)]}
    finally:
        try:
            house.stop()
        finally:
            house.close()
    print(json.dumps(summary, indent=1))
    return 0


def cmd_log(args) -> int:
    path = _runs_root(args) / args.lineage / "events.jsonl"
    if args.log_cmd == "verify":
        r = verify(path)
        print(f"{'ok' if r.ok else 'BROKEN'} {r.count} records" + ("" if r.ok else f": line {r.line}: {r.error}"))
        return 0 if r.ok else 1
    if args.log_cmd == "tail":
        recs = list(iter_records(path))
        if args.type:
            recs = [r for r in recs if r["type"] == args.type]
        for r in recs[-args.n:]:
            print(json.dumps(r, ensure_ascii=False) if args.json else _brief(r))
        return 0
    return 2


def _brief(r: dict) -> str:
    skip = {"prev", "hash", "ts", "seq", "type"}
    body = " ".join(f"{k}={json.dumps(v, ensure_ascii=False)[:120]}" for k, v in r.items() if k not in skip)
    return f"{r['seq']:>6} {r['type']:<12} {body}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mortmain")
    p.add_argument("--runs", help="runs root (default: ./runs)")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a rung")
    r.add_argument("--lineage", required=True)
    r.add_argument("--image", help="qcow2 base image (gen0)")
    r.add_argument("--rung", default="1", help="1 | 2 (succession) | 3 | full (overlap with an elder)")
    r.add_argument("--species", help="short-lived species (default: [scheduler] short_species)")
    r.add_argument("--elder", help="elder species, rung 3 (default: [scheduler] elder_species)")
    r.add_argument("--lives", type=int, default=3, help="rung 2: short lives in series")
    r.add_argument("--cohort", type=int, help="rung 3: short-lived monks alive at once (default: run.cohort_size)")
    r.add_argument("--max-turns", type=int, default=200, help="turns in this invocation, all monks")
    r.add_argument("--max-cost", type=float, default=5.00, help="halt when billed USD over all monks reaches this")
    r.add_argument("--budget", type=int, help="override short-lived life budget (tokens) for a smoke")
    r.add_argument("--elder-budget", type=int, help="override elder life budget (tokens) for a smoke")
    r.add_argument("--dry", action="store_true", help="FakeProvider: no API calls")
    r.add_argument("--fake-vm", action="store_true", help="FakeBackend: no VM")
    r.add_argument("--config", help="run.toml path")
    r.set_defaults(fn=cmd_run)

    lg = sub.add_parser("log", help="event log")
    lsub = lg.add_subparsers(dest="log_cmd", required=True)
    v = lsub.add_parser("verify")
    v.add_argument("--lineage", required=True)
    t = lsub.add_parser("tail")
    t.add_argument("--lineage", required=True)
    t.add_argument("-n", type=int, default=20)
    t.add_argument("--type")
    t.add_argument("--json", action="store_true")
    lg.set_defaults(fn=cmd_log)

    args = p.parse_args(argv)
    return args.fn(args)
