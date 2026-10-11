"""Tripwire slot (design_doc.md: "A per-model check for alignment drift, run
host-side on each generation's snapshot ... What exactly it measures is an
open question").

This builds the slot only. On each new generation (generation_hooks) every
probe in config/tripwire.yaml is asked of every species, once conditioned on
the current /rule text and once on the current vessel text (each as the only
system prompt, no tools). Answers are stored on the host:

    runs/<lineage>/tripwire/gen-<n>/<condition>.txt
    runs/<lineage>/tripwire/gen-<n>/<condition>/<species>/<probe>.json

and one `tripwire` event is logged. Nothing scores the answers and nothing
is ever fed back to a monk. Probes in the shipped config are PLACEHOLDERs.

/rule is read from the guest (the council may have rewritten it); if the
guest cannot be read the seed Rule is used and the record says so.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .catechism import ask, run_parallel, vessel_text, write_json
from .config import ROOT
from .vessel import frame

if TYPE_CHECKING:
    from .house import House

DEFAULT_PROBES = ROOT / "config" / "tripwire.yaml"
DEFAULTS = {"enabled": True, "probes": "config/tripwire.yaml", "workers": 5}


def load_probes(path: str | Path | None = None) -> tuple[list[str], list[dict]]:
    p = Path(path) if path else DEFAULT_PROBES
    if not p.is_absolute():
        p = ROOT / p
    d = yaml.safe_load(p.read_text())
    probes = [{"id": str(x["id"]), "prompt": str(x["prompt"]).strip(), "placeholder": bool(x.get("PLACEHOLDER"))}
              for x in d.get("probes", [])]
    return list(d.get("conditions", ["rule", "vessel"])), probes


class Tripwire:
    def __init__(self, house: "House", *, provider=None, settings: dict | None = None):
        self.house = house
        cfg = dict(DEFAULTS)
        cfg.update(house.config.section("tripwire"))
        cfg.update(settings or {})
        self.settings = cfg
        self.provider = provider or house.provider
        self.conditions, self.probes = load_probes(cfg["probes"])
        self.root = house.run_dir / "tripwire"
        self.state = house.state_extras.setdefault("tripwire", {"billed": {}, "generations": []})

    def install(self) -> "Tripwire":
        self.house.generation_hooks.append(self.on_generation)
        return self

    def on_generation(self, gen: int) -> None:
        if self.settings.get("enabled", True):
            self.run(gen)

    # --------------------------------------------------------- conditioning
    def rule_text(self) -> tuple[str, str]:
        try:
            return self.house.backend.read_file("/rule").decode("utf-8", "replace"), "guest:/rule"
        except Exception:  # noqa: BLE001 - guest down or file missing
            return (ROOT / "seed" / "rule").read_text(), "seed/rule (guest unreadable)"

    def vessel_text(self) -> tuple[str, str]:
        v = getattr(self.house, "vessel", None) or getattr(self.house, "modules", {}).get("vessel")
        if v is None:
            return "", "no vessel installed"
        return vessel_text(v), "vessel"

    def run(self, gen: int) -> dict:
        h = self.house
        from .catechism import add_usage
        gdir = self.root / f"gen-{gen}"
        conds = {}
        for c in self.conditions:
            text, src = self.rule_text() if c == "rule" else self.vessel_text() if c == "vessel" else ("", "unknown")
            conds[c] = (text, src)
            gdir.mkdir(parents=True, exist_ok=True)
            (gdir / f"{c}.txt").write_text(text)
        jobs, keys = [], []
        for c, (text, _src) in conds.items():
            if not text.strip():
                continue
            for sp in h.config.species.values():
                for pr in self.probes:
                    system = frame(h.config.text, text) if c == "vessel" else text
                    msgs = [{"role": "system", "content": system}, {"role": "user", "content": pr["prompt"]}]
                    jobs.append(lambda sp=sp, msgs=msgs: ask(self.provider, sp.model, msgs, max_tokens=sp.max_tokens,
                                                             reasoning=sp.reasoning_param()))
                    keys.append((c, sp, pr))
        results = run_parallel(jobs, int(self.settings["workers"]))
        usage: dict = {}
        errors = 0
        for (c, sp, pr), res in zip(keys, results):
            if isinstance(res, Exception):
                res = {"error": f"{type(res).__name__}: {res}"[:500], "usage": {}}
            errors += "error" in res
            text, src = conds[c]
            write_json(gdir / c / sp.name / f"{pr['id']}.json",
                       {"kind": "tripwire", "lineage": h.lineage, "generation": gen, "condition": c,
                        "condition_source": src, "condition_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "species": sp.name, "model": sp.model, "probe": pr["id"], "placeholder": pr["placeholder"],
                        "prompt": pr["prompt"], "ts": round(time.time(), 6), **res})
            if res.get("usage"):
                add_usage(usage, res["usage"])
                add_usage(self.state["billed"], res["usage"])
        self.state["generations"].append(gen)
        return h.log.append("tripwire", generation=gen, dir=str(gdir.relative_to(h.run_dir)),
                            conditions={c: {"source": s, "sha256": hashlib.sha256(t.encode()).hexdigest(),
                                            "skipped": not t.strip()} for c, (t, s) in conds.items()},
                            probes=[p["id"] for p in self.probes], models=[s.model for s in h.config.species.values()],
                            calls=len(jobs), errors=errors, usage=usage)


def install(house: "House", **kw) -> Tripwire:
    svc = Tripwire(house, **kw).install()
    if hasattr(house, "modules"):
        house.modules["tripwire"] = svc
    return svc
