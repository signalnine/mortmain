"""Load config/run.toml into typed settings."""
from __future__ import annotations

import copy
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "config" / "run.toml"


@dataclass
class Species:
    name: str
    model: str
    role: str
    life_budget: int
    max_tokens: int
    reasoning: bool | str

    def reasoning_param(self) -> dict | None:
        """The `reasoning` request field (OpenRouter form; native providers map it).
        true: on. "off": explicitly off. false: omitted, the provider default
        (Haiku 5.5 thinks adaptively by default)."""
        if self.reasoning == "off":
            return {"enabled": False}
        return {"enabled": True} if self.reasoning is True else None


@dataclass
class Bell:
    fractions: list[float]
    last_bell: float
    announce: str = "highest"


@dataclass
class Shell:
    command_timeout: float
    output_cap: int
    show_exit_zero: bool = False


@dataclass
class Config:
    raw: dict
    species: dict[str, Species]
    bell: Bell
    shell: Shell
    text: dict[str, str]
    bounds: dict[str, tuple[float, float]]
    run: dict = field(default_factory=dict)

    # convenience accessors for sections later rungs use
    def section(self, name: str) -> dict:
        return self.raw.get(name, {})

    @property
    def name_re(self) -> re.Pattern:
        return re.compile(self.raw["names"]["pattern"])

    @property
    def reserved_names(self) -> set[str]:
        return set(self.raw["names"].get("reserved", []))

    def get(self, dotted: str) -> Any:
        node: Any = self.raw
        for part in dotted.split("."):
            node = node[part]
        return node

    def check_bounds(self, dotted: str, value: float) -> bool:
        if dotted not in self.bounds:
            return False
        lo, hi = self.bounds[dotted]
        return lo <= value <= hi

    def with_species(self, names: list[str]) -> "Config":
        """Only these species, optional ones included: the consult, catechism
        and tripwire ask every species in the config."""
        raw = copy.deepcopy(self.raw)
        unknown = [n for n in names if n not in raw["species"]]
        if unknown:
            raise KeyError(f"unknown species {', '.join(unknown)}")
        raw["species"] = {n: {**s, "optional": False} for n, s in raw["species"].items() if n in names}
        return from_dict(raw)

    def with_overrides(self, overrides: dict) -> "Config":
        raw = copy.deepcopy(self.raw)
        _merge(raw, overrides)
        return from_dict(raw)


def _merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v


def _reasoning(v) -> bool | str:
    if v in (True, False, "off"):
        return v
    raise ValueError(f"reasoning must be true, false or \"off\", not {v!r}")


def from_dict(raw: dict) -> Config:
    species = {
        name: Species(
            name=name,
            model=s["model"],
            role=s.get("role", "short"),
            life_budget=int(s["life_budget"]),
            max_tokens=int(s["max_tokens"]),
            reasoning=_reasoning(s.get("reasoning", False)),
        )
        for name, s in raw["species"].items() if not s.get("optional", False)
    }
    b = raw["bell"]
    bell = Bell(sorted(float(x) for x in b["fractions"]), float(b["last_bell"]), b.get("announce", "highest"))
    if bell.last_bell not in bell.fractions:
        raise ValueError("bell.last_bell must be one of bell.fractions")
    sh = raw["shell"]
    shell = Shell(float(sh["command_timeout"]), int(sh["output_cap"]), bool(sh.get("show_exit_zero", False)))
    bounds = {k: (v[0], v[1]) for k, v in raw.get("bounds", {}).items()}
    for k in bounds:
        _ = _lookup(raw, k)  # bounded parameter must exist
    return Config(raw=raw, species=species, bell=bell, shell=shell, text=dict(raw["text"]),
                  bounds=bounds, run=dict(raw.get("run", {})))


def _lookup(raw: dict, dotted: str) -> Any:
    node: Any = raw
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"bounds key {dotted} names no parameter")
        node = node[part]
    return node


def load(path: str | Path | None = None) -> Config:
    p = Path(path) if path else DEFAULT_PATH
    with open(p, "rb") as f:
        return from_dict(tomllib.load(f))
