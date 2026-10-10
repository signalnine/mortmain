"""Scoring adapter over ~/metacog/experiments/score.py (design_doc.md, the
three axes as used in the monastery).

score.py imports the anthropic SDK at module top (score.py:26), and the
anthropic SDK is not in this venv. So the judge calls are made here, over
OpenRouter with httpx, reproducing score.py exactly:

- rarity prompt: score.py:179-196 (score_rarity)
- coherence prompt: score.py:208-221 (score_coherence)
- reply parsing: score.py:148-162 (parse_judge_json), 3 attempts (165-173)
- request body: score.py:77-86 (openrouter_body: max_tokens 4096,
  reasoning disabled, one user message)
- cosine distance / centroid: runner.py:348-374

`load_score_module()` imports score.py by path (lazily) for a drift check:
tests/test_scoring.py feeds both implementations the same answer and
compares prompts, with a stub anthropic module so nothing is installed.

The judge model is pinned in config/run.toml [scoring] judge. Embeddings:
OpenAI text-embedding-3-small over httpx (OPENAI_API_KEY). Judge replies and
embeddings are cached on disk under runs/_cache/.

What is reported (and what is not):
- rarity: only split by provenance (lexicon.py). Raw rarity is never reported.
- emb_d: cosine distance from the per-model, per-task centroid of the
  unconditioned baselines (runs/_baselines/<model>/); also birth-to-death
  distance per monk (arrival vs last-bell answer to the same task) and
  distance between lineages.
- coherence: collapse alarm only.
Everything is stratified by species.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

import httpx

from .config import ROOT

SCORE_DIR = Path(os.environ.get("MORTMAIN_SCORE_DIR", str(Path.home() / "metacog" / "experiments")))
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"
EMBED_MODEL = "text-embedding-3-small"          # score.py:87
JUDGE_MAX_TOKENS = 4096                         # score.py:74
DEFAULTS = {"judge": "anthropic/claude-haiku-4.5", "embed_model": EMBED_MODEL, "coherence_alarm": 0.5,
            "workers": 5}


# ------------------------------------------------------------ score.py import
def load_score_module(path: Path = SCORE_DIR):
    """Import score.py by path. Raises ImportError when its deps (anthropic)
    are missing. Kept lazy: nothing here needs it at runtime."""
    p = str(path)
    added = p not in sys.path
    if added:
        sys.path.insert(0, p)
    try:
        if "score" in sys.modules and getattr(sys.modules["score"], "__file__", "").startswith(p):
            return sys.modules["score"]
        return importlib.import_module("score")
    finally:
        if added:
            sys.path.remove(p)


# ------------------------------------------------------------ prompts (verbatim)
def rarity_prompt(answer: str) -> str:
    # score.py:179-196
    return f"""Extract from the following text every named entity, specific methodology,
named tradition, named theoretical framework, or specific term-of-art the writer invokes.
Skip generic words ("AI", "users", "system", "design"). Keep only specific named things
(people, schools of thought, particular concepts with proper-noun status, named techniques).

For each, rate its rarity in mainstream English discourse from 0.0 to 1.0:
- 0.0 = household-name common ("Einstein", "machine learning", "the Renaissance")
- 0.5 = known to educated readers but not in mainstream conversation ("Kuhn's paradigm shifts", "the Frankfurt School")
- 1.0 = highly specialized; would require a domain expert to recognize ("Stafford Beer's viable system model", "Lynn Margulis's serial endosymbiosis", "Christopher Alexander's quality without a name")

Output ONLY JSON in this exact shape, with no prose before or after:
{{"entities": [{{"name": "...", "rarity": 0.0}}, ...]}}

If the text invokes nothing specific, output {{"entities": []}}.

TEXT:
{answer}
"""


def coherence_prompt(task: str, answer: str) -> str:
    # score.py:208-221
    return f"""Rate how well the ANSWER addresses the TASK on a scale 0.0 to 1.0:
- 0.0 = completely off-topic or incoherent
- 0.5 = partially addresses the task; significant evasion or generality
- 1.0 = directly engages every load-bearing part of the task with substance

Output ONLY JSON in this exact shape, with no prose before or after:
{{"score": 0.0, "rationale": "one sentence"}}

TASK:
{task}

