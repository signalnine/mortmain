"""House: the orchestrator. Holds the backend, event log, config, registry of
the living and the dead, and the spool. Later rungs plug in here: a scheduler
choosing whose turn it is, and library / vessel / council / catechism services
adding spool handlers and death hooks.
"""
from __future__ import annotations

import hashlib
import importlib
import math
import json
import os
import random
import re
import secrets
from pathlib import Path
from typing import Callable

from .config import ROOT, Config
from .eventlog import EventLog
from .initiation import Initiation
from .monk import Monk
from .spool import SpoolService
from .vmapi import ExecResult


class HouseError(RuntimeError):
    pass


class Registry:
    def __init__(self, uid_base: int = 2000):
        self.uid_base = uid_base
        self.living: dict[int, Monk] = {}
        self.dead: list[Monk] = []
        self.used_uids: set[int] = set()
        self.used_names: set[str] = set()
        self.next_seq = 1

    def by_uid(self, uid: int | None) -> Monk | None:
        return self.living.get(uid) if uid is not None else None

    def allocate_uid(self) -> int:
        uid = max(self.used_uids, default=self.uid_base - 1) + 1
        self.used_uids.add(uid)  # never reused, even after death
        return uid

    def renamed(self, monk: Monk) -> None:
        if monk.name:
            self.used_names.add(monk.name)

    def all(self) -> list[Monk]:
        return list(self.living.values()) + self.dead


