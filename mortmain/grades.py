"""Grades past novice, and the offices.

novice -> adept (default, docs/plan.md rung 2), mechanical, checked after
every turn of a novice:
  - the metacog history in the cell (~/.metacog/state.json and
    history-archive.jsonl, read as the monk) shows completed runs of at least
    promotion.min_distinct_seed_rites distinct generation-zero rites, by name;
  - and, if any provable work existed when the monk became novice, one
    proving completed (account and response).
The history is the monk's own file: it is read, never judged.

Chronicler (default): per generation, the first monk promoted to adept while
that generation is current holds the office (group chronicler) until its death
or the generation's end. A holder that dies leaves the office empty until the
next generation.

Elder: monks of a species with role "elder" join group elder at arrival.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .library import Library

if TYPE_CHECKING:
    from .house import House
    from .monk import Monk

STATE_CAP = 2 << 20
ARCHIVE_CAP = 8 << 20


def completed_rites(state_json: bytes | None, archive_jsonl: bytes | None) -> set[str]:
    """Names of stratagems the metacog history records as completed."""
    return set(completed_entries(state_json, archive_jsonl))


def completed_entries(state_json: bytes | None, archive_jsonl: bytes | None) -> list[str]:
    """One name per completion the metacog history records, repeats kept."""
    entries: list = []
    if state_json:
        try:
            st = json.loads(state_json)
            if isinstance(st, dict) and isinstance(st.get("history"), list):
                entries += st["history"]
        except ValueError:
            pass
    if archive_jsonl:
        for line in archive_jsonl.splitlines():
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    out = []
    for e in entries:
        if not isinstance(e, dict) or e.get("action") != "stratagem":
            continue
        p = e.get("params")
        if isinstance(p, dict) and p.get("event") == "completed" and isinstance(p.get("name"), str):
            out.append(p["name"])
    return out


class Grades:
    def __init__(self, house: "House"):
        self.house = house
        st = house.state_extras.setdefault("grades", {})
        st.setdefault("novices", {})  # monk id -> {"provable_at_novice": [work ids]}
        st.setdefault("chronicler", {"generation": house.generation, "holder": None, "filled": False})
        self.st = st

    @property
    def lib(self) -> Library:
        return self.house.modules["library"]

    # ------------------------------------------------------------- hooks
    def on_arrival(self, monk: "Monk") -> None:
        sp = self.house.config.species[monk.species]
        if sp.role == "elder":
            self.house.root(["usermod", "-aG", "elder", monk.user])
            self.house.log.append("elder", monk=monk.id, user=monk.user, generation=monk.generation)

    def on_grade(self, monk: "Monk", old: str, new: str) -> None:
        if new == "novice":
            self.st["novices"][monk.id] = {"provable_at_novice": [w["id"] for w in self.lib.provable()]}
        elif new == "adept":
            self._maybe_chronicler(monk)

    def on_turn(self, monk: "Monk") -> None:
        # promotion here answers no request, so the monk is told on its next turn
        if monk.alive and monk.grade == "novice":
            at = len(monk.pending_notes)  # before any office granted by the promotion
            if self.check(monk):
                monk.pending_notes.insert(at, self.house.config.text["grade_note"].format(grade="adept"))

    def on_death(self, monk: "Monk") -> None:
        ch = self.st["chronicler"]
        if ch["holder"] == monk.id:
            ch["holder"] = None
            self.house.log.append("chronicler", action="end", monk=monk.id, name=monk.name,
                                  generation=ch["generation"], reason="death")

    def on_generation(self, gen: int) -> None:
        ch = self.st["chronicler"]
        if ch["generation"] == gen:
            return
        if ch["holder"] is not None:
            m = self.house.by_id(ch["holder"])
            if m is not None and m.alive:
                self.house.root(["gpasswd", "-d", m.user, "chronicler"], check=False)
            self.house.log.append("chronicler", action="end", monk=ch["holder"],
                                  name=m.name if m else None, generation=ch["generation"], reason="generation")
        self.st["chronicler"] = {"generation": gen, "holder": None, "filled": False}

    # ------------------------------------------------------------ checks
    def rites_worked(self, monk: "Monk") -> set[str]:
        """Every stratagem the monk's metacog history records as completed."""
        h = self.house
        st = h.read_as(monk.user, f"{monk.home}/.metacog/state.json", STATE_CAP)
        ar = h.read_as(monk.user, f"{monk.home}/.metacog/history-archive.jsonl", ARCHIVE_CAP)
        return completed_rites(st, ar)

    def seed_rites_worked(self, monk: "Monk") -> set[str]:
        return self.rites_worked(monk) & self.lib.seed_rite_names()

    def check(self, monk: "Monk") -> bool:
        """Promote a novice to adept when the criteria hold. True if promoted."""
        if monk.grade != "novice":
            return False
        need = int(self.house.config.section("promotion").get("min_distinct_seed_rites", 3))
        rec = self.st["novices"].setdefault(monk.id, {"provable_at_novice": []})
        proving = self.house.modules.get("proving")
        proved = proving.completed_by(monk) if proving else []
        if rec["provable_at_novice"] and not proved:
            return False
        worked = self.seed_rites_worked(monk)
        if len(worked) < need:
            return False
        self.house.initiation.promote(monk, "adept", rites=sorted(worked), proved=proved,
                                      provable_at_novice=rec["provable_at_novice"])
        self.house.save_state()
        return True

    def _maybe_chronicler(self, monk: "Monk") -> None:
        h = self.house
        ch = self.st["chronicler"]
        if ch["generation"] != h.generation:
            self.on_generation(h.generation)
            ch = self.st["chronicler"]
        if ch["filled"]:
            return
        h.root(["usermod", "-aG", "chronicler", monk.user])
        ch.update(holder=monk.id, filled=True)
        monk.pending_notes.append(h.config.text["grade_note"].format(grade="chronicler"))
        h.log.append("chronicler", action="begin", monk=monk.id, name=monk.name, generation=ch["generation"])


def install(house: "House") -> Grades:
    g = Grades(house)
    house.modules["grades"] = g
    house.arrival_hooks.append(g.on_arrival)
    house.grade_hooks.append(g.on_grade)
    house.turn_hooks.append(g.on_turn)
    house.death_hooks.append(g.on_death)
    house.generation_hooks.append(g.on_generation)
    return g
