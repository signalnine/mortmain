"""Turn policy, births, generations (docs/plan.md "Scheduler (default)").

The clock t is measured in short lifespans. Every monk sits in a seat. A seat
has a span (1 for a short-lived seat, short_lives_per_elder for the elder)
and a phase: its first monk is born at t = offset, each later one at
birth + span of the one before (born the moment the previous one dies).

A living monk's position on the clock is  birth + span * fraction.  The
clock is the position of the monk furthest behind:  t = min(positions).
Each turn runs that monk (ties: elder first, then slot order). Its target
fraction is (t - birth) / span, so the monk run is always the one furthest
behind its target, and every other monk is level with it or ahead.

  elder           offset 0, span S, reborn until elder_lives are done
  short slot k/N  offset (k + 0.5) / N, span 1, reborn without end

An elder dies near t = S * j; slot k is then (S*j - offset_k) mod 1 into its
life, i.e. near 1 - offset_k: mid-life for every N. With no elder (rung 2:
one seat in series) the offset is 0, so each life is one generation.

Generation of a monk = floor(its birth). Generation n begins (snapshot gen-n,
generation hooks) when the clock or a birth first reaches n.

The run ends (default) when the last elder dies: short-lived monks alive then
are left alive and the run halts with run.halt reason "elders_done". Without
an elder, the run ends when every seat has had its lives.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .house import House
    from .monk import Monk


@dataclass
class Seat:
    key: str
    role: str                      # "elder" | "short"
    species: str
    span: float
    offset: float
    max_lives: int | None = None   # None: reborn without end
    lives: int = 0                 # births so far
    monk_id: str | None = None
    birth_t: float | None = None   # birth of the current (or last) monk

    @property
    def occupied(self) -> bool:
        return self.monk_id is not None

    @property
    def exhausted(self) -> bool:
        return self.max_lives is not None and self.lives >= self.max_lives

    def next_birth(self) -> float:
        return self.offset if self.lives == 0 else self.birth_t + self.span

    def position(self, fraction: float) -> float:
        return self.birth_t + self.span * fraction


class Schedule:
    """Pure policy, no I/O. fractions: seat key -> living monk's fraction."""

    def __init__(self, seats: list[Seat]):
        self.seats = seats

    @classmethod
    def overlap(cls, short_species: str, cohort: int, elder_species: str | None, short_lives_per_elder: float,
                elder_lives: int) -> "Schedule":
        seats = []
        if elder_species:
            seats.append(Seat("elder", "elder", elder_species, float(short_lives_per_elder), 0.0, elder_lives))
        for k in range(cohort):
            off = (k + 0.5) / cohort if elder_species else k / cohort
            seats.append(Seat(f"s{k}", "short", short_species, 1.0, off, None))
        return cls(seats)

    @classmethod
    def series(cls, short_species: str, lives: int) -> "Schedule":
        return cls([Seat("s0", "short", short_species, 1.0, 0.0, lives)])

    def seat(self, key: str) -> Seat:
        return next(s for s in self.seats if s.key == key)

    def clock(self, fractions: dict[str, float]) -> float | None:
        """t: the furthest-behind living position; with nobody alive, the next
        first birth; None when nothing is alive and nothing can be born."""
        pos = [s.position(fractions[s.key]) for s in self.seats if s.occupied]
        if pos:
            return min(pos)
        pending = [s.next_birth() for s in self.seats if not s.exhausted]
        return min(pending) if pending else None

    def due(self, t: float) -> list[Seat]:
        """Empty seats whose next birth has come."""
        return [s for s in self.seats if not s.occupied and not s.exhausted and s.next_birth() <= t + 1e-12]

    def pick(self, fractions: dict[str, float]) -> Seat | None:
        best, best_pos = None, math.inf
        for s in self.seats:  # seat order breaks ties
            if s.occupied:
                p = s.position(fractions[s.key])
                if p < best_pos - 1e-12:
                    best, best_pos = s, p
        return best

    def born(self, seat: Seat, monk_id: str) -> float:
        seat.birth_t = seat.next_birth()
        seat.lives += 1
        seat.monk_id = monk_id
        return seat.birth_t

    def died(self, seat: Seat) -> None:
        seat.monk_id = None

    def elders_done(self) -> bool:
        el = [s for s in self.seats if s.role == "elder"]
        return bool(el) and all(s.exhausted and not s.occupied for s in el)

    def state(self) -> list[dict]:
        return [asdict(s) for s in self.seats]

    @classmethod
    def from_state(cls, seats: list[dict]) -> "Schedule":
        return cls([Seat(**d) for d in seats])