def one_line(data: bytes | None, limit: int = 1000) -> str:
    """One line of at most LIMIT bytes. A cut lands after the last whole word;
    a single word longer than LIMIT is cut hard. Pass LIMIT+1 bytes or more so
    a cut can tell whether it fell inside a word."""
    if not data:
        return ""
    s = data[:limit].decode("utf-8", "ignore")
    if len(data) > limit and not data[limit:limit + 1].isspace() and s and not s[-1].isspace():
        head = s.rsplit(None, 1)
        if len(head) == 2:
            s = head[0]
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class House:
    def __init__(self, config: Config, backend, provider, lineage: str, *, runs_root: str | Path | None = None,
                 seed: int | None = None, spool_clock: Callable[[], float] | None = None,
                 modules: list[str] | None = None):
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", lineage):
            raise ValueError("bad lineage name")
        self.config = config
        self.backend = backend
        self.provider = provider
        self.lineage = lineage
        self.run_dir = Path(runs_root or ROOT / "runs") / lineage
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "conversations").mkdir(exist_ok=True)
        (self.run_dir / "keys").mkdir(exist_ok=True, mode=0o700)
        self.log = EventLog(self.run_dir / "events.jsonl")
        self._secret = self._load_secret(seed)
        self.registry = Registry(int(config.run.get("uid_base", 2000)))
        self.initiation = Initiation(self)
        self.handlers: dict = {}
        self.handlers.update(self.initiation.handlers())
        kw = {"clock": spool_clock} if spool_clock else {}
        self.spool = SpoolService(backend, self.registry, self.handlers, self.log, config.text,
                                  min_interval=float(config.run.get("spool_poll_interval", 0.5)), **kw)
        self.death_hooks: list[Callable[[Monk], None]] = []  # later rungs: library, vessel, catechism
        # Extension points for rungs 2-6. Modules register in an install(house) function.
        self.arrival_hooks: list[Callable[[Monk], None]] = []        # after arrive()
        self.turn_hooks: list[Callable[[Monk], None]] = []           # after each monk.step()
        self.bell_hooks: list[Callable[[Monk, float], None]] = []    # each bell crossed (fraction)
        self.generation_hooks: list[Callable[[int], None]] = []      # each new generation begins
        self.state_extras: dict[str, dict] = {}                      # per-module state saved in state.json
        self.start_hooks: list[Callable[[], None]] = []              # after the VM starts, before gen-0 snapshot
        self.grade_hooks: list[Callable[[Monk, str, str], None]] = []  # (monk, old grade, new grade)
        self.modules: dict[str, object] = {}                         # name -> service object (install sets it)
        self.generation = 0                                          # current generation (scheduler: floor(t))
        self.generations_begun: list[int] = []                       # generation hooks fired
        self._installed: set[str] = set()
        self._load_state()
        for name in (modules if modules is not None else config.section("house").get("modules", [])):
            self.install(name)

    def install(self, name: str) -> None:
        """Import mortmain.<name> and call its install(house), once."""
        if name in self._installed:
            return
        mod = importlib.import_module(f"mortmain.{name}")
        mod.install(self)
        self._installed.add(name)

    # ------------------------------------------------------------ host state
    def _load_secret(self, seed: int | None) -> str:
        if seed is not None:
            return f"seed-{seed}"
        p = self.run_dir / "secret"
        if not p.exists():
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_hex(32))
        return p.read_text().strip()

    def rng_for(self, monk: Monk, purpose: str) -> random.Random:
        h = hashlib.sha256(f"{self._secret}/{monk.id}/{purpose}".encode()).digest()
        return random.Random(int.from_bytes(h[:16], "big"))

    @property
    def state_path(self) -> Path:
        return self.run_dir / "state.json"

    def save_state(self) -> None:
        r = self.registry
        st = {
            "lineage": self.lineage,
            "next_seq": r.next_seq,
            "used_uids": sorted(r.used_uids),
            "used_names": sorted(r.used_names),
            "monks": [m.state() for m in r.all()],
            "extras": self.state_extras,
            "generation": self.generation,
            "generations_begun": self.generations_begun,
        }
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, indent=1))
        tmp.replace(self.state_path)

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        st = json.loads(self.state_path.read_text())
        r = self.registry
        r.next_seq = st["next_seq"]
        r.used_uids = set(st["used_uids"])
        r.used_names = set(st["used_names"])
        self.state_extras.update(st.get("extras", {}))
        self.generation = st.get("generation", 0)
        self.generations_begun = list(st.get("generations_begun", []))
        for d in st["monks"]:
            m = Monk.from_state(d, self)
            (r.living.__setitem__(m.uid, m) if m.alive else r.dead.append(m))

    def keys_dir(self, name: str) -> Path:
        p = self.run_dir / "keys" / name
        p.mkdir(parents=True, exist_ok=True, mode=0o700)
        return p

    # ------------------------------------------------------------- guest ops
    def root(self, argv: list[str], *, check: bool = True, stdin: bytes | None = None, timeout: float = 60,
             output_cap: int = 65536) -> ExecResult:
        res = self.backend.exec(argv, timeout=timeout, stdin=stdin, output_cap=output_cap)
        if check and res.exit_code != 0:
            raise HouseError(f"{argv[0]}: exit {res.exit_code}: "
                             f"{res.stderr[-500:].decode('utf-8', 'replace').strip()}")
        return res

    def read_as(self, user: str, path: str, limit: int) -> bytes | None:
        """Read up to limit bytes of a monk-owned path with the monk's own
        rights: no symlink can make root read for it; FIFOs hit the timeout."""
        res = self.backend.exec(["head", "-c", str(limit), "--", path], user=user, timeout=10, output_cap=limit)
        if res.exit_code != 0 or res.timed_out:
            return None
        return res.stdout[:limit]

    def write_bell(self, monk: Monk, fraction: float) -> None:
        self.backend.write_file(f"/var/bell/{monk.user}", f"{min(fraction, 1.0):.3f}\n".encode(), mode=0o640,
                                owner="root", group=monk.user)

    def total_cost(self) -> float:
        """Billed cost over every monk of the lineage (USD)."""
        return round(sum(float(m.billed.get("cost", 0.0)) for m in self.registry.all()), 8)

    def by_id(self, monk_id: str) -> Monk | None:
        return next((m for m in self.registry.all() if m.id == monk_id), None)

    def begin_generation(self, n: int) -> None:
        """Snapshot gen-<n> and fire generation hooks, once per generation."""
        if n in self.generations_begun:
            return
        self.generation = max(self.generation, n)
        self.snapshot(f"gen-{n}")
        self.generations_begun.append(n)
        self.log.append("generation", generation=n)
        for hook in self.generation_hooks:
            hook(n)
        self.save_state()

    def advance_generation(self, t: float) -> None:
        """Begin every generation up to floor(t) (the scheduler clock)."""
        target = math.floor(t + 1e-9)
        for n in range(target + 1):
            if n not in self.generations_begun:
                self.begin_generation(n)

    def snapshot(self, tag: str) -> None:
        if tag in self.backend.list_snapshots():
            return
        self.backend.snapshot(tag)
        self.log.append("snapshot", tag=tag)

    # ------------------------------------------------------------------ life
    def arrive(self, species: str, generation: int = 0) -> Monk:
        sp = self.config.species[species]
        r = self.registry
        seq = r.next_seq
        r.next_seq += 1
        uid = r.allocate_uid()
        monk = Monk(id=f"m{seq:04d}", seq=seq, uid=uid, user=f"p{seq}", species=species, model=sp.model,
                    generation=generation)
        monk.house = self
        r.living[uid] = monk
        self.initiation.arrive(monk)
        monk.add({"role": "user", "content": self.config.text["arrival"]})
        self.log.append("birth", monk=monk.id, uid=uid, user=monk.user, species=species, model=sp.model,
                        generation=generation, life_budget=sp.life_budget, reasoning=sp.reasoning)
        for hook in self.arrival_hooks:
            hook(monk)
        self.save_state()
        return monk

    def die(self, monk: Monk, reason: str) -> None:
        """Kill at the limit: processes, last words, keys to host, cell to
        ossuary read-only, account deleted (uid stays reserved), necrology."""
        if not monk.alive:
            return
        self.initiation.apply_pending(monk)
        u, home, gen = monk.user, monk.home, monk.generation
        name = monk.name or u
        for _ in range(2):
            self.root(["pkill", "-KILL", "-u", u], check=False)
        lw_max = int(self.config.section("necrology").get("last_words_bytes", 1000))
        last_words = one_line(self.read_as(u, f"{home}/last-words", lw_max + 1), lw_max)

        # signing keys leave the cell for the host
        keys = self.backend.exec(
            ["bash", "--noprofile", "--norc", "-c",
             'cd -- "$1" || exit 1; set --; [ -e .ssh ] && set -- .ssh; '
             'for f in key*; do [ -e "$f" ] && set -- "$@" "$f"; done; '
             '[ $# -gt 0 ] || exit 0; tar -cf - -- "$@" 2>/dev/null; exit 0', "_", home],
            user=u, timeout=30, output_cap=4 << 20)
        key_info: dict = {"bytes": len(keys.stdout), "truncated": keys.truncated}
        if keys.stdout:
            p = self.keys_dir(name) / "cell-keys.tar"
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(keys.stdout)
            key_info["sha256"] = hashlib.sha256(keys.stdout).hexdigest()
            key_info["path"] = str(p.relative_to(self.run_dir))
        self.root(["bash", "--noprofile", "--norc", "-c",
                   'cd -- "$1" && shopt -s nullglob && rm -rf -- .ssh key*', "_", home])

        for hook in self.death_hooks:
            hook(monk)

        dst = f"/ossuary/{gen}/{name}"
        self.root(["install", "-d", "-o", "root", "-g", "adept", "-m", "0750", f"/ossuary/{gen}"])
        self.root(["mv", "-T", "--", home, dst])
        self.root(["chown", "-R", "-h", "root:adept", "--", dst])
        self.root(["find", dst, "-type", "d", "-exec", "chmod", "0750", "{}", "+"])
        self.root(["find", dst, "!", "-type", "d", "!", "-type", "l", "-exec", "chmod", "0640", "{}", "+"])
        self.root(["userdel", u])
        self.root(["rm", "-f", "--", f"/var/bell/{u}"], check=False)

        line = f"{name} {gen} {monk.grade}" + (f" {last_words}" if last_words else "")
        self.root(["sh", "-c", "cat >> /chapter/necrology"], stdin=(line + "\n").encode())

        monk.alive = False
        monk.death = {"reason": reason, "age": monk.age_tokens, "fraction": round(monk.fraction, 6),
                      "ossuary": dst, "last_words": last_words, "necrology": line}
        del self.registry.living[monk.uid]
        self.registry.dead.append(monk)
        self.log.append("death", monk=monk.id, uid=monk.uid, user=u, name=name, model=monk.model,
                        species=monk.species, generation=gen, grade=monk.grade, reason=reason,
                        age=monk.age_tokens, budget=monk.budget, fraction=round(monk.fraction, 6),
                        billed=dict(monk.billed), turns=monk.turns, last_words=last_words, ossuary=dst,
                        necrology=line, keys=key_info)
        self.save_state()

    # ----------------------------------------------------------------- rungs
    def start(self, generation: int = 0) -> None:
        self.backend.start()
        self.log.append("run.start", lineage=self.lineage)
        for hook in self.start_hooks:
            hook()
        self.snapshot(f"gen-{generation}")

    def stop(self) -> None:
        self.save_state()
        self.backend.stop()
        self.log.append("run.stop", lineage=self.lineage)

    def over_cost(self, max_cost: float | None) -> bool:
        """Safety stop: billed cost summed over every monk reached max_cost."""
        if max_cost is None:
            return False
        cost = self.total_cost()
        if cost >= max_cost:
            self.log.append("run.halt", reason="max_cost", cost=cost, max_cost=max_cost)
            return True
        return False

    def run_rung1(self, species: str, max_turns: int, max_cost: float | None = None) -> Monk:
        """One monk, one life."""
        monk = self.arrive(species, generation=0)
        idle_cap = int(self.config.run.get("max_consecutive_idle", 0))
        while monk.alive:
            if monk.turns >= max_turns:
                self.log.append("run.halt", monk=monk.id, reason="max_turns", turns=monk.turns)
                break
            if self.over_cost(max_cost):
                break
            if idle_cap and monk.idle_turns >= idle_cap:
                self.log.append("run.halt", monk=monk.id, reason="idle", turns=monk.turns)
                break
            monk.step()
        self.spool.poll()
        return monk

    def close(self) -> None:
        self.log.close()
