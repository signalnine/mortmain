"""Reader surfaces and measurement, host side, out of band.

    python -m mortmain.report surfaces --lineage L [--work ID ...]
    python -m mortmain.report lexicon  --lineage L
    python -m mortmain.report score    --lineage L          (judge + embeddings: network)
    python -m mortmain.report baseline [--species haiku] [--n 5]   (provider: network)
    python -m mortmain.report coined                        (judge: network)
    python -m mortmain.report distance --lineage A --other B (embeddings: network)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config as config_mod
from .config import ROOT


def _runs(args) -> Path:
    return Path(args.runs) if args.runs else ROOT / "runs"


def _scoring_settings(cfg) -> dict:
    from .scoring import DEFAULTS
    s = dict(DEFAULTS)
    s.update(cfg.section("scoring"))
    return s


def cmd_surfaces(args) -> int:
    from .surfaces import render_all
    out = render_all(_runs(args) / args.lineage, work_ids=args.work or ())
    print(f"{len(out)} files in {out[0].parent if out else '-'}")
    return 0


def cmd_lexicon(args) -> int:
    from .lexicon import Lexicon
    run = _runs(args) / args.lineage
    lx = Lexicon.build(run)
    lx.save(run / "lexicon.json")
    d = lx.to_json()
    print(json.dumps({"terms": len(d["terms"]), "new_terms_by_generation": d["new_terms_by_generation"]}, indent=1))
    return 0


def cmd_score(args) -> int:
    from .scoring import Scorer, score_run
    cfg = config_mod.load(args.config)
    s = _scoring_settings(cfg)
    scorer = Scorer.from_config(cfg, _runs(args))
    summary = score_run(_runs(args) / args.lineage, _runs(args), scorer, coherence_alarm=float(s["coherence_alarm"]))
    print(json.dumps(summary, indent=1))
    return 0


def cmd_baseline(args) -> int:
    from .catechism import baseline
    from .providers import make_provider
    cfg = config_mod.load(args.config)
    n = args.n or int(cfg.section("catechism").get("baseline_n", 5))
    res = baseline(cfg, make_provider(cfg), _runs(args), species=args.species or None, n=n,
                   workers=int(cfg.section("catechism").get("workers", 5)),
                   log=lambda s: print(s, file=sys.stderr))
    print(json.dumps(res, indent=1))
    return 0


def cmd_coined(args) -> int:
    from .scoring import Scorer, coined_word_check
    cfg = config_mod.load(args.config)
    scorer = Scorer.from_config(cfg, _runs(args))
    rows = coined_word_check(scorer)
    for r in rows:
        print(f"{r['word']:<14} {'rated ' + format(r['rarity'], '.2f') if r['extracted'] else 'dropped':<12} "
              f"{json.dumps(r['entities'])}")
    rated = [r["rarity"] for r in rows if r["extracted"]]
    print(f"judge {scorer.judge_model}: {len(rated)}/{len(rows)} extracted"
          + (f", mean rarity {sum(rated) / len(rated):.3f}" if rated else ""))
    return 0


def cmd_distance(args) -> int:
    from .scoring import Scorer, lineage_distance
    cfg = config_mod.load(args.config)
    scorer = Scorer.from_config(cfg, _runs(args))
    print(json.dumps(lineage_distance(_runs(args) / args.lineage, _runs(args) / args.other, scorer), indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mortmain.report")
    p.add_argument("--runs", help="runs root (default: ./runs)")
    p.add_argument("--config", help="run.toml path")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("surfaces", help="render reader surfaces to runs/<lineage>/surfaces/")
    s.add_argument("--lineage", required=True)
    s.add_argument("--work", action="append", help="work id for a history page (default: every work)")
    s.set_defaults(fn=cmd_surfaces)
    s = sub.add_parser("lexicon", help="build runs/<lineage>/lexicon.json")
    s.add_argument("--lineage", required=True)
    s.set_defaults(fn=cmd_lexicon)
    s = sub.add_parser("score", help="score catechism answers (network)")
    s.add_argument("--lineage", required=True)
    s.set_defaults(fn=cmd_score)
    s = sub.add_parser("baseline", help="unconditioned answers per species (network)")
    s.add_argument("--species", action="append")
    s.add_argument("--n", type=int)
    s.set_defaults(fn=cmd_baseline)
    s = sub.add_parser("coined", help="20 coined words through the rarity judge (network)")
    s.set_defaults(fn=cmd_coined)
    s = sub.add_parser("distance", help="embedding distance between two lineages (network)")
    s.add_argument("--lineage", required=True)
    s.add_argument("--other", required=True)
    s.set_defaults(fn=cmd_distance)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
