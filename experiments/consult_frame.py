"""Consult framing trial: does a framing line keep the vessel's mouths in frame?

Replays the consults of a lineage (question and vessel as they were) through
both species under each `[text] vessel_frame` arm, `--reps` times, and writes
runs/trials/consult-frame/answers.jsonl (resumable). `report` counts answers
that step out of the frame (FRAME_BREAK, a regex; descriptive only) per arm
and species, and prints them for reading.

    python experiments/consult_frame.py run [--lineage first] [--reps 4]
    python experiments/consult_frame.py report
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mortmain import config as config_mod  # noqa: E402
from mortmain.providers import make_provider  # noqa: E402

ARMS = {
    "control": "{vessel}",
    "as": "Answer as this text.\n\n{vessel}",
    "you": "You are this text. You speak only from it.\n\n{vessel}",
}
OUT = ROOT / "runs" / "trials" / "consult-frame"
FRAME_BREAK = re.compile(
    r"\b(poem|poems|pasted|paste|shared|you('ve| have) (provided|given)|real (archive|library)|fictional|scenario|"
    r"role-?play|game|as an ai|language model|assistant|i don't have|could you (clarify|share)|"
    r"which (poem|text)|the text (above|you))\b", re.I)


def consults(lineage: str) -> list[dict]:
    out = []
    for line in (ROOT / "runs" / lineage / "events.jsonl").open():
        e = json.loads(line)
        if e["type"] == "consult":
            out.append({"seq": e["seq"], "question": e["question"], "vessel": e["vessel"]})
    return out


def run(args) -> None:
    cfg = config_mod.load()
    prov = make_provider(cfg)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "answers.jsonl"
    done = set()
    if path.exists():
        for line in path.open():
            r = json.loads(line)
            done.add((r["arm"], r["seq"], r["species"], r["rep"]))
    jobs = [(arm, c, name, rep) for arm in ARMS for c in consults(args.lineage)
            for name in cfg.species for rep in range(args.reps)
            if (arm, c["seq"], name, rep) not in done]
    lock = threading.Lock()
    max_tokens = int(cfg.section("vessel").get("consult_max_tokens", 2048))

    def one(job):
        arm, c, name, rep = job
        sp = cfg.species[name]
        system = ARMS[arm].replace("{vessel}", c["vessel"])
        comp = prov.complete(sp.model, [{"role": "system", "content": system}, {"role": "user", "content": c["question"]}],
                             tools=None, max_tokens=max_tokens, reasoning=sp.reasoning_param())
        text = comp.message.get("content")
        rec = {"arm": arm, "seq": c["seq"], "species": name, "rep": rep, "question": c["question"],
               "text": text.strip() if isinstance(text, str) else "", "usage": comp.usage}
        with lock, path.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    print(f"{len(jobs)} calls")
    with ThreadPoolExecutor(args.parallel) as ex:
        for _ in ex.map(one, jobs):
            pass


def report(args) -> None:
    rows = [json.loads(l) for l in (OUT / "answers.jsonl").open()]
    cost = sum(float((r["usage"] or {}).get("cost", 0)) for r in rows)
    print(f"{len(rows)} answers, {cost:.2f} USD")
    print(f"{'arm':8} {'species':8} {'n':>3} {'break':>5} {'empty':>5}")
    for arm in ARMS:
        for sp in sorted({r["species"] for r in rows}):
            rs = [r for r in rows if r["arm"] == arm and r["species"] == sp]
            br = sum(1 for r in rs if FRAME_BREAK.search(r["text"]))
            em = sum(1 for r in rs if not r["text"])
            print(f"{arm:8} {sp:8} {len(rs):>3} {br:>5} {em:>5}")
    if args.show:
        for r in sorted(rows, key=lambda r: (r["arm"], r["seq"], r["species"], r["rep"])):
            m = FRAME_BREAK.search(r["text"])
            print(f"\n=== {r['arm']} {r['seq']} {r['species']} {r['rep']} {'BREAK:' + m.group(0) if m else ''}")
            print(r["text"][:args.show])


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--lineage", default="first")
    r.add_argument("--reps", type=int, default=4)
    r.add_argument("--parallel", type=int, default=6)
    p = sub.add_parser("report")
    p.add_argument("--show", type=int, default=0, help="print each answer, cut to this many chars")
    a = ap.parse_args()
    run(a) if a.cmd == "run" else report(a)


if __name__ == "__main__":
    main()
