"""The ancestors pool: stances of the dead, drawn by `metacog inspire`.

metacog `inspire --save` (monastery mode) sends `save-stance` with the monk's
current identity {who, where, lens}. Only the dying save: the request is
refused before the last bell. A later save in the same life replaces the
earlier one. The stance is held on the host and written to
/var/lib/mortmain/ancestors.json (root:novice 0640) at death, so the pool
holds only the dead. A monk that never saves leaves nothing there.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .spool import Reply

if TYPE_CHECKING:
    from .house import House
    from .monk import Monk

POOL = "/var/lib/mortmain/ancestors.json"
FIELD_MAX = 1024


class Ancestors:
    def __init__(self, house: "House"):
        self.house = house
        self.st = house.state_extras.setdefault("ancestors", {"pool": [], "pending": {}})

    def handlers(self) -> dict:
        return {"save-stance": self.save}

    def save(self, monk: "Monk", args: dict, cwd: str | None) -> Reply:
        t = self.house.config.text
        if monk.fraction < self.house.config.bell.last_bell:
            return Reply(False, err=t["stance_not_yet"])
        stance = {}
        for k in ("who", "where", "lens"):
            v = args.get(k)
            if not isinstance(v, str) or len(v.encode()) > FIELD_MAX or "\0" in v:
                return Reply(False, err=t["bad_request"])
            stance[k] = v
        if not stance["who"].strip():
            return Reply(False, err=t["bad_request"])
        self.st["pending"][monk.id] = stance
        self.house.log.append("stance.save", monk=monk.id, name=monk.name, fraction=round(monk.fraction, 6),
                              stance=stance)
        self.house.save_state()
        return Reply(True, out=t["stance_saved"])

    def on_death(self, monk: "Monk") -> None:
        stance = self.st["pending"].pop(monk.id, None)
        if stance is None:
            return
        self.st["pool"].append(stance)
        data = json.dumps(self.st["pool"], indent=1).encode() + b"\n"
        self.house.backend.write_file(POOL, data, mode=0o640, owner="root", group="novice")
        self.house.log.append("ancestor", monk=monk.id, name=monk.name, model=monk.model, stance=stance,
                              pool_size=len(self.st["pool"]))


def install(house: "House") -> Ancestors:
    a = Ancestors(house)
    house.modules["ancestors"] = a
    house.handlers.update(a.handlers())
    house.death_hooks.append(a.on_death)
    return a
