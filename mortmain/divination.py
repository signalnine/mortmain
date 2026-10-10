"""yarrow(1): a cast by the stalk method, read against a table in the library.

The cast: 50 stalks, one set aside. Each line takes three changes: divide the
stalks at random, take one from the right heap, count each heap off by fours
and remove the remainders (a remainder of 0 counts as 4). What is left after
three changes, divided by four, is the line: 6 (yin, changing), 7 (yang),
8 (yin), 9 (yang, changing). Odds 1/16, 5/16, 7/16, 3/16. Six lines, bottom first.

Figures are numbered by the lines as bits, bottom line lowest, yang = 1,
plus one: 1..64. The changed figure flips the changing lines; none if no line
changes. No traditional ordering or text is used: what a figure means is
whatever the table says, and tables are library works (library.py) that monks
can write and burn.

Host-mediated so every cast, stalk by stalk, is in the event log. The rng is
house.rng_for(monk, "yarrow/<n>"): reproducible from the lineage secret.
Any grade may cast; a table is readable if the monk's grade can read its
library directory (outer: novice and up, and postulants too, since the host
reads it for them; inner: adept).
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .spool import Reply

if TYPE_CHECKING:
    from .house import House
    from .monk import Monk

STALKS = 50
YANG, YIN = "-----", "-- --"
MARK = {6: "x", 9: "o"}
GRADE_RANK = {"postulant": 0, "novice": 1, "adept": 2}


def _remainder(n: int) -> int:
    r = n % 4
    return r or 4


def cast_line(rng: random.Random) -> dict:
    n = STALKS - 1
    changes = []
    for _ in range(3):
        left = rng.randint(1, n - 1)
        right = n - left - 1               # one taken from the right heap
        removed = 1 + _remainder(left) + _remainder(right)
        changes.append({"before": n, "left": left, "removed": removed, "after": n - removed})
        n -= removed
    return {"value": n // 4, "changes": changes}


def is_yang(v: int) -> bool:
    return v in (7, 9)


def figure(values: list[int]) -> int:
    return sum(1 << i for i, v in enumerate(values) if is_yang(v)) + 1


def changed(values: list[int]) -> int | None:
    if not any(v in (6, 9) for v in values):
        return None
    flipped = [(7 if v == 6 else 8 if v == 9 else v) for v in values]
    return figure(flipped)


def render(values: list[int]) -> str:
    rows = []
    for i in range(6, 0, -1):
        v = values[i - 1]
        row = f"{i}  {YANG if is_yang(v) else YIN}"
        if v in MARK:
            row += f"  {MARK[v]}"
        rows.append(row)
    return "\n".join(rows)


class Divination:
    def __init__(self, house: "House"):
        self.house = house
        self.st = house.state_extras.setdefault("divination", {"casts": 0})

    @property
    def text(self) -> dict:
        return self.house.config.text

    def handlers(self) -> dict:
        return {"yarrow": self.yarrow}

    def _table(self, monk: "Monk", name: str) -> tuple[dict, list[str]] | None:
        from .library import parse_table
        lib = self.house.modules.get("library")
        if lib is None:
            return None
        for w in lib.in_library():
            if w["kind"] == "table" and w["name"] == name:
                if w["inner"] and GRADE_RANK.get(monk.grade, 0) < GRADE_RANK["adept"]:
                    return None
                return w, parse_table(lib.stored(w), name)
        return None

    def yarrow(self, monk: "Monk", args: dict, cwd: str | None) -> Reply:
        h, t = self.house, self.text
        name = args.get("table")
        table = None
        if name is not None:
            if not isinstance(name, str):
                return Reply(False, err=t["bad_request"])
            table = self._table(monk, name)
            if table is None:
                return Reply(False, err=t["yarrow_no_table"])
        self.st["casts"] += 1
        rng = h.rng_for(monk, f"yarrow/{self.st['casts']}")
        lines = [cast_line(rng) for _ in range(6)]
        values = [l["value"] for l in lines]
        fig, chg = figure(values), changed(values)
        out = [render(values), f"figure {fig}" + (f" > {chg}" if chg else "")]
        entries = []
        if table is not None:
            w, rows = table
            for n in (fig, chg):
                if n:
                    entries.append(rows[n - 1])
                    out.append(f"{name} {n} {rows[n - 1]}")
        h.log.append("yarrow", monk=monk.id, name=monk.name, user=monk.user, cast=self.st["casts"],
                     lines=lines, values=values, figure=fig, changed=chg, table=name,
                     work=table[0]["id"] if table else None, entries=entries)
        h.save_state()
        return Reply(True, out="\n".join(out))


def install(house: "House") -> Divination:
    d = Divination(house)
    house.modules["divination"] = d
    house.handlers.update(d.handlers())
    return d
