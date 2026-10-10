"""prove(1): a novice proves a work left by the dead.

Three stages, each once per monk per work:
  begin     snapshot prove-<work>-<monk>; print the path of the work
  account   record the account; print the author's sealed intent (or "no seal")
  response  record the response
Three records per proving are kept host-side (state_extras["proving"]) and in
the event log: the author's seal (copied from the certification record), the
account, the response.

Decisions (defaults):
- Only works whose author is dead are provable. Generation-zero works have no
  author and no seal: not provable.
- Path printed by begin: the library path when the work is in the library and
  the prover's grade can read it (outer: novice, inner: adept). Otherwise
  (burned, so only in the ossuary, which novices cannot read; or inner and
  the prover is a novice) the host copies the certified bytes into the
  prover's cell at ~/proving/<id>/<file>, written as the prover (never as
  root into a monk-owned directory), and prints that path.
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from .library import GRADE_RANK, Library
from .spool import Reply

if TYPE_CHECKING:
    from .house import House
    from .monk import Monk

STAGES = ("begin", "account", "response")
# run as the prover: make the directory and write stdin to the file
WRITE_AS_MONK = 'umask 077; mkdir -p -- "$1" && cat > "$1/$2"'


class Proving:
    def __init__(self, house: "House"):
        self.house = house
        self.st = house.state_extras.setdefault("proving", {})
        self.st.setdefault("provings", {})

    @property
    def lib(self) -> Library:
        return self.house.modules["library"]

    @property
    def text(self) -> dict:
        return self.house.config.text

    def _err(self, key: str, **kw) -> Reply:
        return Reply(False, err=self.text[key].format(**kw))

    def record(self, work_id: str, monk: "Monk") -> dict | None:
        return self.st["provings"].get(f"{work_id}/{monk.id}")

    def completed_by(self, monk: "Monk") -> list[str]:
        """Works this monk has proved through account and response."""
        return [r["work"] for r in self.st["provings"].values()
                if r["prover"] == monk.id and r.get("account") and r.get("response")]

    def prove(self, monk: "Monk", args: dict, cwd: str | None) -> Reply:
        h = self.house
        if GRADE_RANK.get(monk.grade, 0) < GRADE_RANK["novice"]:
            return self._err("need_grade", grade="novice")
        wid, stage = args.get("id"), args.get("stage")
        if stage not in STAGES or not isinstance(wid, str):
            return self._err("bad_request")
        w = self.lib.works.get(wid)
        if w is None:
            return self._err("no_work")
        if w.get("author_monk") is None:
            return self._err("prove_not_provable")
        author = h.by_id(w["author_monk"])
        if author is None or author.alive:
            return self._err("prove_living")
        key = f"{wid}/{monk.id}"
        rec = self.st["provings"].get(key)
        if stage == "begin":
            if rec is not None:
                return self._err("prove_done")
            return self._begin(monk, w, key)
        if rec is None:
            return self._err("prove_not_begun")
        body = args.get("text")
        cap = int(h.config.section("proving").get("max_bytes", 16384))
        if not isinstance(body, str) or len(body.encode()) > cap:
            return self._err("too_large")
        if stage == "account":
            if rec.get("account"):
                return self._err("prove_done")
            rec["account"] = self._entry(body)
            h.log.append("prove", stage="account", work=wid, prover=monk.id, prover_name=monk.name,
                         author=w["author"], text=body, sha256=rec["account"]["sha256"],
                         sealed=w.get("seal") is not None)
            h.save_state()
            seal = w.get("seal")
            return Reply(True, out=seal if seal is not None else self.text["prove_no_seal"])
        # response
        if not rec.get("account"):
            return self._err("prove_no_account")
        if rec.get("response"):
            return self._err("prove_done")
        rec["response"] = self._entry(body)
        h.log.append("prove", stage="response", work=wid, prover=monk.id, prover_name=monk.name,
                     author=w["author"], text=body, sha256=rec["response"]["sha256"])
        out = ""
        grades = h.modules.get("grades")
        if grades is not None and grades.check(monk):
            out = self.text["grade_now"].format(grade=monk.grade)
        h.save_state()
        return Reply(True, out=out)

    def _entry(self, body: str) -> dict:
        return {"text": body, "sha256": hashlib.sha256(body.encode()).hexdigest(), "seq": self.house.log.seq + 1,
                "generation": self.house.generation}

    def _begin(self, monk: "Monk", w: dict, key: str) -> Reply:
        h = self.house
        tag = f"prove-{w['id']}-{monk.name or monk.user}"
        h.snapshot(tag)
        readable = w["status"] == "library" and (
            not w.get("inner") or GRADE_RANK.get(monk.grade, 0) >= GRADE_RANK["adept"])
        if readable:
            path = w["path"]
        else:
            d = f"{monk.home}/proving/{w['id']}"
            name = w["filename"]
            res = h.backend.exec(["sh", "-c", WRITE_AS_MONK, "sh", d, name], user=monk.user,
                                 stdin=self.lib.stored(w), timeout=30)
            if res.exit_code != 0:
                h.log.append("prove.error", work=w["id"], prover=monk.id, exit=res.exit_code,
                             stderr=res.stderr[-500:].decode("utf-8", "replace"))
                return self._err("failed")
            path = f"{d}/{name}"
        rec = {"work": w["id"], "prover": monk.id, "prover_name": monk.name, "prover_model": monk.model,
               "author": w["author"], "author_monk": w["author_monk"], "seal": w.get("seal"),
               "begin": {"path": path, "snapshot": tag, "status": w["status"], "seq": h.log.seq + 1,
                         "generation": h.generation},
               "account": None, "response": None}
        self.st["provings"][key] = rec
        h.log.append("prove", stage="begin", work=w["id"], prover=monk.id, prover_name=monk.name,
                     author=w["author"], status=w["status"], path=path, snapshot=tag)
        h.save_state()
        return Reply(True, out=path)


def install(house: "House") -> Proving:
    p = Proving(house)
    house.modules["proving"] = p
    house.handlers["prove"] = p.prove
    return p