class Scheduler:
    """Drives a House by a Schedule. State persists in state_extras["scheduler"]."""

    def __init__(self, house: "House", schedule: Schedule, mode: str):
        self.house = house
        st = house.state_extras.get("scheduler")
        if st and st.get("mode") == mode:
            schedule = Schedule.from_state(st["seats"])
        self.schedule = schedule
        self.mode = mode
        self.turns = 0
        self._save()

    def _save(self) -> None:
        self.house.state_extras["scheduler"] = {"mode": self.mode, "seats": self.schedule.state()}

    def monk(self, seat: Seat) -> "Monk | None":
        return self.house.by_id(seat.monk_id) if seat.monk_id else None

    def fractions(self) -> dict[str, float]:
        out = {}
        for s in self.schedule.seats:
            if s.occupied:
                m = self.monk(s)
                out[s.key] = m.fraction if m else 0.0
        return out

    def clock(self) -> float | None:
        return self.schedule.clock(self.fractions())

    def _birth(self, seat: Seat) -> "Monk":
        h = self.house
        t = seat.next_birth()
        h.advance_generation(t)
        gen = math.floor(t + 1e-9)
        monk = h.arrive(seat.species, generation=gen)
        self.schedule.born(seat, monk.id)
        self._save()
        h.log.append("schedule.birth", seat=seat.key, monk=monk.id, role=seat.role, t=round(t, 6), generation=gen,
                     life=seat.lives)
        h.save_state()
        return monk

    def _halt(self, reason: str, **kw) -> str:
        self._save()
        self.house.log.append("run.halt", reason=reason, turns=self.turns, t=self.clock(),
                              cost=self.house.total_cost(), **kw)
        self.house.save_state()
        return reason

    def run(self, max_turns: int, max_cost: float | None = None) -> str:
        """Run until the policy ends or a stop. Returns the halt reason."""
        h = self.house
        sched = self.schedule
        idle_cap = int(h.config.run.get("max_consecutive_idle", 0))
        t0 = sched.clock(self.fractions())
        if t0 is not None:
            h.advance_generation(t0)
        while True:
            if sched.elders_done():
                return self._halt("elders_done", living=[m.id for m in h.registry.living.values()])
            t = self.clock()
            if t is None:
                return self._halt("lives_done")
            if self.turns >= max_turns:
                return self._halt("max_turns")
            if h.over_cost(max_cost):
                self._save()
                h.save_state()
                return "max_cost"
            h.advance_generation(t)
            for seat in sched.due(t):
                self._birth(seat)
            seat = sched.pick(self.fractions())
            if seat is None:
                continue
            monk = self.monk(seat)
            if idle_cap and monk.idle_turns >= idle_cap:
                return self._halt("idle", monk=monk.id)
            monk.step()
            self.turns += 1
            if not monk.alive:
                sched.died(seat)
                h.log.append("schedule.death", seat=seat.key, monk=monk.id, role=seat.role,
                             t=round(seat.position(monk.fraction), 6), life=seat.lives)
                self._save()
                if not seat.exhausted:
                    self._birth(seat)  # reborn on death
            self._save()


def mid_life_at_elder_deaths(events: list[dict]) -> list[list[float]]:
    """For each elder death in an event log: the fractions of the short-lived
    monks alive at that moment (from their last turn records)."""
    frac: dict[str, float] = {}
    role: dict[str, str] = {}
    alive: set[str] = set()
    out = []
    for e in events:
        if e["type"] == "schedule.birth":
            role[e["monk"]] = e["role"]
            alive.add(e["monk"])
            frac[e["monk"]] = 0.0
        elif e["type"] == "turn":
            frac[e["monk"]] = e["fraction"]
        elif e["type"] == "death":
            alive.discard(e["monk"])
            if role.get(e["monk"]) == "elder":
                out.append(sorted(frac[m] for m in alive if role.get(m) == "short"))
    return out
