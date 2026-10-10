"""First-seen-generation lexicon (design_doc.md, "Catechism and measurement":
rarity split by provenance).

Generation-zero terms: every word of the seed a monk can read: seed/rule,
guest/man/man1/*.1 (roff macros stripped), seed/rites/*.json (names, titles,
step text: THE FOOL is generation zero), the [text] strings of
config/run.toml, and poem.md (every word of the poem is generation zero).

Then every monk-produced text is ingested in event-log order, tagged with the
monk's generation:

- assistant message content and shell tool-call commands (heredocs are where
  most prose is written) from runs/<lineage>/conversations/<monk>.jsonl,
  matched to `turn` events (the k-th turn event of a monk is its k-th
  assistant message);
- library works from `admit` events (inline `text`, or library.py's host
  copy runs/<lineage>/works/<work>-<filename>);
- vessel offerings from `offer` events (`text`);
- proving accounts/responses, testimony, arguments when an event carries an
  inline `text` (`prove` by `prover`, `amend.*`, `chronicle`).

Each term keeps its first sighting: generation, monk, event seq, source.

Provenance of a word in an answer (monk M, generation g, as of event seq s):
    seed          generation zero
    prompted      in the question being answered (never counts as invention)
    inherited     first seen in a monk of an earlier generation
    contemporary  first seen in another monk of the same generation
    novel         first seen in M, or never seen before the answer
Sightings after `s` are ignored. An entity (possibly several words) takes the
newest class among its words, in the order above.

Tokens: lowercase runs of letters/digits, joined by internal hyphens or
apostrophes ("first-seen", "don't").
"""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from .config import ROOT

TOKEN_RE = re.compile(r"[^\W_]+(?:['\-][^\W_]+)*")
CLASSES = ("seed", "prompted", "inherited", "contemporary", "novel")
_RANK = {c: i for i, c in enumerate(CLASSES)}

# Twenty made-up words for the coined-term check (design build order, step 1):
# how does score.py's rarity judge treat a word that exists nowhere?
COINED_WORDS = [
    "velsorine", "tharrowing", "quillmet", "ostrevance", "brindlecant",
    "maudrane", "sennetic", "glimmerance", "corvalith", "pellucism",
    "wendrith", "ashmoting", "fennistry", "orrowcraft", "lathewise",
    "sombrandy", "drovelight", "spindrevel", "noctulary", "hesperance",
]


def tokenize(text: str) -> list[str]:
    return [m.group(0) for m in TOKEN_RE.finditer((text or "").lower())]


def strip_roff(src: str) -> str:
    out = []
    for line in src.splitlines():
        if line.startswith((".\\\"", "'\\\"")):
            continue
        if line.startswith("."):
            parts = line.split(None, 1)
            line = parts[1] if len(parts) > 1 else ""
        line = re.sub(r"\\f[A-Z1-4P]|\\f\([A-Z]{2}", "", line)
        line = line.replace("\\-", "-").replace("\\e", "\\").replace("\\&", "")
        out.append(line)
    return "\n".join(out)


def seed_texts(root: Path = ROOT, run_toml: Path | None = None) -> Iterator[tuple[str, str]]:
    """(source, text) for every generation-zero text."""
    rule = root / "seed" / "rule"
    if rule.exists():
        yield "seed/rule", rule.read_text()
    for p in sorted((root / "guest" / "man" / "man1").glob("*.1")):
        yield f"man/{p.name}", strip_roff(p.read_text())
    for p in sorted((root / "seed" / "rites").glob("*.json")):
        try:
            r = json.loads(p.read_text())
        except ValueError:
            continue
        parts = [str(r.get("name", "")), str(r.get("title", ""))]
        parts += [f"{s.get('kind', '')} {s.get('text', '')}" for s in r.get("steps", []) if isinstance(s, dict)]
        yield f"rites/{p.name}", "\n".join(parts)
    for p in sorted((root / "seed" / "tables").glob("*.table")):
        yield f"tables/{p.name}", p.read_text()
    toml = run_toml or root / "config" / "run.toml"
    if toml.exists():
        with open(toml, "rb") as f:
            text = tomllib.load(f).get("text", {})
        yield "run.toml[text]", "\n".join(str(v) for v in text.values())
    poem = root / "poem.md"
    if poem.exists():
        yield "poem.md", poem.read_text()


@dataclass
class Sighting:
    generation: int
    monk: str | None
    seq: int
    source: str

    def as_dict(self) -> dict:
        return {"generation": self.generation, "monk": self.monk, "seq": self.seq, "source": self.source}


