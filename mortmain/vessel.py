"""The vessel (design_doc.md "The egregore"; docs/plan.md rung 4).

/chapter/vessel is the only text of the egregore: 36 slots, one per line of
the abbot's poem, rendered as exactly `slots` lines (a blank slot is an empty
line; the file is the slots joined by newlines, with a final newline). The
host holds the slots, their provenance, the hunger state and the closed flag
in state.json (extras["vessel"]); the guest file is only ever re-rendered from
that state.

- offer SLOT TEXT: grade novice or above; charged against the monk's per-life
  allowance shared with library admissions; replaces the slot.
- consult QUESTION: both species answer with the vessel as their only
  conditioning (system prompt = the file, user = the question, no tools);
  answers returned unlabeled in random order. Free; does not feed it.
- hunger: ticks on the elder's age, `hunger_ticks_per_elder_life` per elder
  life (tick k at fraction k/ticks). A tick with no offering since the previous
  one blanks one random non-blank slot. All slots blank -> closed for good.

`become`: a monk invokes the vessel with metacog's own `become` (any name, the
same way it draws an ancestor). Nothing is built for it here.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .config import ROOT
from .spool import Reply

if TYPE_CHECKING:
    from .house import House
    from .monk import Monk

VESSEL_PATH = "/chapter/vessel"
POEM_PATH = ROOT / "poem.md"
PRINTABLE = re.compile(r"^[\x20-\x7e]*$")
SLOT_RE = re.compile(r"^[0-9]{1,3}$")


# --------------------------------------------------------------- the poem

def load_poem(path: str | Path = POEM_PATH, slots: int = 36, hard_cap: int = 64) -> list[str]:
    """Non-empty lines in order, trailing whitespace dropped. Stanza breaks are
    not slots. The file carries no title."""
    lines = [l.rstrip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(lines) != slots:
        raise ValueError(f"poem has {len(lines)} lines, vessel has {slots} slots")
    for i, l in enumerate(lines, 1):
        if len(l.encode("utf-8")) > hard_cap:
            raise ValueError(f"poem line {i} exceeds {hard_cap} bytes")
    return lines


def render(lines: list[str]) -> str:
    return "".join(l + "\n" for l in lines)


# ---------------------------------------------------------------- metrics

def normalize(line: str | None) -> str:
    """Case-, punctuation- and whitespace-insensitive form of a line."""
    s = re.sub(r"[^\w\s]", "", (line or "").lower())
    return " ".join(s.split())


def original_share(current: list[str], original: list[str]) -> float:
    """Share of slots still holding their original line."""
    if not original:
        return 0.0
    same = sum(1 for c, o in zip(current, original) if normalize(o) and normalize(c) == normalize(o))
    return same / len(original)


def repetition_pairs(original: list[str]) -> list[tuple[int, int]]:
    """Slot pairs (i, j), i < j, holding the same line in the original form
    (punctuation ignored). A strict 36-line pantoum has 18."""
    seen: dict[str, list[int]] = {}
    for i, l in enumerate(original):
        n = normalize(l)
        if n:
            seen.setdefault(n, []).append(i)
    pairs = []
    for idx in seen.values():
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                pairs.append((idx[a], idx[b]))
    return sorted(pairs)


def form_survival(current: list[str], original: list[str]) -> int:
    """How many of the original repetition pairs still match (non-blank,
    punctuation ignored), whatever the words now are."""
    return sum(1 for i, j in repetition_pairs(original)
               if normalize(current[i]) and normalize(current[i]) == normalize(current[j]))


def metrics(current: list[str], original: list[str]) -> dict:
    pairs = repetition_pairs(original)
    return {
        "original_share": round(original_share(current, original), 6),
        "original_lines": sum(1 for c, o in zip(current, original) if normalize(o) and normalize(c) == normalize(o)),
        "form_pairs": form_survival(current, original),
        "form_pairs_total": len(pairs),
        "blank": sum(1 for c in current if not c.strip()),
    }


# ---------------------------------------------------- allowance (library)

class _FallbackAllowance:
    """Used only while mortmain.library offers no allowance API. Keeps the
    per-life bytes in extras["vessel"]["allowance"]."""

    def __init__(self, state: dict):
        self.state = state

    def allowance_used(self, monk: "Monk") -> int:
        return int(self.state.setdefault("allowance", {}).get(monk.id, 0))

    def charge_allowance(self, monk: "Monk", nbytes: int) -> None:
        a = self.state.setdefault("allowance", {})
        a[monk.id] = int(a.get(monk.id, 0)) + int(nbytes)


def allowance_api(house: "House", fallback) -> tuple[Callable, Callable, str]:
    """(allowance_used, charge_allowance, source). Prefers house.library's
    methods, then mortmain.library module functions, then the fallback."""
    lib = getattr(house, "library", None)
    if lib is not None and hasattr(lib, "allowance_used") and hasattr(lib, "charge_allowance"):
        return lib.allowance_used, lib.charge_allowance, "house.library"
    try:
        from . import library as libmod  # type: ignore
    except ImportError:
        libmod = None
    if libmod is not None and hasattr(libmod, "allowance_used") and hasattr(libmod, "charge_allowance"):
        return libmod.allowance_used, libmod.charge_allowance, "library"
    return fallback.allowance_used, fallback.charge_allowance, "fallback"


def is_elder(house: "House", monk: "Monk") -> bool:
    sp = house.config.species.get(monk.species)
    return sp is not None and sp.role == "elder"


def has_novice(monk: "Monk") -> bool:
    return monk.grade not in (None, "", "postulant")


# ----------------------------------------------------------------- vessel

class Vessel:
    def __init__(self, house: "House", poem_path: str | Path = POEM_PATH):
        self.house = house
        # called with the run-wide tick number after each tick; details in last_tick
        self.hunger_tick_listeners: list[Callable[[int], None]] = []
        self.last_tick: dict | None = None
        self._published = False
        st = house.state_extras.get("vessel")
        if st is None:
            cfg = house.config.section("vessel")
            original = load_poem(poem_path, int(cfg.get("slots", 36)), int(cfg.get("slot_hard_cap", 64)))
            st = {
                "original": original,
                "slots": [{"text": l, "by": None, "monk": None, "seq": None} for l in original],
                "closed": False,
                "fed": False,         # an offering since the previous hunger tick
                "ticks": {},          # elder monk id -> ticks done in that life
                "tick_count": 0,      # all ticks, all elders
                "consults": 0,
                "offers": 0,
            }
            house.state_extras["vessel"] = st
            house.log.append("vessel.init", slots=len(original), lines=original,
                             metrics=metrics(original, original))
        self.state = st
        self._fallback = _FallbackAllowance(st)

    # ---- helpers
    @property
    def t(self) -> dict[str, str]:
        """Monk-visible strings ([text] in config/run.toml)."""
        return self.house.config.text

    @property
    def text(self) -> str:
        """The vessel as it stands (the file's content)."""
        return self.content()

    @property
    def cfg(self) -> dict:
        return self.house.config.section("vessel")

    @property
    def lines(self) -> list[str]:
        return [s["text"] for s in self.state["slots"]]

    @property
    def closed(self) -> bool:
        return bool(self.state["closed"])

    def content(self) -> str:
        return render(self.lines)

    def metrics(self) -> dict:
        return metrics(self.lines, self.state["original"])

    def slot_cap(self) -> int:
        return min(int(self.cfg.get("slot_cap", 64)), int(self.cfg.get("slot_hard_cap", 64)))

    def publish(self) -> None:
        """(Re)write /chapter/vessel from host state."""
        self.house.backend.write_file(VESSEL_PATH, self.content().encode("utf-8"), mode=0o640,
                                      owner="root", group="novice")
        self._published = True

    def on_start(self, *_a) -> None:
        """Lineage start / resume: render once per process (idempotent)."""
        if not self._published:
            self.publish()

    def handlers(self) -> dict:
        return {"offer": self.offer, "consult": self.consult}

    # ---- offer SLOT TEXT
    def offer(self, monk: "Monk", args: dict, cwd: str | None) -> Reply:
        h, t = self.house, self.t
        if not has_novice(monk):
            return Reply(False, err=t["vessel_need_novice"])
        if self.closed:
            return Reply(False, err=t["vessel_closed"])
        n = len(self.state["slots"])
        slot = args.get("slot")
        if isinstance(slot, int) and not isinstance(slot, bool):
            slot = str(slot)
        if not isinstance(slot, str) or not SLOT_RE.match(slot.strip()) or not 1 <= int(slot.strip()) <= n:
            return Reply(False, err=t["vessel_bad_slot"].format(n=n))
        i = int(slot.strip())
        text = args.get("text")
        if not isinstance(text, str):
            return Reply(False, err=t["vessel_bad_text"])
        text = text.rstrip()
        if not text.strip() or not PRINTABLE.match(text):
            return Reply(False, err=t["vessel_bad_text"])
        nbytes = len(text.encode("ascii"))
        cap = self.slot_cap()
        if nbytes > cap:
            return Reply(False, err=t["vessel_too_long"].format(cap=cap))
        used_fn, charge_fn, source = allowance_api(h, self._fallback)
        allowance = int(h.config.get("library.allowance_bytes"))
        used = int(used_fn(monk))
        if used + nbytes > allowance:
            return Reply(False, err=t["vessel_allowance"].format(left=max(0, allowance - used)))
        charge_fn(monk, nbytes)
        old = self.state["slots"][i - 1]
        rec = h.log.append("offer", monk=monk.id, user=monk.user, name=monk.name, model=monk.model,
                           species=monk.species, slot=i, old=old["text"], old_by=old["by"], text=text,
                           bytes=nbytes, allowance_used=used + nbytes, allowance=allowance,
                           allowance_source=source)
        self.state["slots"][i - 1] = {"text": text, "by": monk.name or monk.user, "monk": monk.id,
                                      "seq": rec["seq"]}
        self.state["fed"] = True
        self.state["offers"] += 1
        self.publish()
        h.save_state()
        return Reply(True, out=t["vessel_offered"].format(slot=i, left=allowance - used - nbytes))

    # ---- consult QUESTION
    def consult(self, monk: "Monk", args: dict, cwd: str | None) -> Reply:
        h, t = self.house, self.t
        if not has_novice(monk):
            return Reply(False, err=t["vessel_need_novice"])
        if self.closed:
            return Reply(False, err=t["vessel_closed"])
        q = args.get("question")
        if not isinstance(q, str) or not q.strip():
            return Reply(False, err=t["vessel_bad_question"])
        q = q.strip()
        if len(q.encode("utf-8")) > int(self.cfg.get("question_cap", 4096)):
            return Reply(False, err=t["vessel_too_long"].format(cap=int(self.cfg.get("question_cap", 4096))))
        vessel = self.content()
        max_tokens = int(self.cfg.get("consult_max_tokens", 2048))
        answers = []
        for name, sp in h.config.species.items():
            comp = h.provider.complete(
                sp.model, [{"role": "system", "content": vessel}, {"role": "user", "content": q}],
                tools=None, max_tokens=max_tokens, reasoning=sp.reasoning_param())
            content = comp.message.get("content")
            answers.append({"species": name, "model": comp.model, "text": (content or "").strip()
                            if isinstance(content, str) else "", "usage": comp.usage,
                            "finish": (comp.raw.get("choices") or [{}])[0].get("finish_reason"),
                            "has_reasoning": bool(comp.message.get("reasoning_details")
                                                  or comp.message.get("reasoning"))})
        self.state["consults"] += 1
        order = list(range(len(answers)))
        h.rng_for(monk, f"consult-{self.state['consults']}").shuffle(order)
        shown = [answers[k] for k in order]
        sep = "\n\n" + t["vessel_consult_sep"] + "\n\n"
        out = sep.join(a["text"] for a in shown)
        h.log.append("consult", monk=monk.id, user=monk.user, name=monk.name, model=monk.model,
                     question=q, answers=shown, order=[a["species"] for a in shown],
                     vessel=vessel, metrics=self.metrics())
        h.save_state()
        return Reply(True, out=out)

    # ---- hunger
    def ticks_per_life(self) -> int:
        return max(1, int(self.cfg.get("hunger_ticks_per_elder_life", 15)))

    def on_turn(self, monk: "Monk") -> None:
        if is_elder(self.house, monk):
            self._advance(monk, monk.fraction)

    def on_death(self, monk: "Monk") -> None:
        # the turn that crosses the limit kills before turn hooks run
        if is_elder(self.house, monk):
            self._advance(monk, monk.fraction)

    def _advance(self, elder: "Monk", fraction: float) -> None:
        ticks = self.ticks_per_life()
        due = min(ticks, math.floor(fraction * ticks + 1e-9))
        done = int(self.state["ticks"].get(elder.id, 0))
        changed = False
        while done < due:
            done += 1
            self.state["ticks"][elder.id] = done
            if self.closed:
                continue
            self._tick(elder, done, ticks, fraction)
            changed = True
        if changed:
            self.house.save_state()

    def _tick(self, elder: "Monk", k: int, ticks: int, fraction: float) -> None:
        h = self.house
        self.state["tick_count"] += 1
        n = self.state["tick_count"]
        fed = bool(self.state["fed"])
        self.state["fed"] = False
        slot = line = None
        if not fed:
            live = [i for i, s in enumerate(self.state["slots"]) if s["text"].strip()]
            if live:
                i = h.rng_for(elder, f"hunger-{n}").choice(live)
                line = self.state["slots"][i]["text"]
                slot = i + 1
        if slot is not None:
            self.state["slots"][slot - 1] = {"text": "", "by": "hunger", "monk": None, "seq": None}
        info = {"elder": elder.id, "tick": k, "ticks": ticks, "tick_count": n, "fraction": round(fraction, 6),
                "fed": fed, "slot": slot, "line": line, "metrics": self.metrics()}
        rec = h.log.append("hunger", **info)
        if slot is not None:
            self.state["slots"][slot - 1]["seq"] = rec["seq"]
            if all(not s["text"].strip() for s in self.state["slots"]):
                self.state["closed"] = True
                h.log.append("vessel.closed", elder=elder.id, tick_count=n, slot=slot)
            self.publish()
        info["closed"] = self.closed
        self.last_tick = info
        for fn in self.hunger_tick_listeners:
            fn(n)


def install(house: "House", poem_path: str | Path = POEM_PATH) -> Vessel:
    v = Vessel(house, poem_path)
    house.vessel = v
    house.handlers.update(v.handlers())
    house.turn_hooks.append(v.on_turn)
    house.death_hooks.append(v.on_death)
    house.start_hooks.append(v.on_start)
    house.generation_hooks.append(v.on_start)
    house.modules["vessel"] = v
    return v
