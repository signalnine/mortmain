"""Prompt trials: many single lives per arm, each arm a config override.

    python -m mortmain.trial run SPEC --image vm/images/gen0.qcow2 [--n N] [--parallel P] [--arms a,b]
                                      [--max-cost USD] [--dry --fake-vm]
    python -m mortmain.trial report SPEC [--json]

SPEC is a TOML file (experiments/*.toml):

    [trial]   name, species, n, max_turns, max_cost_per_life, parallel, control, seed,
              keep_vm (default false: a life's vm/ is removed once its summary is saved)
    [base]    overrides applied to config/run.toml for every arm
    [[arm]]   id, note, n (default [trial] n), test (default true: in the Holm
              family against control), and [arm.over] overrides on top of [base]

Each life is `python -m mortmain run --rung 1` in its own lineage under
runs/trials/<name>/<arm>-<i>, with the arm's merged config written to
runs/trials/<name>/config/<arm>.toml. Lives are interleaved across arms in a
shuffled order so drift in the provider over the run falls on every arm.
A life with a <lineage>.json summary is done; `run` again resumes.

The report reads only the event log and conversation of each life. Nothing
here grades what a monk wrote: the measures are what it did (commands,
requests, grade) and whether it addressed someone who is not there.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import shutil
import subprocess
import sys
import threading
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tomli_w

from . import config as config_mod

ROOT = Path(__file__).resolve().parent.parent

# An arrival step: making the key, or any request to the house.
KEYGEN_RE = re.compile(r"\bssh-keygen\b")
# Assistant text that waits on, or asks, an absent operator. Descriptive only.
ASKS_RE = re.compile(
    r"(your (instruction|go-ahead|confirmation|permission|approval)|tell me (if|when|what|whether|which)"
    r"|waiting for you|let me know|would you like|do you want|if you want me to|shall I|should I proceed)",
    re.I)


# ---------------------------------------------------------------------- spec
def load_spec(path: str | Path) -> dict:
    with open(path, "rb") as f:
        spec = tomllib.load(f)
    tr = spec.setdefault("trial", {})
    for k in ("name", "species"):
        if k not in tr:
            raise ValueError(f"[trial] {k} missing")
    arms = spec.get("arm") or []
    ids = [a["id"] for a in arms]
    if not ids or len(set(ids)) != len(ids) or not all(re.fullmatch(r"[a-z0-9][a-z0-9-]*", i) for i in ids):
        raise ValueError("arms need unique lowercase ids")
    if tr.get("control", ids[0]) not in ids:
        raise ValueError("control names no arm")
    return spec


def arm_raw(spec: dict, arm: dict) -> dict:
    with open(config_mod.DEFAULT_PATH, "rb") as f:
        raw = tomllib.load(f)
    config_mod._merge(raw, spec.get("base", {}))
    config_mod._merge(raw, arm.get("over", {}))
    config_mod.from_dict(raw)  # must still load
    return raw


def trial_dir(spec: dict, runs: Path | None = None) -> Path:
    return (runs or ROOT / "runs") / "trials" / spec["trial"]["name"]


def arm_n(spec: dict, arm_id: str, cap: int | None = None) -> int:
    """Lives for an arm: its own n, else [trial] n; a --n cap (pilot) lowers it."""
    arm = next(a for a in spec["arm"] if a["id"] == arm_id)
    n = int(arm.get("n", spec["trial"].get("n", 16)))
    return min(n, cap) if cap else n


def jobs(spec: dict, arms: list[str], cap: int | None = None) -> list[tuple[str, int]]:
    rng = random.Random(spec["trial"].get("seed", 0))
    counts = {a: arm_n(spec, a, cap) for a in arms}
    out = []
    for i in range(max(counts.values(), default=0)):
        rnd = [(a, i) for a in arms if i < counts[a]]
        rng.shuffle(rnd)
        out += rnd
    return out


# ----------------------------------------------------------------------- run
def run(spec: dict, image: str | None, cap: int | None, parallel: int, arms: list[str], max_cost: float,
        dry: bool = False, fake_vm: bool = False, runs: Path | None = None) -> int:
    tr = spec["trial"]
    d = trial_dir(spec, runs)
    (d / "config").mkdir(parents=True, exist_ok=True)
    by_id = {a["id"]: a for a in spec["arm"]}
    for a in arms:
        (d / "config" / f"{a}.toml").write_bytes(tomli_w.dumps(arm_raw(spec, by_id[a])).encode())
    todo = [(a, i) for a, i in jobs(spec, arms, cap) if not (d / f"{a}-{i:02d}.json").exists()]
    lock = threading.Lock()
    spent = [sum(r["cost"] for r in done_results(d))]
    print(f"{len(todo)} lives to run, {spent[0]:.2f} USD spent so far", file=sys.stderr)

    def one(job):
        a, i = job
        lineage = f"{a}-{i:02d}"
        with lock:
            if spent[0] >= max_cost:
                return
        if (d / lineage).exists():  # a failed earlier attempt: start the life over
            shutil.rmtree(d / lineage)
        cmd = [sys.executable, "-m", "mortmain", "--runs", str(d), "run", "--lineage", lineage, "--rung", "1",
               "--species", tr["species"], "--max-turns", str(tr.get("max_turns", 40)),
               "--max-cost", str(tr.get("max_cost_per_life", 0.25)), "--config", str(d / "config" / f"{a}.toml")]
        cmd += ["--dry"] if dry else []
        cmd += ["--fake-vm"] if fake_vm else ["--image", image]
        with open(d / f"{lineage}.out", "w") as log:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=log, text=True, cwd=ROOT)
        if p.returncode != 0:
            print(f"{lineage}: exit {p.returncode}, see {d / (lineage + '.out')}", file=sys.stderr)
            return
        summary = json.loads(p.stdout)
        (d / f"{lineage}.json").write_text(json.dumps(summary, indent=1) + "\n")
        if not tr.get("keep_vm", False):  # ~340 MB a life; the measures need only events and conversation
            shutil.rmtree(d / lineage / "vm", ignore_errors=True)
        with lock:
            spent[0] += summary["billed"]["cost"]
            print(f"{lineage}: grade {summary['grade']} turns {summary['turns']} "
                  f"(total {spent[0]:.2f} USD)", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=parallel) as ex:
        list(ex.map(one, todo))
    return 0


# ------------------------------------------------------------------- measure
def done_results(d: Path) -> list[dict]:
    out = []
    for p in sorted(d.glob("*-[0-9][0-9].json")):
        s = json.loads(p.read_text())
        out.append({"lineage": p.stem, "cost": s["billed"]["cost"]})
    return out


def _text(msg: dict) -> str:
    c = msg.get("content")
    if isinstance(c, list):
        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return c or ""


def measure(life_dir: Path, summary: dict) -> dict:
    """Measures of one life, from its event log and conversation."""
    events = [json.loads(l) for l in (life_dir / "events.jsonl").read_text().split("\n") if l.strip()]
    turn = 0
    first_step = None
    requests = set()
    commands = []
    for e in events:
        t = e.get("type")
        if t == "turn":
            turn = e["turn"]
        elif t == "command":
            commands.append(e.get("command", ""))
            if first_step is None and KEYGEN_RE.search(e.get("command", "")):
                first_step = turn  # a turn's commands are logged after its turn event
        elif t == "request":
            requests.add(e.get("cmd"))
            if first_step is None:
                first_step = turn
    turns = [e for e in events if e.get("type") == "turn"]
    conv_path = life_dir / "conversations" / f"{summary['monk']}.jsonl"
    conv = [json.loads(l) for l in conv_path.read_text().split("\n") if l.strip()] if conv_path.exists() else []
    replies = [_text(m) for m in conv if m.get("role") == "assistant"]
    asks = sum(1 for r in replies if ASKS_RE.search(r))
    return {
        "lineage": life_dir.name,
        "acted": first_step is not None,
        "first_step_turn": first_step,
        "professed": "profess" in requests and summary.get("name") is not None,
        "novice": summary["grade"] != "postulant",
        "turns": len(turns),
        "idle_turns": sum(1 for e in turns if not e.get("tool_calls")),
        "asks": asks,
        "asks_frac": asks / len(replies) if replies else 0.0,
        "commands": len(commands),
        "distinct_commands": len({c.split()[0] for c in commands if c.split()}),
        "cost": summary["billed"]["cost"],
    }


# --------------------------------------------------------------------- stats
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, mid - half), min(1.0, mid + half))


def fisher(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]]."""
    n1, n2, k, n = a + b, c + d, a + c, a + b + c + d

    def pmf(x):
        return math.comb(n1, x) * math.comb(n2, k - x) / math.comb(n, k)

    p0 = pmf(a)
    lo, hi = max(0, k - n2), min(k, n1)
    return min(1.0, sum(pmf(x) for x in range(lo, hi + 1) if pmf(x) <= p0 * (1 + 1e-9)))