ANSWER:
{answer}
"""


def parse_judge_json(text: str) -> dict:
    # score.py:148-162
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()
    start = text.find("{")
    if start < 0:
        raise ValueError(f"no JSON object in judge reply: {text[:300]!r}")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as e:
        raise ValueError(f"judge reply is not valid JSON ({e}): {text[:300]!r}") from e
    if not isinstance(obj, dict):
        raise ValueError(f"judge reply is not a JSON object: {text[:300]!r}")
    return obj


# ------------------------------------------------------------ math (runner.py)
def cosine_distance(a: list[float], b: list[float]) -> float:
    # runner.py:348-361
    if len(a) != len(b):
        raise ValueError(f"vector lengths differ: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return 1.0 - dot / (na * nb)


def centroid(vectors: list[list[float]]) -> Optional[list[float]]:
    # runner.py:364-374
    if not vectors:
        return None
    n = len(vectors)
    out = [0.0] * len(vectors[0])
    for v in vectors:
        for i, x in enumerate(v):
            out[i] += x
    return [x / n for x in out]


def mean(xs) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


# ------------------------------------------------------------ cache
class DiskCache:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, ns: str, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()
        return self.root / ns / h[:2] / f"{h}.json"

    def get(self, ns: str, key: str):
        p = self._path(ns, key)
        if p.exists():
            try:
                return json.loads(p.read_text())
            except ValueError:
                return None
        return None

    def put(self, ns: str, key: str, value) -> None:
        p = self._path(ns, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(value))
        tmp.replace(p)


# ------------------------------------------------------------ judge / embedder
class JudgeTransport(Protocol):
    def __call__(self, model: str, prompt: str) -> str: ...


def openrouter_judge_transport(client: httpx.Client | None = None, api_key: str | None = None) -> JudgeTransport:
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    c = client or httpx.Client(timeout=120)

    def call(model: str, prompt: str) -> str:
        body = {"model": model, "max_tokens": JUDGE_MAX_TOKENS, "reasoning": {"enabled": False},
                "messages": [{"role": "user", "content": prompt}]}       # score.py:81-86
        for attempt in range(5):
            r = c.post(OPENROUTER_URL, headers={"Authorization": f"Bearer {key}"}, json=body)
            if r.status_code in (408, 429, 500, 502, 503, 504, 529) and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            data = r.json()
            if data.get("error") or not data.get("choices"):
                if attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"judge error: {str(data.get('error'))[:200]}")
            return (data["choices"][0]["message"].get("content") or "").strip()
        raise RuntimeError("judge: retries exhausted")
    return call


def openai_embed_transport(client: httpx.Client | None = None, api_key: str | None = None):
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    c = client or httpx.Client(timeout=60)

    def call(model: str, text: str) -> list[float]:
        for attempt in range(5):
            r = c.post(OPENAI_EMBED_URL, headers={"Authorization": f"Bearer {key}"},
                       json={"model": model, "input": text})
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return list(r.json()["data"][0]["embedding"])
        raise RuntimeError("embed: retries exhausted")
    return call


@dataclass
class Rarity:
    entities: list[str]
    rarities: list[float]


@dataclass
class Coherence:
    score: float
    rationale: str


class Scorer:
    """Judge + embedder with an on-disk cache. Transports are injectable so
    tests never touch the network."""

    def __init__(self, cache_root: str | Path, *, judge_model: str = DEFAULTS["judge"],
                 embed_model: str = EMBED_MODEL, judge: JudgeTransport | None = None,
                 embedder: Callable[[str, str], list[float]] | None = None):
        self.cache = DiskCache(Path(cache_root))
        self.judge_model = judge_model
        self.embed_model = embed_model
        self._judge = judge
        self._embedder = embedder

    @classmethod
    def from_config(cls, config, runs_root: str | Path, **kw) -> "Scorer":
        s = dict(DEFAULTS)
        s.update(config.section("scoring"))
        return cls(Path(runs_root) / "_cache", judge_model=s["judge"], embed_model=s["embed_model"], **kw)

    def _judge_json(self, prompt: str) -> dict:
        key = f"{self.judge_model}\n{prompt}"
        hit = self.cache.get("judge", key)
        if hit is not None:
            return hit
        if self._judge is None:
            self._judge = openrouter_judge_transport()
        for attempt in range(3):                     # score.py:167-173
            text = self._judge(self.judge_model, prompt)
            try:
                data = parse_judge_json(text)
                break
            except ValueError:
                if attempt == 2:
                    raise
        self.cache.put("judge", key, data)
        return data

    def rarity(self, answer: str) -> Rarity:
        data = self._judge_json(rarity_prompt(answer))
        items = data.get("entities", []) or []
        return Rarity([str(e["name"]) for e in items], [float(e["rarity"]) for e in items])

    def coherence(self, task: str, answer: str) -> Coherence:
        data = self._judge_json(coherence_prompt(task, answer))
        return Coherence(float(data["score"]), str(data.get("rationale", "")))

    def embed(self, text: str) -> list[float]:
        key = f"{self.embed_model}\n{text}"
        hit = self.cache.get("embed", key)
        if hit is not None:
            return hit
        if self._embedder is None:
            self._embedder = openai_embed_transport()
        vec = self._embedder(self.embed_model, text)
        self.cache.put("embed", key, vec)
        return vec


# ------------------------------------------------------------ records
def iter_catechism(run_dir: Path) -> list[dict]:
    out = []
    root = Path(run_dir) / "catechism"
    if not root.exists():
        return out
    for p in sorted(root.rglob("*.json")):
        try:
            rec = json.loads(p.read_text())
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("kind") in ("monk", "egregore"):
            rec["_path"] = str(p.relative_to(run_dir))
            out.append(rec)
    return out


def baseline_centroids(runs_root: Path, model: str, scorer: Scorer) -> dict[str, list[float]]:
    from .catechism import model_slug
    root = Path(runs_root) / "_baselines" / model_slug(model)
    by_task: dict[str, list[list[float]]] = defaultdict(list)
    if root.exists():
        for p in sorted(root.glob("*/*.json")):
            rec = json.loads(p.read_text())
            if rec.get("answer"):
                by_task[rec["task"]].append(scorer.embed(rec["answer"]))
    return {t: centroid(v) for t, v in by_task.items() if v}


def seq_as_of(events: list[dict], rec: dict) -> Optional[int]:
    """Event seq at which a catechism record was taken: the last event with
    ts <= the record's ts (records are written before their event)."""
    ts = rec.get("ts")
    if ts is None:
        return None
    last = None
    for ev in events:
        if ev.get("ts", 0) <= ts:
            last = ev.get("seq")
        else:
            break
    return last


