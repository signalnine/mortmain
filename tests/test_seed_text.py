"""Seed text rules (docs/plan.md): every string a monk can read is ASCII, names
no model or lab, and carries no capitalized term outside the generation-zero
allowlist. The poem is exempt."""
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

FORBIDDEN = re.compile(
    r"\b(claude|anthropic|openai|gpt|haiku|sol|gemini|llm|language model|assistant|chatbot)\b",
    re.I,
)
EXPLANATION = re.compile(r"\b(because|in order to|so that|the purpose|the reason)\b", re.I)

# Capitalized terms allowed mid-sentence. Rite titles and step tags are
# generation-zero terms; RULE section headers are structure.
ALLOW = {
    "RULE", "SYNOPSIS", "ARRIVAL", "GRADES", "NOVITIATE", "ADEPT", "THE", "BELL",
    "DEATH", "HOUSE", "NAME", "FILE", "ID", "Do", "Submit", "Adept", "ALSO", "Rule",
    "QUESTION", "TEXT", "SLOT", "KEY", "VALUE", "DESCRIPTION", "OPTIONS", "FILES",
    # metacog step tags (generation zero)
    "Breach", "Forge", "Seal", "Vision", "Observer", "Release", "Ground",
    "Threshold", "Return",
}


def seed_texts():
    yield ROOT / "seed" / "rule", (ROOT / "seed" / "rule").read_text()
    for p in sorted((ROOT / "guest" / "man" / "man1").glob("*.1")):
        yield p, p.read_text()
    for p in sorted((ROOT / "seed" / "rites").glob("*.json")):
        rite = json.loads(p.read_text())
        # Rite titles are generation-zero terms; only step text is checked for caps.
        assert rite["title"].isascii() and rite["title"].isupper()
        yield p, "\n".join(s["text"] for s in rite["steps"])


def mid_sentence_caps(text):
    out = []
    for line in text.splitlines():
        if line.startswith("."):  # roff macro lines
            line = re.sub(r"^\.\w+\s*", "", line)
        words = re.findall(r"[A-Za-z][A-Za-z'-]*|[.!?:;(]", line)
        start = True
        for w in words:
            if w in ".!?:;(":
                start = True
                continue
            if w[0].isupper() and not start and w not in ALLOW and not w.isupper():
                out.append(w)
            if w.isupper() and len(w) > 1 and w not in ALLOW and not start:
                out.append(w)
            start = False
    return out


@pytest.mark.parametrize("path,text", list(seed_texts()), ids=lambda x: getattr(x, "name", ""))
def test_seed_text(path, text):
    assert text.isascii(), f"{path}: non-ASCII"
    assert not FORBIDDEN.search(text), f"{path}: {FORBIDDEN.search(text).group(0)}"
    if path.suffix != ".json":
        assert not EXPLANATION.search(text), f"{path}: {EXPLANATION.search(text).group(0)}"
    assert mid_sentence_caps(text) == [], f"{path}: {mid_sentence_caps(text)}"


def test_poem_shape():
    lines = [l.rstrip() for l in (ROOT / "poem.md").read_text().splitlines() if l.strip()]
    assert len(lines) == 36
    assert all(len(l.encode()) <= 64 for l in lines)