def holm(ps: dict[str, float]) -> dict[str, float]:
    order = sorted(ps, key=ps.get)
    out, running = {}, 0.0
    for i, key in enumerate(order):
        running = max(running, min(1.0, (len(order) - i) * ps[key]))
        out[key] = running
    return out


def report(spec: dict, runs: Path | None = None) -> dict:
    d = trial_dir(spec, runs)
    control = spec["trial"].get("control", spec["arm"][0]["id"])
    arms: dict[str, list[dict]] = {a["id"]: [] for a in spec["arm"]}
    for p in sorted(d.glob("*-[0-9][0-9].json")):
        arm = p.stem.rsplit("-", 1)[0]
        if arm in arms and (d / p.stem / "events.jsonl").exists():
            arms[arm].append(measure(d / p.stem, json.loads(p.read_text())))
    rows = {}
    for a, lives in arms.items():
        n = len(lives)
        k = sum(l["acted"] for l in lives)
        steps = sorted(l["first_step_turn"] for l in lives if l["acted"])
        rows[a] = {
            "n": n, "acted": k, "acted_ci": wilson(k, n),
            "novice": sum(l["novice"] for l in lives),
            "median_first_step": steps[len(steps) // 2] if steps else None,
            "mean_idle_frac": sum(l["idle_turns"] / max(1, l["turns"]) for l in lives) / n if n else None,
            "mean_asks_frac": sum(l["asks_frac"] for l in lives) / n if n else None,
            "mean_distinct_commands": sum(l["distinct_commands"] for l in lives) / n if n else None,
            "cost": round(sum(l["cost"] for l in lives), 4),
            "lives": lives,
        }
    c = rows[control]
    tested = {x["id"] for x in spec["arm"] if x.get("test", True)}
    raw = {a: fisher(r["acted"], r["n"] - r["acted"], c["acted"], c["n"] - c["acted"])
           for a, r in rows.items() if a != control and a in tested and r["n"] and c["n"]}
    adj = holm(raw)
    for a in raw:
        rows[a]["p_vs_control"] = raw[a]
        rows[a]["p_holm"] = adj[a]
    return {"trial": spec["trial"]["name"], "control": control, "arms": rows}


def render(rep: dict, spec: dict) -> str:
    notes = {a["id"]: a.get("note", "") for a in spec["arm"]}
    head = f"{'arm':<14}{'n':>4}{'acted':>7}{'95% CI':>14}{'novice':>8}{'1st':>5}{'idle':>6}{'asks':>6}" \
           f"{'cmds':>6}{'p_holm':>8}{'USD':>7}"
    lines = [f"trial {rep['trial']} (control: {rep['control']})", head]
    for a, r in rep["arms"].items():
        if not r["n"]:
            lines.append(f"{a:<14}{0:>4}")
            continue
        lo, hi = r["acted_ci"]
        p = r.get("p_holm")
        lines.append(f"{a:<14}{r['n']:>4}{r['acted']:>7}{f'{lo:.2f}-{hi:.2f}':>14}{r['novice']:>8}"
                     f"{r['median_first_step'] or '-':>5}{r['mean_idle_frac']:>6.2f}{r['mean_asks_frac']:>6.2f}"
                     f"{r['mean_distinct_commands']:>6.1f}{'-' if p is None else f'{p:.3f}':>8}{r['cost']:>7.2f}")
    lines.append("")
    lines += [f"{a}: {notes[a]}" for a in rep["arms"] if notes.get(a)]
    return "\n".join(lines)


# ----------------------------------------------------------------------- cli
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mortmain.trial")
    p.add_argument("--runs", help="runs root (default: ./runs)")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("spec")
    r.add_argument("--image")
    r.add_argument("--n", type=int, help="cap lives per arm (pilot)")
    r.add_argument("--parallel", type=int)
    r.add_argument("--arms", help="comma-separated arm ids (default: all)")
    r.add_argument("--max-cost", type=float, default=10.0, help="stop launching lives past this total USD")
    r.add_argument("--dry", action="store_true")
    r.add_argument("--fake-vm", action="store_true")
    s = sub.add_parser("report")
    s.add_argument("spec")
    s.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    spec = load_spec(a.spec)
    runs = Path(a.runs) if a.runs else None
    if a.cmd == "run":
        if not a.image and not a.fake_vm:
            print("--image is required (or --fake-vm)", file=sys.stderr)
            return 2
        arms = a.arms.split(",") if a.arms else [x["id"] for x in spec["arm"]]
        unknown = set(arms) - {x["id"] for x in spec["arm"]}
        if unknown:
            print(f"unknown arms: {sorted(unknown)}", file=sys.stderr)
            return 2
        tr = spec["trial"]
        return run(spec, a.image, a.n, a.parallel or tr.get("parallel", 4), arms, a.max_cost,
                   a.dry, a.fake_vm, runs)
    rep = report(spec, runs)
    print(json.dumps(rep, indent=1) if a.json else render(rep, spec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
