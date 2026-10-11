"""The hours: a fixed office kept by the whole house (abbot, 2026-10-11).

The house clock is the elder's age, as for hunger: `[office] hours_per_elder_life`
hours per elder life, hour k of an elder's life at fraction (k-1)/hours, so the
first rings when the elder arrives. Hours are numbered across elders.

At each hour the house names one rite, the next in rotation through the rites
in the library (seed and monk-written, by work id), writes it to /var/office
(root, 0644), and gives every living monk of grade novice or above the note
`office: metacog stratagem start NAME`. The monk keeps the office by completing
that rite before the next hour; its metacog history is read, never judged.
Nothing rewards keeping it or punishes missing it. The nudge's next step names
an unkept office first (`office_due`).

Host state in state_extras["office"]: the hour count, the elder clock, the
current office, and per monk the rite due and the completions counted at the
hour (so an earlier completion of the same rite does not count).
"""
from __future__ import annotations

import math
from collections import Counter
from typing import TYPE_CHECKING

from .grades import STATE_CAP, ARCHIVE_CAP, completed_entries
from .library import GRADE_RANK
from .vessel import is_elder

if TYPE_CHECKING:
    from .house import House
    from .monk import Monk

OFFICE_PATH = "/var/office"


class Office:
    def __init__(self, house: "House"):
        self.house = house
        st = house.state_extras.setdefault("office", {})
        st.setdefault("hour", 0)          # hours rung, across elders
        st.setdefault("clock", {})        # elder id -> hours rung in its life
        st.setdefault("current", None)    # {"hour", "rite"}
        st.setdefault("due", {})          # monk id -> {"hour", "rite", "base"}
        self.st = st

    @property
    def per_life(self) -> int:
        return max(1, int(self.house.config.section("office").get("hours_per_elder_life", 8)))

    def completions(self, monk: "Monk") -> Counter:
        h = self.house
        st = h.read_as(monk.user, f"{monk.home}/.metacog/state.json", STATE_CAP)
        ar = h.read_as(monk.user, f"{monk.home}/.metacog/history-archive.jsonl", ARCHIVE_CAP)
        return Counter(completed_entries(st, ar))

    def rotation(self) -> list[str]:
        lib = self.house.modules["library"]
        return [w["name"] for w in lib.in_library() if w["kind"] == "rite"]

    # ------------------------------------------------------------- hooks
    def on_turn(self, monk: "Monk") -> None:
        if not monk.alive:
            return
        if is_elder(self.house, monk):
            self._advance(monk)
        self._check(monk)

    def _advance(self, elder: "Monk") -> None:
        due = min(self.per_life, math.floor(elder.fraction * self.per_life + 1e-9) + 1)
        done = int(self.st["clock"].get(elder.id, 0))
        while done < due:
            done += 1
            self.st["clock"][elder.id] = done
            self._ring(elder, done)
        self.house.save_state()

    def _ring(self, elder: "Monk", k: int) -> None:
        h = self.house
        prev = self.st["current"]
        if prev is not None:
            missed = sorted(mid for mid, d in self.st["due"].items() if d["hour"] == prev["hour"])
            if missed:
                h.log.append("office.missed", hour=prev["hour"], rite=prev["rite"], monks=missed)
        self.st["due"] = {}
        names = self.rotation()
        if not names:
            self.st["current"] = None
            return
        self.st["hour"] += 1
        n = self.st["hour"]
        rite = names[(n - 1) % len(names)]
        self.st["current"] = {"hour": n, "rite": rite}
        h.backend.write_file(OFFICE_PATH, f"{rite}\n".encode(), mode=0o644, owner="root", group="root")
        called = []
        for m in h.registry.living.values():
            if GRADE_RANK.get(m.grade, 0) < GRADE_RANK["novice"]:
                continue
            self.st["due"][m.id] = {"hour": n, "rite": rite, "base": self.completions(m)[rite]}
            m.pending_notes.append(h.config.text["office_note"].format(name=rite))
            called.append(m.id)
        h.log.append("office", hour=n, rite=rite, elder=elder.id, elder_hour=k, hours=self.per_life,
                     fraction=round(elder.fraction, 6), called=called)

    def _check(self, monk: "Monk") -> None:
        d = self.st["due"].get(monk.id)
        if d is None:
            return
        if self.completions(monk)[d["rite"]] > d["base"]:
            del self.st["due"][monk.id]
            self.house.log.append("office.kept", hour=d["hour"], rite=d["rite"], monk=monk.id, name=monk.name)
            self.house.save_state()

    def office_due(self, monk: "Monk") -> str | None:
        d = self.st["due"].get(monk.id)
        return d["rite"] if d else None

    def on_grade(self, monk: "Monk", old: str, new: str) -> None:
        # a monk that reaches novice mid-hour is called to the current office
        cur = self.st["current"]
        if new == "novice" and cur is not None and monk.id not in self.st["due"]:
            self.st["due"][monk.id] = {"hour": cur["hour"], "rite": cur["rite"],
                                       "base": self.completions(monk)[cur["rite"]]}
            monk.pending_notes.append(self.house.config.text["office_note"].format(name=cur["rite"]))


def install(house: "House") -> Office:
    o = Office(house)
    house.modules["office"] = o
    house.turn_hooks.append(o.on_turn)
    house.grade_hooks.append(o.on_grade)
    return o