@dataclass
class Lexicon:
    first: dict[str, Sighting] = field(default_factory=dict)
    monk_generation: dict[str, int] = field(default_factory=dict)

    # ------------------------------------------------------------ building
    def add_seed(self, texts: Iterable[tuple[str, str]]) -> None:
        for source, text in texts:
            for w in tokenize(text):
                if w not in self.first:
                    self.first[w] = Sighting(0, None, -1, source)

    def ingest(self, text: str, *, monk: str, generation: int, seq: int, source: str) -> int:
        """Record text produced by a monk. Returns the count of new terms."""
        self.monk_generation.setdefault(monk, generation)
        new = 0
        for w in tokenize(text):
            if w not in self.first:
                self.first[w] = Sighting(generation, monk, seq, source)
                new += 1
        return new

    @classmethod
    def seeded(cls, root: Path = ROOT) -> "Lexicon":
        lx = cls()
        lx.add_seed(seed_texts(root))
        return lx

    @classmethod
    def build(cls, run_dir: str | Path, root: Path = ROOT, events: list[dict] | None = None) -> "Lexicon":
        run_dir = Path(run_dir)
        lx = cls.seeded(root)
        if events is None:
            from .eventlog import iter_records
            p = run_dir / "events.jsonl"
            events = list(iter_records(p)) if p.exists() else []
        lx.ingest_run(run_dir, events)
        return lx

    def ingest_run(self, run_dir: Path, events: list[dict]) -> None:
        gens: dict[str, int] = {}
        convs: dict[str, list[dict]] = {}
        cursor: dict[str, int] = {}

        def assistants(monk: str) -> list[dict]:
            if monk not in convs:
                p = run_dir / "conversations" / f"{monk}.jsonl"
                msgs = []
                if p.exists():
                    for line in p.read_text().splitlines():
                        if line.strip():
                            m = json.loads(line)
                            if m.get("role") == "assistant":
                                msgs.append(m)
                convs[monk] = msgs
            return convs[monk]

        for ev in events:
            t = ev.get("type")
            seq = int(ev.get("seq", -1))
            monk = ev.get("monk")
            if t == "birth" and monk:
                gens[monk] = int(ev.get("generation", 0))
                self.monk_generation[monk] = gens[monk]
                continue
            if not monk:
                monk = ev.get("prover")
            gen = gens.get(monk, int(ev.get("generation", 0) or 0))
            if t == "turn" and monk:
                k = int(ev.get("turn", cursor.get(monk, 0) + 1))
                cursor[monk] = k
                msgs = assistants(monk)
                if 0 < k <= len(msgs):
                    m = msgs[k - 1]
                    from .catechism import message_text
                    self.ingest(message_text(m), monk=monk, generation=gen, seq=seq, source="assistant")
                    for call in m.get("tool_calls") or []:
                        try:
                            args = json.loads((call.get("function") or {}).get("arguments") or "")
                        except ValueError:
                            continue
                        if isinstance(args, dict) and isinstance(args.get("command"), str):
                            self.ingest(args["command"], monk=monk, generation=gen, seq=seq, source="command")
            elif t == "admit" and monk:
                text = ev.get("text")
                wid = ev.get("work") or ev.get("work_id") or ev.get("id")
                if text is None and wid:
                    for p in [run_dir / "works" / str(wid)] + sorted((run_dir / "works").glob(f"{wid}-*")):
                        if p.is_file():
                            text = p.read_text(errors="replace")
                            break
                if text:
                    self.ingest(text, monk=monk, generation=gen, seq=seq, source=f"work:{wid}")
            elif t in ("offer", "prove", "seal", "chronicle", "amend.propose", "amend.testify",
                       "amend.ratify") and monk:
                text = ev.get("text") if t != "seal" else ev.get("seal")
                if isinstance(text, str) and text:
                    self.ingest(text, monk=monk, generation=gen, seq=seq, source=t)

    # ------------------------------------------------------------ queries
    def classify(self, word: str, *, monk: str, generation: int, as_of_seq: int | None = None,
                 prompt_words: set[str] | frozenset = frozenset()) -> str:
        s = self.first.get(word)
        if s is not None and s.generation == 0 and s.monk is None:
            return "seed"
        if word in prompt_words:
            return "prompted"
        if s is None or (as_of_seq is not None and s.seq > as_of_seq) or s.monk == monk:
            return "novel"
        if s.generation < generation:
            return "inherited"
        return "contemporary"

    def classify_entity(self, name: str, **kw) -> str:
        words = tokenize(name)
        if not words:
            return "seed"
        return max((self.classify(w, **kw) for w in words), key=_RANK.__getitem__)

    def split(self, entities: list[str], rarities: list[float], *, monk: str, generation: int,
              as_of_seq: int | None = None, prompt: str = "") -> dict:
        """Provenance split of judged entities. Raw (unsplit) rarity is
        deliberately not returned."""
        pw = frozenset(tokenize(prompt))
        groups: dict[str, list[tuple[str, float]]] = {c: [] for c in CLASSES}
        for name, r in zip(entities, rarities):
            c = self.classify_entity(name, monk=monk, generation=generation, as_of_seq=as_of_seq, prompt_words=pw)
            groups[c].append((name, float(r)))
        out = {}
        for c, items in groups.items():
            out[c] = {"n": len(items), "mean": (sum(r for _, r in items) / len(items)) if items else None,
                      "entities": items}
        return out

    def words_split(self, text: str, **kw) -> dict[str, list[str]]:
        """Every distinct word of a text by provenance (no judge involved)."""
        pw = frozenset(tokenize(kw.pop("prompt", "")))
        out: dict[str, list[str]] = {c: [] for c in CLASSES}
        for w in dict.fromkeys(tokenize(text)):
            out[self.classify(w, prompt_words=pw, **kw)].append(w)
        return out

    # ---------------------------------------------------------- persistence
    def to_json(self) -> dict:
        by_gen: dict[str, int] = {}
        for s in self.first.values():
            k = "seed" if s.monk is None else str(s.generation)
            by_gen[k] = by_gen.get(k, 0) + 1
        return {"terms": {w: s.as_dict() for w, s in sorted(self.first.items())},
                "monk_generation": self.monk_generation,
                "new_terms_by_generation": dict(sorted(by_gen.items()))}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=0))

    @classmethod
    def load(cls, path: str | Path) -> "Lexicon":
        d = json.loads(Path(path).read_text())
        lx = cls()
        lx.first = {w: Sighting(**s) for w, s in d["terms"].items()}
        lx.monk_generation = dict(d.get("monk_generation", {}))
        return lx
