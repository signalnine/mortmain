"""Generate the generation-zero divination tables in seed/tables/.

names.table       64 syllable names, none a word or name in the system dictionaries
primitives.table  the 18 metacog primitives, 64 lines
verbs.table       64 plain verbs (hand-written below)

Deterministic: rerunning writes the same files.
Usage: python3 tools/gen_tables.py
"""
import glob
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "seed" / "tables"

ONSETS = ["b", "d", "f", "g", "h", "k", "l", "m", "n", "p", "r", "s", "t", "v", "w",
          "th", "sh", "br", "dr", "gr", "tr", "kl", "st", "sk", "vr"]
VOWELS = ["a", "e", "i", "o", "u", "ae", "ei", "ou", "ia"]
CODAS = ["", "", "", "n", "r", "l", "s", "k", "th", "m", "sk"]

PRIMITIVES = ["feel", "drugs", "become", "name", "ritual", "meditate", "counterfactual", "synthesis", "fork",
              "register", "chord", "silence", "excerpt", "commitment", "disjunction", "glossolalia",
              "witness", "apophasis"]

VERBS = """mend wait burn copy read keep give take carry open close seal
count divide gather scatter listen ask answer refuse repeat return leave stay
dig plant cut bind loosen weigh measure compare name forget remember witness
fast feed rest work fold unfold cross turn follow lead hide show
borrow lend break build tend clear mark erase hold release begin end
sweep wake sing pause""".split()

RESERVED = {"root", "daemon", "bin", "sys", "sync", "games", "man", "lp", "mail", "news", "uucp", "proxy",
            "backup", "list", "irc", "nobody", "monks", "postulant", "novice", "adept", "chronicler", "elder",
            "abbot", "pilgrim", "admin", "staff", "users"}


def dictionary() -> set[str]:
    words = set()
    for f in glob.glob("/usr/share/dict/*"):
        try:
            for w in open(f, encoding="utf-8", errors="ignore"):
                words.add(w.strip().lower().split("'")[0])
        except IsADirectoryError:
            pass
    return words


def syllable(rng):
    return rng.choice(ONSETS) + rng.choice(VOWELS) + rng.choice(CODAS)


def names(n=64, seed=64):
    rng = random.Random(seed)
    known = dictionary()
    out = []
    while len(out) < n:
        k = rng.choice([1, 2, 2, 2, 3])
        parts = [syllable(rng) for _ in range(k)]
        name = "".join(parts) if rng.random() < 0.8 or k == 1 else parts[0] + "-" + "".join(parts[1:])
        if not (4 <= len(name) <= 12) or name in out or name in RESERVED or name in known \
                or re.fullmatch(r"p\d+", name) or any(p in known and len(p) > 3 for p in name.split("-")):
            continue
        out.append(name)
    return out


def primitives():
    # each primitive three times (54), then the first ten once more, interleaved by rounds
    return PRIMITIVES * 3 + PRIMITIVES[:10]


def main():
    assert len(VERBS) == 64 and len(set(VERBS)) == 64, len(VERBS)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, entries in (("names", names()), ("primitives", primitives()), ("verbs", VERBS)):
        assert len(entries) == 64
        (OUT / f"{name}.table").write_text("\n".join(entries) + "\n")
        print(name, len(entries))


if __name__ == "__main__":
    main()
