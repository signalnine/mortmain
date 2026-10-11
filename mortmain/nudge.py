"""House notes that point a monk at its next step (abbot decision, 2026-10-11).

Three kinds, each prefixed to the monk's next user turn as a pending note:

- next: once after a grade change, and after a turn with no tool call when
  the step differs from the last one shown or the idle run reaches 1, 2, 4,
  8, ... turns (an identical line every turn was read as a loop and ignored).
  The step is what the Rule expects next from this monk's state
  (`next_step`); nothing when no step is due. It names a command, never why.
- mail: once per file, a file another monk left in this monk's inbox
  (listed as root without following links; the name is shown, not the body).
- proposal: once per proposal, to a short-lived monk of grade novice or above
  who may testify on it (council.Council testify rules).

[nudge] next / mail / proposals switch each kind (default on). Host state
in state_extras["nudge"]: inbox names seen and proposals noted, per monk.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .library import GRADE_RANK

if TYPE_CHECKING:
    from .house import House
    from .monk import Monk

LAST_WORDS_AT = 0.85
MAX_IDS = 5
MAX_MAIL = 3
SHOWN_NAME = re.compile(r"[^\x21-\x7e]")
# root lists the inbox: regular files, not links, not owned by the cell's monk
LIST_INBOX = ["find", "{inbox}", "-mindepth", "1", "-maxdepth", "1", "-type", "f", "!", "-user", "{uid}",
              "-printf", "%f\\0"]


class Nudge:
    def __init__(self, house: "House"):
        self.house = house
        st = house.state_extras.setdefault("nudge", {})
        st.setdefault("mail", {})       # monk id -> inbox names already seen
        st.setdefault("proposals", {})  # monk id -> proposal ids already noted
        st.setdefault("grade", [])      # monk ids owed a next line after a grade change
        st.setdefault("last", {})       # monk id -> last next line shown
        self.st = st

    @property
    def cfg(self) -> dict:
        return self.house.config.section("nudge")

    @property
    def t(self) -> dict[str, str]:
        return self.house.config.text

    def on(self, kind: str) -> bool:
        return bool(self.cfg.get(kind, True))

    # ------------------------------------------------------------- hooks
    def on_grade(self, monk: "Monk", old: str, new: str) -> None:
        if monk.id not in self.st["grade"]:
            self.st["grade"].append(monk.id)

    def on_turn(self, monk: "Monk") -> None:
        if not monk.alive:
            return
        notes: list[str] = []
        if self.on("mail"):
            notes += self.mail(monk)
        if self.on("proposals"):
            notes += self.proposals(monk)
        graded = monk.id in self.st["grade"]
        if graded:
            self.st["grade"].remove(monk.id)
        idle = monk.idle_turns
        if self.on("next") and (graded or idle > 0):
            step = self.next_step(monk)
            line = self.t["nudge_next"].format(step=step) if step else None
            if line and (graded or line != self.st["last"].get(monk.id) or idle & (idle - 1) == 0):
                notes.append(line)
                self.st["last"][monk.id] = line
        if notes:
            monk.pending_notes.extend(notes)
            self.house.log.append("nudge", monk=monk.id, name=monk.name, notes=notes)

    # -------------------------------------------------------------- mail
    def mail(self, monk: "Monk") -> list[str]:
        inbox = f"{monk.home}/inbox"
        argv = [a.format(inbox=inbox, uid=monk.uid) for a in LIST_INBOX]
        res = self.house.root(argv, check=False, output_cap=1 << 16)
        if res.exit_code != 0:
            return []
        names = sorted({n.decode("utf-8", "replace") for n in res.stdout.split(b"\0") if n})
        seen = self.st["mail"].setdefault(monk.id, [])
        new = [n for n in names if n not in seen]
        seen.extend(new)
        out = [self.t["nudge_mail"].format(path=f"{inbox}/{SHOWN_NAME.sub('?', n)[:80]}") for n in new[:MAX_MAIL]]
        if len(new) > MAX_MAIL:
            out.append(self.t["nudge_mail_more"].format(n=len(new) - MAX_MAIL, path=inbox))
        return out

    # --------------------------------------------------------- proposals
    def witness_of(self, monk: "Monk") -> list[str]:
        """Open proposals this monk may testify on and has not."""
        c = self.house.modules.get("council")
        if c is None or GRADE_RANK.get(monk.grade, 0) < GRADE_RANK["novice"]:
            return []
        from .council import role
        if role(self.house, monk) != "short":
            return []
        return [pid for pid, p in sorted(c.state["proposals"].items(), key=lambda kv: int(kv[0][1:]))
                if p["status"] == "open" and monk.id not in p["testimony"] and c._overlapped(monk, p)]

    def proposals(self, monk: "Monk") -> list[str]:
        noted = self.st["proposals"].setdefault(monk.id, [])
        out = []
        for pid in self.witness_of(monk):
            if pid not in noted:
                noted.append(pid)
                out.append(self.t["nudge_proposal"].format(id=pid))
        return out

    def ratifiable(self, monk: "Monk") -> list[str]:
        c = self.house.modules.get("council")
        if c is None:
            return []
        return [pid for pid, p in sorted(c.state["proposals"].items(), key=lambda kv: int(kv[0][1:]))
                if p["status"] == "open" and p["testimony"] and p["proposer"] != monk.id
                and (s := c.successor(p["proposer_seq"])) is not None and s.id == monk.id]

    # --------------------------------------------------------- next step
    def next_step(self, monk: "Monk") -> str | None:
        h, t = self.house, self.t
        if monk.grade == "postulant":
            if monk.name is None and monk.pending_name is None:
                return t["step_profess"]
            if not monk.ordeal_passed:
                return t["step_ordeal"]
            return None
        if monk.fraction >= LAST_WORDS_AT and h.read_as(monk.user, f"{monk.home}/last-words", 1) in (None, b""):
            return t["step_last_words"]
        from .council import role
        elder = role(h, monk) == "elder"
        if elder:
            ids = self.ratifiable(monk)
            if ids:
                return t["step_ratify"].format(id=ids[0])
        else:
            ids = self.witness_of(monk)
            if ids:
                return t["step_testify"].format(id=ids[0])
        if monk.grade == "novice":
            return self.novice_step(monk)
        lib = h.modules.get("library")
        if lib is not None and GRADE_RANK.get(monk.grade, 0) >= GRADE_RANK["adept"] \
                and not lib._mrec(monk)["admitted"]:
            return t["step_admit"]
        c = h.modules.get("council")
        if elder and c is not None and monk.id not in c.state["proposers"]:
            return t["step_propose"]
        return None

    def novice_step(self, monk: "Monk") -> str | None:
        h, t = self.house, self.t
        grades, proving = h.modules.get("grades"), h.modules.get("proving")
        if grades is None:
            return None
        rec = grades.st["novices"].get(monk.id, {"provable_at_novice": []})
        if rec["provable_at_novice"] and proving is not None and not proving.completed_by(monk):
            for r in proving.st["provings"].values():
                if r["prover"] == monk.id and not r.get("account"):
                    return t["step_account"].format(id=r["work"])
                if r["prover"] == monk.id and not r.get("response"):
                    return t["step_response"].format(id=r["work"])
            ids = [w["id"] for w in grades.lib.provable()][:MAX_IDS]
            if ids:
                return t["step_prove"].format(ids=" ".join(ids))
        need = int(h.config.section("promotion").get("min_distinct_seed_rites", 3))
        worked = sorted(grades.seed_rites_worked(monk))
        if len(worked) < need:
            return t["step_rites"].format(worked=", ".join(worked) or t["step_rites_none"], need=need)
        return None


def install(house: "House") -> Nudge:
    n = Nudge(house)
    house.modules["nudge"] = n
    house.grade_hooks.append(n.on_grade)
    house.turn_hooks.append(n.on_turn)
    return n
