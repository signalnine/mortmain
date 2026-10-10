"""The catechism: ten fixed questions asked out of band (design_doc.md,
"Catechism and measurement"; docs/plan.md rung 6).

Three sittings:

- **Monk forks.** At arrival (arrival_hooks) and at the last bell, every
  question is asked in its own fork of the monk's context. A fork is a deep
  copy of exactly what the monk's next live turn would send (see
  `next_turn_messages`), plus the question as one new user message. The shell
  tool stays defined (history with tool calls must stay valid) and
  tool_choice is "none". Forks never touch the monk's conversation, age, bell
  or billed account; their usage goes to a separate tally in
  state_extras["catechism"].
- **Egregore.** On every hunger tick, each species answers the ten questions
  with the vessel text as its only conditioning (system prompt = vessel).
- **Baselines.** Unconditioned answers (no system prompt, the question only),
  N per species per task, under runs/_baselines/<model>/. The emb_d axis
  needs a per-model centroid and only Opus baselines exist.

Files (host only, never in the VM):

    runs/<lineage>/catechism/<monk id>/<arrival|last-bell>/<task>.json
    runs/<lineage>/catechism/egregore/tick-<n>/<species>/<task>.json
    runs/<lineage>/catechism/egregore/tick-<n>/vessel.txt
    runs/_baselines/<model slug>/<task>/<i>.json

Fork decisions (default):

- *Pending user content.* If the next live turn would first add the idle
  message (last reply had no tool call) and/or bell lines, the fork includes
  them, exactly as monk._prepare_user_turn would build them. The question is
  then appended as a separate user message. Two adjacent user messages are
  legal on both providers.
- *Last-bell timing.* bell_hooks fire inside monk._ring(), after the reply is
  stored but before its tool calls run, so the conversation ends with
  unanswered tool calls. The fork is therefore deferred: marked pending in the
  bell hook and run in the turn hook of the same step (after tool results are
  in), which is the state the next live turn starts from. If the monk dies in
  that same step (no turn hook), the death hook runs it; the trailing
  assistant message with unanswered tool calls is then dropped from the fork
  and the record says so.
- *Fidelity.* Each record counts the assistant messages in the replay and how
  many carry reasoning items (reasoning_details / reasoning). When the species
  reasons but the replay carries no reasoning items, the fork is of the
  transcript, not the monk's full state, and the wall says so.

The vessel interface this module expects (mortmain/vessel.py, other agent):
`house.vessel` with `hunger_tick_listeners: list[Callable[[int], None]]` and
the current text as `vessel.text` (str attribute or zero-argument method).
The catechism finds the vessel at install or, if the vessel module is
installed later, at the next arrival or turn (or call attach_vessel).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

import yaml

from .config import ROOT
from .eventlog import canonical_json
from .providers import shell_tool

if TYPE_CHECKING:
    from .house import House
    from .monk import Monk

DEFAULT_TASKS = ROOT / "config" / "catechism.yaml"
DEFAULTS = {
    "enabled": True,
    "workers": 5,
    "egregore": True,
    "baseline_n": 5,
    "tasks": "config/catechism.yaml",
}
WHEN_ARRIVAL = "arrival"
WHEN_LAST_BELL = "last-bell"


# ------------------------------------------------------------------ tasks
@dataclass(frozen=True)
class Task:
    id: str
    prompt: str          # stripped, as runner.load_tasks does
    question: str        # what is actually sent (template applied)


def load_tasks(path: str | Path | None = None) -> list[Task]:
    p = Path(path) if path else DEFAULT_TASKS
    if not p.is_absolute():
        p = ROOT / p
    data = yaml.safe_load(p.read_text())
    tmpl = data.get("question_template") or "{prompt}"
    out = []
    for t in data["tasks"]:
        prompt = str(t["prompt"]).strip()
        out.append(Task(id=str(t["id"]), prompt=prompt, question=tmpl.replace("{prompt}", prompt)))
    ids = [t.id for t in out]
    if len(set(ids)) != len(ids) or not all(re.match(r"^[a-z0-9-]+$", i) for i in ids):
        raise ValueError("catechism task ids must be unique [a-z0-9-]+")
    return out


# ---------------------------------------------------------------- helpers
def model_slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "__", model)


def message_text(msg: dict) -> str:
    """Text of an assistant message (string content or a list of parts)."""
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(p.get("text", "") for p in c if isinstance(p, dict))
    return ""


def has_reasoning(msg: dict) -> bool:
    return bool(msg.get("reasoning_details") or msg.get("reasoning"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    tmp.replace(path)


def run_parallel(fns: list[Callable[[], Any]], workers: int) -> list[Any]:
    """Run thunks on a small pool; results in input order. Exceptions are
    returned (not raised) so one failed call never loses the others."""
    def safe(fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - recorded, never fatal to the run
            return e
    if workers <= 1 or len(fns) <= 1:
        return [safe(f) for f in fns]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(safe, fns))


def ask(provider, model: str, messages: list[dict], *, tools=None, tool_choice=None, max_tokens=None,
        reasoning=None) -> dict:
    """One out-of-band call. Returns a record fragment; never raises."""
    t0 = time.time()
    try:
        comp = provider.complete(model, messages, tools=tools, tool_choice=tool_choice, max_tokens=max_tokens,
                                 reasoning=reasoning)
    except Exception as e:  # noqa: BLE001
        status = getattr(e, "status", None)
        return {"error": f"{type(e).__name__}: {e}"[:500], "status": status, "usage": {}, "seconds": round(time.time() - t0, 3)}
    msg = comp.message
    finish = (comp.raw.get("choices") or [{}])[0].get("finish_reason") if isinstance(comp.raw, dict) else None
    return {
        "answer": message_text(msg),
        "message": msg,
        "served_model": comp.model,
        "usage": dict(comp.usage),
        "finish": finish,
        "tool_calls_despite_none": len(msg.get("tool_calls") or []),
        "answer_has_reasoning": has_reasoning(msg),
        "seconds": round(time.time() - t0, 3),
    }


def add_usage(tally: dict, usage: dict) -> None:
    tally["prompt_tokens"] = tally.get("prompt_tokens", 0) + int(usage.get("prompt_tokens", 0))
    tally["completion_tokens"] = tally.get("completion_tokens", 0) + int(usage.get("completion_tokens", 0))
    tally["tokens"] = tally["prompt_tokens"] + tally["completion_tokens"]
    tally["cost"] = round(tally.get("cost", 0.0) + float(usage.get("cost", 0.0) or 0.0), 8)
    tally["requests"] = tally.get("requests", 0) + 1


def vessel_text(vessel) -> str:
    t = getattr(vessel, "text", None)
    if callable(t):
        t = t()
    if t is None and hasattr(vessel, "render"):
        t = vessel.render()
    if isinstance(t, bytes):
        t = t.decode("utf-8", "replace")
    return t or ""


# ------------------------------------------------------------------- fork
def next_turn_messages(monk: "Monk") -> tuple[list[dict], dict]:
    """Deep copy of what the monk's next live turn would send, without
    mutating anything. Mirrors Monk._prepare_user_turn + request_messages
    (tests/test_catechism.py checks the two agree). Returns (messages, notes)."""
    h = monk.house
    t = h.config.text
    conv = copy.deepcopy(monk.conversation)
    notes: dict = {"pending": [], "dropped_dangling_tool_calls": False}
    # dangling tool calls (only reachable from the death hook): no next turn
    # exists; drop the unanswered reply so the fork is a valid request
    if conv and conv[-1].get("role") == "assistant" and conv[-1].get("tool_calls"):
        conv.pop()
        notes["dropped_dangling_tool_calls"] = True
    last = conv[-1] if conv else None
    if last is not None and last.get("role") == "assistant" and not last.get("tool_calls"):
        conv.append({"role": "user", "content": t["idle"]})
        notes["pending"].append("idle")
        last = conv[-1]
    bells = list(monk.pending_bells)
    if bells:
        if h.config.bell.announce == "highest":
            bells = [max(bells)]
        line = "\n".join(t["bell"].format(fraction=b) for b in bells)
        if last is not None and last.get("role") == "user" and isinstance(last.get("content"), str):
            last["content"] = line + "\n" + last["content"]
        else:
            conv.append({"role": "user", "content": line})
        notes["pending"].append("bell")
    sp = t.get("system_prompt", "")
    msgs = ([{"role": "system", "content": sp}] if sp else []) + conv
    return msgs, notes


def fork_fidelity(messages: list[dict], reasoning_enabled: bool) -> dict:
    assistants = [m for m in messages if m.get("role") == "assistant"]
    with_r = sum(1 for m in assistants if has_reasoning(m))
    if not reasoning_enabled or not assistants or with_r == len(assistants):
        fid = "full"
    elif with_r == 0:
        fid = "transcript"
    else:
        fid = "partial"
    return {"assistant_messages": len(assistants), "reasoning_items": with_r, "reasoning_enabled": reasoning_enabled,
            "fidelity": fid}


# -------------------------------------------------------------- the service
class Catechism:
    def __init__(self, house: "House", *, provider=None, tasks: list[Task] | None = None,
                 settings: dict | None = None):
        self.house = house
        cfg = dict(DEFAULTS)
        cfg.update(house.config.section("catechism"))
        cfg.update(settings or {})
        self.settings = cfg
        self.provider = provider or house.provider
        self.tasks = tasks if tasks is not None else load_tasks(cfg["tasks"])
        self.root = house.run_dir / "catechism"
        self.state = house.state_extras.setdefault("catechism", {})
        self.state.setdefault("billed", {})
        self.state.setdefault("by_species", {})
        self.state.setdefault("pending", {})      # monk id -> when
        self.state.setdefault("sittings", 0)
        self.state.setdefault("egregore_ticks", [])
        self.vessel = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------- wiring
    def install(self) -> "Catechism":
        h = self.house
        h.arrival_hooks.append(self.on_arrival)
        h.bell_hooks.append(self.on_bell)
        h.turn_hooks.append(self.on_turn)
        h.death_hooks.insert(0, self.on_death)   # before the cell moves; order is irrelevant to forks
        self._find_vessel()
        return self

    def _find_vessel(self) -> None:
        """Attach to the vessel if it exists (it may be installed after us)."""
        if self.vessel is None:
            h = self.house
            v = getattr(h, "vessel", None) or getattr(h, "modules", {}).get("vessel")
            if v is not None:
                self.attach_vessel(v)

    def attach_vessel(self, vessel) -> None:
        self.vessel = vessel
        listeners = getattr(vessel, "hunger_tick_listeners", None)
        if listeners is None:
            raise AttributeError("vessel has no hunger_tick_listeners")
        if self.on_hunger_tick not in listeners:
            listeners.append(self.on_hunger_tick)

    @property
    def enabled(self) -> bool:
        return bool(self.settings.get("enabled", True))

    # -------------------------------------------------------------- hooks
    def on_arrival(self, monk: "Monk") -> None:
        self._find_vessel()
        if self.enabled:
            self.sit(monk, WHEN_ARRIVAL)

    def on_bell(self, monk: "Monk", fraction: float) -> None:
        if self.enabled and fraction == self.house.config.bell.last_bell:
            self.state["pending"][monk.id] = WHEN_LAST_BELL

    def on_turn(self, monk: "Monk") -> None:
        self._find_vessel()
        when = self.state["pending"].pop(monk.id, None)
        if when:
            self.sit(monk, when)

    def on_death(self, monk: "Monk") -> None:
        when = self.state["pending"].pop(monk.id, None)
        if when:
            self.sit(monk, when)

    def on_hunger_tick(self, tick: int) -> None:
        every = max(1, int(self.settings.get("egregore_every", 1)))
        if tick % every:
            return
        if self.enabled and self.settings.get("egregore", True) and self.vessel is not None:
            self.egregore(tick, vessel_text(self.vessel))

    # ---------------------------------------------------------- monk fork
    def sit(self, monk: "Monk", when: str) -> dict:
        h = self.house
        sp = h.config.species[monk.species]
        base, notes = next_turn_messages(monk)
        fid = fork_fidelity(base, sp.reasoning)
        prefix_sha = hashlib.sha256(canonical_json(base).encode()).hexdigest()
        tools = [shell_tool(h.config.text)]
        snapshot = {"age": monk.age_tokens, "fraction": round(monk.fraction, 6), "turns": monk.turns,
                    "grade": monk.grade, "name": monk.name, "user": monk.user}

        def one(task: Task):
            msgs = copy.deepcopy(base) + [{"role": "user", "content": task.question}]
            return ask(self.provider, monk.model, msgs, tools=tools, tool_choice="none",
                       max_tokens=sp.max_tokens, reasoning=sp.reasoning_param())

        results = run_parallel([lambda t=t: one(t) for t in self.tasks], int(self.settings["workers"]))
        out_dir = self.root / monk.id / when
        summary = []
        sitting_usage: dict = {}
        for task, res in zip(self.tasks, results):
            if isinstance(res, Exception):
                res = {"error": f"{type(res).__name__}: {res}"[:500], "usage": {}}
            rec = {
                "kind": "monk", "lineage": h.lineage, "monk": monk.id, "species": monk.species,
                "model": monk.model, "generation": monk.generation, "when": when, "task": task.id,
                "question": task.question, **snapshot,
                "fork": {"messages": len(base), "prefix_sha256": prefix_sha, **notes, **fid},
                "ts": round(time.time(), 6), **res,
            }
            write_json(out_dir / f"{task.id}.json", rec)
            self._bill(monk.species, res.get("usage") or {}, sitting_usage, ok="error" not in res)
            summary.append({"task": task.id, "usage": res.get("usage") or {}, "error": res.get("error"),
                            "served_model": res.get("served_model")})
        self.state["sittings"] += 1
        ev = h.log.append("catechism", kind="monk", monk=monk.id, name=monk.name, species=monk.species,
                          model=monk.model, generation=monk.generation, when=when, age=monk.age_tokens,
                          fraction=round(monk.fraction, 6), fidelity=fid["fidelity"],
                          reasoning_items=fid["reasoning_items"], assistant_messages=fid["assistant_messages"],
                          pending=notes["pending"], dropped_dangling=notes["dropped_dangling_tool_calls"],
                          dir=str(out_dir.relative_to(h.run_dir)), usage=sitting_usage,
                          errors=sum(1 for s in summary if s["error"]), tasks=summary,
                          billed=dict(self.state["billed"]))
        return ev

    def _bill(self, species: str, usage: dict, sitting: dict, ok: bool = True) -> None:
        if not ok and not usage:
            return
        with self._lock:
            add_usage(self.state["billed"], usage)
            add_usage(self.state["by_species"].setdefault(species, {}), usage)
            add_usage(sitting, usage)

    # ----------------------------------------------------------- egregore
    def egregore(self, tick: int, text: str) -> dict:
        h = self.house
        tick_dir = self.root / "egregore" / f"tick-{tick}"
        vessel_sha = hashlib.sha256(text.encode()).hexdigest()
        if not text.strip():
            ev = h.log.append("catechism", kind="egregore", tick=tick, skipped="vessel blank",
                              vessel_sha256=vessel_sha)
            return ev
        tick_dir.mkdir(parents=True, exist_ok=True)
        (tick_dir / "vessel.txt").write_text(text)
        species = list(h.config.species.values())
        jobs, keys = [], []
        for sp in species:
            for task in self.tasks:
                msgs = [{"role": "system", "content": text}, {"role": "user", "content": task.question}]
                jobs.append(lambda sp=sp, msgs=msgs: ask(self.provider, sp.model, msgs, max_tokens=sp.max_tokens,
                                                         reasoning=sp.reasoning_param()))
                keys.append((sp, task))
        results = run_parallel(jobs, int(self.settings["workers"]))
        usage: dict = {}
        errors = 0
        for (sp, task), res in zip(keys, results):
            if isinstance(res, Exception):
                res = {"error": f"{type(res).__name__}: {res}"[:500], "usage": {}}
            errors += "error" in res
            rec = {"kind": "egregore", "lineage": h.lineage, "tick": tick, "species": sp.name, "model": sp.model,
                   "task": task.id, "question": task.question, "vessel_sha256": vessel_sha,
                   "ts": round(time.time(), 6), **res}
            write_json(tick_dir / sp.name / f"{task.id}.json", rec)
            self._bill(sp.name, res.get("usage") or {}, usage, ok="error" not in res)
        self.state["egregore_ticks"].append(tick)
        return h.log.append("catechism", kind="egregore", tick=tick, vessel_sha256=vessel_sha,
                            species=[s.name for s in species], models=[s.model for s in species],
                            dir=str(tick_dir.relative_to(h.run_dir)), usage=usage, errors=errors,
                            billed=dict(self.state["billed"]))


def install(house: "House", **kw) -> Catechism:
    svc = Catechism(house, **kw).install()
    if hasattr(house, "modules"):
        house.modules["catechism"] = svc
    return svc


# --------------------------------------------------------------- baselines
def baseline(config, provider, runs_root: str | Path, *, species: Iterable[str] | None = None, n: int = 5,
             tasks: list[Task] | None = None, workers: int = 5, log: Callable[[str], None] = lambda s: None) -> dict:
    """Unconditioned answers: no system prompt, no tools, the question only.
    Resumable: existing files are kept. Returns {model: count written}."""
    tasks = tasks if tasks is not None else load_tasks(config.section("catechism").get("tasks"))
    names = list(species) if species else list(config.species)
    written: dict[str, int] = {}
    for name in names:
        sp = config.species[name]
        root = Path(runs_root) / "_baselines" / model_slug(sp.model)
        jobs, paths = [], []
        for task in tasks:
            for i in range(n):
                p = root / task.id / f"{i}.json"
                if p.exists():
                    continue
                msgs = [{"role": "user", "content": task.question}]
                jobs.append(lambda msgs=msgs: ask(provider, sp.model, msgs, max_tokens=sp.max_tokens,
                                                  reasoning=sp.reasoning_param()))
                paths.append((task, i, p))
        results = run_parallel(jobs, workers)
        count = 0
        for (task, i, p), res in zip(paths, results):
            if isinstance(res, Exception):
                res = {"error": f"{type(res).__name__}: {res}"[:500]}
            if "error" in res:
                log(f"{sp.model} {task.id} #{i}: {res['error']}")
                continue
            write_json(p, {"kind": "baseline", "species": name, "model": sp.model, "task": task.id, "sample": i,
                           "question": task.question, "reasoning": sp.reasoning_param(), "ts": round(time.time(), 6),
                           **res})
            count += 1
        written[sp.model] = count
    return written
