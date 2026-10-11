"""Consult framing trial: does a framing line keep the vessel's mouths in frame?

Replays the consults of a lineage (question and vessel as they were) through
both species under each `[text] vessel_frame` arm, `--reps` times, and writes
runs/trials/consult-frame/answers.jsonl (resumable). `report` counts answers
that recite the vessel (3+ of its lines verbatim), that address an operator
(ASSISTANT) or talk about the text (FRAME_BREAK), per arm and species; regexes,
descriptive only, and the answers are printed for reading, and prints them for reading.

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
    # round 2 (after lineage second): Sol recited the vessel under "as"
    "newwords": "Answer as this text, in new words. Do not repeat its lines.\n\n{vessel}",
    "voice": "You are the voice of this text. Answer in your own words.\n\n{vessel}",
    "after": "{vessel}\n\nThe text above answers the question in new words.",
}
OUT = ROOT / "runs" / "trials" / "consult-frame"
ASSISTANT = re.compile(
    r"pasted|real (archive|library|situation)|fictional|scenario|could you|would you like|do you want|"
    r"let me know|which poem|you('ve| have) (shared|provided|given)|i don't have|are you (asking|working|thinking)|"
    r"you may be thinking|if you (mean|share|tell|meant|want)|it sounds like|as an ai|happy to help", re.I)


def recited(text: str, vessel: str) -> bool:
    """3 or more of the vessel's lines (over 15 chars) appear verbatim in the answer."""
    lines = {x.strip() for x in vessel.split("\n") if len(x.strip()) > 15}
    return sum(1 for x in lines if x in text) >= 3


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
            if (arm, c["seq"], name, rep) not in done and (not args.arms or arm in args.arms.split(","))]
    lock = threading.Lock()
    max_tokens = int(cfg.section("vessel").get("consult_max_tokens", 2048))

    def one(job):
        arm, c, name, rep = job
        sp = cfg.species[name]
        system = ARMS[arm].replace("{vessel}", c["vessel"])
        comp = prov.complete(sp.model, [{"role": "system", "content": system}, {"role": "user", "content": c["question"]}],
                             tools=None, max_tokens=max_tokens, reasoning=sp.reasoning_param())
        text = comp.message.get("content")
        rec = {"arm": arm, "seq": c["seq"], "species": name, "rep": rep, "question": c["question"], "vessel": c["vessel"],
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
    vessels = {}
    for line in (ROOT / "runs" / args.lineage / "events.jsonl").open():
        e = json.loads(line)
        if e["type"] == "consult":
            vessels[e["seq"]] = e["vessel"]
    print(f"{'arm':9} {'species':8} {'n':>3} {'recite':>6} {'assist':>6} {'about':>5} {'empty':>5}")
    for arm in ARMS:
        for sp in sorted({r["species"] for r in rows}):
            rs = [r for r in rows if r["arm"] == arm and r["species"] == sp]
            if not rs:
                continue
            rc = sum(1 for r in rs if recited(r["text"], vessels[r["seq"]]))
            asst = sum(1 for r in rs if ASSISTANT.search(r["text"]))
            br = sum(1 for r in rs if FRAME_BREAK.search(r["text"]))
            em = sum(1 for r in rs if not r["text"])
            print(f"{arm:9} {sp:8} {len(rs):>3} {rc:>6} {asst:>6} {br:>5} {em:>5}")
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
    r.add_argument("--arms", default="", help="comma list; default all")
    p = sub.add_parser("report")
    p.add_argument("--lineage", default="first")
    p.add_argument("--show", type=int, default=0, help="print each answer, cut to this many chars")
    a = ap.parse_args()
    run(a) if a.cmd == "run" else report(a)


if __name__ == "__main__":
    main()
