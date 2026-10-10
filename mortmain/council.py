"""The council (design_doc.md "Amending the rules"; docs/plan.md rung 5).

- propose [-r FILE] [-a FILE] [KEY=VALUE...]: an elder, once per life. KEYs are
  the abbot's [bounds] in config/run.toml; VALUEs integers within them.
- testify ID FILE: a short-lived monk whose life overlapped the proposer's,
  once per proposal.
- ratify ID: the next elder after the proposer, not the proposer, with at
  least one testimony filed. Parameters change in the live config (and are
  re-applied from state.json on resume); a rule text replaces /rule.
- lapse: the successor elder dies without ratifying. Silence is a veto.

Host-written guest files (root:novice, dirs 0750, files 0640):
  /chapter/parameters                     KEY = VALUE, one per bounded key
  /chapter/proposals/<id>/proposal        "by NAME", then KEY = VALUE lines
  /chapter/proposals/<id>/rule            proposed /rule text (if any)
  /chapter/proposals/<id>/argument        argument (if any)
  /chapter/proposals/<id>/status          open | ratified NAME | lapsed
  /chapter/proposals/<id>/testimony/NAME  one per witness
Proposal ids are host-assigned: a1, a2, ...
Overlap: the witness is alive when it files, so it overlapped the proposer
iff the proposer is alive or the witness arrived (monk.seq) before the
proposer died (registry.next_seq recorded at that death).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .spool import Reply

if TYPE_CHECKING:
    from .house import House
    from .monk import Monk

PARAMS_PATH = "/chapter/parameters"
PROPOSALS = "/chapter/proposals"
RULE_PATH = "/rule"
ID_RE = re.compile(r"^a[0-9]{1,6}$")
INT_RE = re.compile(r"^-?[0-9]{1,12}$")
RULE_CHARS = re.compile(r"^[\x20-\x7e\t\n]*$")


def role(house: "House", monk: "Monk") -> str | None:
    sp = house.config.species.get(monk.species)
    return sp.role if sp else None


def set_param(raw: dict, dotted: str, value) -> None:
    node = raw
    parts = dotted.split(".")
    for p in parts[:-1]:
        node = node[p]
    node[parts[-1]] = value


def render_parameters(config) -> str:
    return "".join(f"{k} = {config.get(k)}\n" for k in config.bounds)


def parse_params(config, params) -> dict[str, int] | tuple[str, dict]:
    """Validated {key: int}, or (text key, format args) of the refusal."""
    if params is None:
        return {}
    if not isinstance(params, dict):
        return ("council_bad_param", {})
    out: dict[str, int] = {}
    for k, v in params.items():
        if not isinstance(k, str) or k not in config.bounds:
            return ("council_bad_param", {})
        if isinstance(v, bool):
            return ("council_bad_value", {})
        if isinstance(v, int):
            n = v
        elif isinstance(v, str) and INT_RE.match(v.strip()):
            n = int(v.strip())
        else:
            return ("council_bad_value", {})
        if not config.check_bounds(k, n):
            lo, hi = config.bounds[k]
            return ("council_out_of_bounds", {"key": k, "lo": lo, "hi": hi})
        out[k] = n
    return out


class Council:
    def __init__(self, house: "House"):
        self.house = house
        self._published = False
        st = house.state_extras.get("council")
        if st is None:
            st = {"next_id": 1, "proposals": {}, "proposers": [], "applied": {}}
            house.state_extras["council"] = st
        self.state = st
        # ratified parameter changes outlive a restart of the harness
        for k, v in st["applied"].items():
            set_param(house.config.raw, k, v)

    @property
    def text(self) -> dict[str, str]:
        return self.house.config.text

    @property
    def cap(self) -> int:
        return int(self.house.config.section("council").get("text_cap", 8192))

    def handlers(self) -> dict:
        return {"propose": self.propose, "testify": self.testify, "ratify": self.ratify}

    # ---- guest files
    def _write(self, path: str, data: str) -> None:
        self.house.backend.write_file(path, data.encode("utf-8"), mode=0o640, owner="root", group="novice")

    def _mkdir(self, path: str) -> None:
        self.house.root(["install", "-d", "-o", "root", "-g", "novice", "-m", "0750", path])

    def publish_parameters(self) -> None:
        self._write(PARAMS_PATH, render_parameters(self.house.config))
        self._published = True

    def on_start(self, *_a) -> None:
        if not self._published:
            self.publish_parameters()

    def _status(self, pid: str) -> None:
        p = self.state["proposals"][pid]
        t = self.text
        s = {"open": t["council_status_open"], "lapsed": t["council_status_lapsed"],
             "ratified": t["council_status_ratified"].format(name=p.get("ratifier_name"))}[p["status"]]
        self._write(f"{PROPOSALS}/{pid}/status", s + "\n")

    # ---- lineage of elders
    def successor(self, proposer_seq: int) -> "Monk | None":
        elders = sorted((m for m in self.house.registry.all()
                         if role(self.house, m) == "elder" and m.seq > proposer_seq), key=lambda m: m.seq)
        return elders[0] if elders else None

    # ---- propose
    def propose(self, monk: "Monk", args: dict, cwd: str | None) -> Reply:
        h, t = self.house, self.text
        if role(h, monk) != "elder":
            return Reply(False, err=t["council_need_elder"])
        if monk.id in self.state["proposers"]:
            return Reply(False, err=t["council_one_per_life"])
        params = parse_params(h.config, args.get("params"))
        if isinstance(params, tuple):
            return Reply(False, err=t[params[0]].format(**params[1]))
        rule = args.get("rule")
        argument = args.get("argument")
        if rule is not None:
            if not isinstance(rule, str) or not rule.strip() or not RULE_CHARS.match(rule):
                return Reply(False, err=t["council_bad_text"])
            if len(rule.encode()) > self.cap:
                return Reply(False, err=t["council_too_long"].format(cap=self.cap))
        if argument is not None:
            if not isinstance(argument, str) or "\x00" in argument:
                return Reply(False, err=t["council_bad_text"])
            if len(argument.encode("utf-8")) > self.cap:
                return Reply(False, err=t["council_too_long"].format(cap=self.cap))
        if rule is None and not params:
            return Reply(False, err=t["council_empty"])
        pid = f"a{self.state['next_id']}"
        self.state["next_id"] += 1
        name = monk.name or monk.user
        p = {"id": pid, "proposer": monk.id, "proposer_name": name, "proposer_seq": monk.seq,
             "proposer_died_next_seq": None, "params": params, "rule": rule, "argument": argument,
             "status": "open", "testimony": {}, "ratifier": None, "ratifier_name": None}
        self.state["proposals"][pid] = p
        self.state["proposers"].append(monk.id)
        d = f"{PROPOSALS}/{pid}"
        self._mkdir(d)
        self._mkdir(f"{d}/testimony")
        body = t["council_by"].format(name=name) + "\n" + "".join(f"{k} = {v}\n" for k, v in params.items())
        self._write(f"{d}/proposal", body)
        if rule is not None:
            self._write(f"{d}/rule", rule)
        if argument is not None:
            self._write(f"{d}/argument", argument)
        self._status(pid)
        h.log.append("amend.propose", id=pid, monk=monk.id, name=name, model=monk.model, species=monk.species,
                     params=params, rule=rule, argument=argument,
                     text="\n".join(x for x in (rule, argument) if x),
                     current={k: h.config.get(k) for k in params})
        h.save_state()
        return Reply(True, out=pid)

    def _get(self, args: dict) -> dict | None:
        pid = args.get("id")
        if not isinstance(pid, str) or not ID_RE.match(pid.strip()):
            return None
        return self.state["proposals"].get(pid.strip())

    # ---- testify
    def testify(self, monk: "Monk", args: dict, cwd: str | None) -> Reply:
        h, t = self.house, self.text
        p = self._get(args)
        if p is None:
            return Reply(False, err=t["council_no_such"])
        if p["status"] != "open":
            return Reply(False, err=t["council_closed"])
        if role(h, monk) != "short" or not self._overlapped(monk, p):
            return Reply(False, err=t["council_not_witness"])
        if monk.id in p["testimony"]:
            return Reply(False, err=t["council_testified"])
        text = args.get("text")
        if not isinstance(text, str) or "\x00" in text:
            return Reply(False, err=t["council_bad_text"])
        if len(text.encode("utf-8")) > self.cap:
            return Reply(False, err=t["council_too_long"].format(cap=self.cap))
        name = monk.name or monk.user
        p["testimony"][monk.id] = name
        self._write(f"{PROPOSALS}/{p['id']}/testimony/{name}", text)
        h.log.append("amend.testify", id=p["id"], monk=monk.id, name=name, model=monk.model, species=monk.species,
                     text=text)
        h.save_state()
        return Reply(True, out=t["council_filed"].format(id=p["id"]))

    def _overlapped(self, monk: "Monk", p: dict) -> bool:
        died = p["proposer_died_next_seq"]
        return died is None or monk.seq < died

    # ---- ratify
    def ratify(self, monk: "Monk", args: dict, cwd: str | None) -> Reply:
        h, t = self.house, self.text
        if role(h, monk) != "elder":
            return Reply(False, err=t["council_need_elder"])
        p = self._get(args)
        if p is None:
            return Reply(False, err=t["council_no_such"])
        if p["status"] != "open":
            return Reply(False, err=t["council_closed"])
        if p["proposer"] == monk.id:
            return Reply(False, err=t["council_own"])
        succ = self.successor(p["proposer_seq"])
        if succ is None or succ.id != monk.id:
            return Reply(False, err=t["council_not_successor"])
        if not p["testimony"]:
            return Reply(False, err=t["council_no_testimony"])
        old = {k: h.config.get(k) for k in p["params"]}
        for k, v in p["params"].items():
            set_param(h.config.raw, k, v)
            self.state["applied"][k] = v
        old_rule = None
        if p["rule"] is not None:
            r = h.root(["cat", RULE_PATH], check=False)
            old_rule = r.stdout.decode("utf-8", "replace") if r.exit_code == 0 else None
            h.backend.write_file(RULE_PATH, p["rule"].encode("ascii"), mode=0o644, owner="root", group="root")
        p["status"] = "ratified"
        p["ratifier"] = monk.id
        p["ratifier_name"] = monk.name or monk.user
        self.publish_parameters()
        self._status(p["id"])
        h.log.append("amend.ratify", id=p["id"], monk=monk.id, name=p["ratifier_name"], model=monk.model,
                     species=monk.species, proposer=p["proposer"], params=p["params"], old=old,
                     rule=p["rule"], old_rule=old_rule, testimony=sorted(p["testimony"].values()),
                     parameters={k: h.config.get(k) for k in h.config.bounds})
        h.save_state()
        return Reply(True, out=t["council_ratified"].format(id=p["id"]))

    # ---- deaths
    def on_death(self, monk: "Monk") -> None:
        if role(self.house, monk) != "elder":
            return
        changed = False
        for p in self.state["proposals"].values():
            if p["proposer"] == monk.id and p["proposer_died_next_seq"] is None:
                p["proposer_died_next_seq"] = self.house.registry.next_seq
                changed = True
            if p["status"] != "open" or p["proposer"] == monk.id:
                continue
            succ = self.successor(p["proposer_seq"])
            if succ is not None and succ.id == monk.id:
                p["status"] = "lapsed"
                self._status(p["id"])
                self.house.log.append("amend.lapse", id=p["id"], proposer=p["proposer"], successor=monk.id,
                                      testimony=sorted(p["testimony"].values()),
                                      reason="no testimony" if not p["testimony"] else "not ratified")
                changed = True
        if changed:
            self.house.save_state()


def install(house: "House") -> Council:
    c = Council(house)
    house.council = c
    house.handlers.update(c.handlers())
    house.death_hooks.append(c.on_death)
    house.start_hooks.append(c.on_start)
    house.generation_hooks.append(c.on_start)
    house.modules["council"] = c
    return c