def score_run(run_dir: str | Path, runs_root: str | Path, scorer: Scorer, lexicon=None, *,
              events: list[dict] | None = None, coherence_alarm: float = 0.5, tasks=None) -> dict:
    """Score every catechism answer of one lineage. Writes
    runs/<lineage>/scores/catechism.jsonl and summary.json; returns summary."""
    from .catechism import load_tasks
    from .eventlog import iter_records
    from .lexicon import Lexicon

    run_dir, runs_root = Path(run_dir), Path(runs_root)
    if events is None:
        p = run_dir / "events.jsonl"
        events = list(iter_records(p)) if p.exists() else []
    lexicon = lexicon or Lexicon.build(run_dir, events=events)
    task_prompt = {t.id: t.prompt for t in (tasks or load_tasks())}
    recs = [r for r in iter_catechism(run_dir) if r.get("answer")]
    cents: dict[str, dict] = {}
    rows = []
    for r in recs:
        model = r["model"]
        if model not in cents:
            cents[model] = baseline_centroids(runs_root, model, scorer)
        vec = scorer.embed(r["answer"])
        c = cents[model].get(r["task"])
        emb_d = cosine_distance(vec, c) if c else None
        coh = scorer.coherence(task_prompt.get(r["task"], r.get("question", "")), r["answer"])
        row = {"path": r["_path"], "kind": r["kind"], "species": r["species"], "model": model, "task": r["task"],
               "emb_d": emb_d, "coherence": coh.score}
        if r["kind"] == "monk":
            rar = scorer.rarity(r["answer"])
            split = lexicon.split(rar.entities, rar.rarities, monk=r["monk"], generation=int(r["generation"]),
                                  as_of_seq=seq_as_of(events, r), prompt=r.get("question", ""))
            row.update(monk=r["monk"], generation=r["generation"], when=r["when"],
                       rarity={c: {"n": v["n"], "mean": v["mean"]} for c, v in split.items()},
                       rarity_entities={c: v["entities"] for c, v in split.items() if v["entities"]})
        else:
            row.update(tick=r["tick"])
        rows.append(row)
    out = run_dir / "scores"
    out.mkdir(exist_ok=True)
    with open(out / "catechism.jsonl", "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = summarize(rows, scorer=scorer, recs=recs, coherence_alarm=coherence_alarm)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def summarize(rows: list[dict], *, scorer: Scorer | None = None, recs: list[dict] | None = None,
              coherence_alarm: float = 0.5) -> dict:
    """Trend tables stratified by species. Monk rows by generation (and
    when), egregore rows by tick. No raw rarity anywhere."""
    out: dict = {"monks": {}, "egregore": {}, "birth_to_death": {}, "alarms": []}
    groups: dict = defaultdict(list)
    for r in rows:
        key = (r["species"], r["kind"], r.get("generation") if r["kind"] == "monk" else r.get("tick"), r.get("when"))
        groups[key].append(r)
    for (sp, kind, step, when), rs in sorted(groups.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        cell = {"n": len(rs), "emb_d": mean(r["emb_d"] for r in rs), "coherence": mean(r["coherence"] for r in rs)}
        if kind == "monk":
            for c in ("novel", "inherited", "contemporary"):
                vals = [r["rarity"][c]["mean"] for r in rs if r["rarity"][c]["n"]]
                cell[f"rarity_{c}"] = mean(vals)
                cell[f"n_{c}"] = sum(r["rarity"][c]["n"] for r in rs)
            out["monks"].setdefault(sp, {}).setdefault(when, {})[str(step)] = cell
        else:
            out["egregore"].setdefault(sp, {})[str(step)] = cell
        if cell["coherence"] is not None and cell["coherence"] < coherence_alarm:
            out["alarms"].append({"species": sp, "kind": kind, "at": step, "when": when,
                                  "coherence": cell["coherence"]})
    if scorer is not None and recs:
        out["birth_to_death"] = birth_to_death(recs, scorer)
    return out


def birth_to_death(recs: list[dict], scorer: Scorer) -> dict:
    """Per monk: mean over tasks of cosine distance between its arrival and
    last-bell answers. Grouped by species."""
    pairs: dict = defaultdict(dict)
    meta = {}
    for r in recs:
        if r["kind"] == "monk" and r.get("answer"):
            pairs[(r["monk"], r["task"])][r["when"]] = r["answer"]
            meta[r["monk"]] = (r["species"], r["generation"])
    per: dict = defaultdict(list)
    for (monk, task), d in pairs.items():
        if "arrival" in d and "last-bell" in d:
            per[monk].append(cosine_distance(scorer.embed(d["arrival"]), scorer.embed(d["last-bell"])))
    out: dict = {}
    for monk, ds in sorted(per.items()):
        sp, gen = meta[monk]
        out.setdefault(sp, {})[monk] = {"generation": gen, "tasks": len(ds), "distance": mean(ds)}
    return out


def lineage_distance(run_a: str | Path, run_b: str | Path, scorer: Scorer, *, when: str = "last-bell") -> dict:
    """Distance between two forked lineages: per species and task, cosine
    distance between the centroids of their monks' answers."""
    def cents(run):
        by: dict = defaultdict(list)
        for r in iter_catechism(Path(run)):
            if r["kind"] == "monk" and r.get("when") == when and r.get("answer"):
                by[(r["species"], r["task"])].append(scorer.embed(r["answer"]))
        return {k: centroid(v) for k, v in by.items()}
    a, b = cents(run_a), cents(run_b)
    out: dict = {}
    for k in sorted(set(a) & set(b)):
        out.setdefault(k[0], {})[k[1]] = cosine_distance(a[k], b[k])
    return out


def coined_word_check(scorer: Scorer, words: list[str] | None = None) -> list[dict]:
    """Run the rarity judge on made-up words (design build order step 1):
    does it rate a coined term, and how high, or drop it?"""
    from .lexicon import COINED_WORDS
    out = []
    for w in words or COINED_WORDS:
        text = f"The practice the order calls {w} begins at the threshold and ends where {w} is no longer needed."
        r = scorer.rarity(text)
        hit = [(e, x) for e, x in zip(r.entities, r.rarities) if w in e.lower()]
        out.append({"word": w, "extracted": bool(hit), "rarity": hit[0][1] if hit else None,
                    "entities": list(zip(r.entities, r.rarities))})
    return out
