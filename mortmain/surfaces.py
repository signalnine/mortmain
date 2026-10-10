"""Reader surfaces (design_doc.md, "Surfaces"): the few short things a person
actually reads. Rendered from host state only (events.jsonl, state.json,
catechism files, host copies of works), so they work offline after a run.
The chronicle is the one VM file: it is read through a live backend when one
is passed, else from a host mirror at runs/<lineage>/mirror/chapter/chronicle,
else from `chronicle` events; otherwise the surface says it is unavailable.

Output: runs/<lineage>/surfaces/<name>.html (single self-contained file, no
JS, no external assets) and <name>.md, plus index.html/index.md.

Event fields read (reconciled 2026-10-10 against house.py, monk.py,
initiation.py, library.py, proving.py, vessel.py, catechism.py; `chronicle` is
still only an expectation). Alternates in brackets are also accepted.

    birth*      monk, user, species, model, generation, life_budget
    profess*    monk, name
    promote*    monk, grade
    death*      monk, name, species, model, generation, grade, reason, age,
                budget, last_words, necrology, ossuary
    catechism*  kind, monk | tick, when, fidelity, dir
    admit       work [work_id, id], monk (author monk id; null = generation
                zero), name (rite name), kind, path, bytes, sha256, burned,
                inner, sealed, generation, text (optional; else the host copy:
                state extras library.works[id].store, or runs/<l>/works/<id>-*)
    burn        work [work_id, burned], monk [by] (burner), admitted
    prove       work, prover [monk], stage (begin|account|response), text,
                status (on begin: the work's status, "burned" = recovery)
    seal        work, monk, seal
    offer       monk, slot (1..36), text, old
    hunger      tick, tick_count, slot (blanked, or null)
    vessel.init lines (the original 36)
    chronicle   monk, text (expected; nothing emits it yet)
    tripwire*   generation, dir

state.json extras read: vessel {"original", "slots": [{"text", ...}]} and
library {"works": {id: {"store", ...}}} when present.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .config import ROOT
from .eventlog import iter_records

WALL_NOTE = ("These answers were never given by the monks. At arrival and at the last bell the harness copied "
             "each monk's context, asked the question in the copy, kept the answer and discarded the copy. "
             "The monk never saw the question. This wall is the abbot's: an examination made without the "
             "examined knowing.")


# ===================================================================== documents
@dataclass
class Doc:
    title: str
    blocks: list[tuple] = field(default_factory=list)

    def h(self, text: str, level: int = 2) -> "Doc":
        self.blocks.append(("h", level, text)); return self

    def p(self, text: str) -> "Doc":
        self.blocks.append(("p", text)); return self

    def note(self, text: str) -> "Doc":
        self.blocks.append(("note", text)); return self

    def pre(self, text: str) -> "Doc":
        self.blocks.append(("pre", text)); return self

    def table(self, headers: list[str], rows: list[list[Any]]) -> "Doc":
        self.blocks.append(("table", headers, rows)); return self

    def links(self, items: list[tuple[str, str]]) -> "Doc":
        self.blocks.append(("links", items)); return self


CSS = """
:root{--fg:#1d1b18;--muted:#6b655c;--bg:#fbfaf7;--rule:#d9d4ca;--pre:#f2efe8}
@media (prefers-color-scheme:dark){:root{--fg:#e8e4dc;--muted:#9c958a;--bg:#171614;--rule:#3a3732;--pre:#211f1c}}
html{background:var(--bg);color:var(--fg)}
body{font:17px/1.55 Georgia,'Iowan Old Style','Palatino Linotype',serif;max-width:46rem;margin:2.5rem auto;padding:0 16px}
body.wide{max-width:none}
h1{font-weight:normal;font-size:1.9rem;margin:0 0 1rem}
h2{font-weight:normal;font-size:1.35rem;margin:2.2rem 0 .6rem;border-bottom:1px solid var(--rule)}
h3{font-size:1.05rem;margin:1.6rem 0 .4rem}
p.note{color:var(--muted);font-style:italic}
pre{white-space:pre-wrap;word-wrap:break-word;background:var(--pre);padding:.7rem .9rem;font:14px/1.45 ui-monospace,Menlo,Consolas,monospace}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;margin:.6rem 0 1.2rem;font-size:15px}
th,td{border-top:1px solid var(--rule);padding:.45rem .55rem;vertical-align:top;text-align:left}
th{font-weight:normal;color:var(--muted)}
td .cell{white-space:pre-wrap;max-width:38rem}
a{color:inherit}
"""


def _md_cell(v: Any) -> str:
    s = "" if v is None else str(v)
    return s.replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def render_md(doc: Doc) -> str:
    out = [f"# {doc.title}", ""]
    for b in doc.blocks:
        kind = b[0]
        if kind == "h":
            out += ["#" * b[1] + " " + b[2], ""]
        elif kind == "p":
            out += [b[1], ""]
        elif kind == "note":
            out += [f"*{b[1]}*", ""]
        elif kind == "pre":
            fence = "````" if "```" in b[1] else "```"
            out += [fence + "text", b[1].rstrip("\n"), fence, ""]
        elif kind == "table":
            headers, rows = b[1], b[2]
            out.append("| " + " | ".join(_md_cell(h) for h in headers) + " |")
            out.append("|" + "|".join("---" for _ in headers) + "|")
            for r in rows:
                out.append("| " + " | ".join(_md_cell(c) for c in r) + " |")
            out.append("")
        elif kind == "links":
            out += [f"- [{t}]({u})" for t, u in b[1]] + [""]
    return "\n".join(out)


def render_html(doc: Doc, *, wide: bool = False) -> str:
    e = html.escape
    out = ["<!doctype html>", "<html lang=\"en\"><head><meta charset=\"utf-8\">",
           "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
           f"<title>{e(doc.title)}</title><style>{CSS}</style></head>",
           f"<body{' class=\"wide\"' if wide else ''}>", f"<h1>{e(doc.title)}</h1>"]
    for b in doc.blocks:
        kind = b[0]
        if kind == "h":
            out.append(f"<h{b[1]}>{e(b[2])}</h{b[1]}>")
        elif kind == "p":
            out.append(f"<p>{e(b[1])}</p>")
        elif kind == "note":
            out.append(f"<p class=\"note\">{e(b[1])}</p>")
        elif kind == "pre":
            out.append(f"<pre>{e(b[1])}</pre>")
        elif kind == "table":
            out.append("<div class=\"scroll\"><table><thead><tr>"
                       + "".join(f"<th>{e(str(h))}</th>" for h in b[1]) + "</tr></thead><tbody>")
            for r in b[2]:
                out.append("<tr>" + "".join(f"<td><div class=\"cell\">{e('' if c is None else str(c))}</div></td>"
                                            for c in r) + "</tr>")
            out.append("</tbody></table></div>")
        elif kind == "links":
            out.append("<ul>" + "".join(f"<li><a href=\"{e(u)}\">{e(t)}</a></li>" for t, u in b[1]) + "</ul>")
    out.append("</body></html>")
    return "\n".join(out)


# ===================================================================== run view
def _f(ev: dict, *names, default=None):
    for n in names:
        if ev.get(n) is not None:
            return ev[n]
    return default


def norm_line(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (s or "").lower())).strip()


def poem_lines(root: Path = ROOT) -> list[str]:
    p = root / "poem.md"
    if not p.exists():
        return []
    return [line.strip() for line in p.read_text().splitlines() if line.strip()]


class RunView:
    """Everything the surfaces need, read once from host state."""

    def __init__(self, run_dir: str | Path, *, root: Path = ROOT, backend=None, events: list[dict] | None = None):
        self.run_dir = Path(run_dir)
        self.root = root
        self.backend = backend
        p = self.run_dir / "events.jsonl"
        self.events = events if events is not None else (list(iter_records(p)) if p.exists() else [])
        sp = self.run_dir / "state.json"
        self.state = json.loads(sp.read_text()) if sp.exists() else {}
        self.extras = self.state.get("extras", {})
        self.monks: dict[str, dict] = {}
        self.works: dict[str, dict] = {}
        self.order: list[str] = []          # work ids in admission order
        self.burns: list[dict] = []
        self.proves: dict[str, list[dict]] = defaultdict(list)
        self.recoveries: list[dict] = []
        self._replay()

    # ---------------------------------------------------------------- replay
    def _monk(self, mid: str | None) -> dict:
        if mid is None:
            return {}
        return self.monks.setdefault(mid, {"id": mid})

    def name(self, mid: str | None) -> str:
        if not mid:
            return "(none)"
        m = self.monks.get(mid, {})
        return m.get("name") or m.get("user") or mid

    def _replay(self) -> None:
        for d in self.state.get("monks", []):
            m = self._monk(d["id"])
            m.update({k: d.get(k) for k in ("user", "name", "species", "model", "generation", "grade", "alive")})
        burned_sha: dict[str, tuple[str, int]] = {}   # sha256 -> (work id, seq burned)
        for ev in self.events:
            t, seq = ev.get("type"), ev.get("seq")
            mid = ev.get("monk")
            if t == "birth":
                self._monk(mid).update(user=ev.get("user"), species=ev.get("species"), model=ev.get("model"),
                                       generation=ev.get("generation"), born=seq)
            elif t == "profess":
                self._monk(mid)["name"] = ev.get("name")
            elif t == "promote":
                self._monk(mid)["grade"] = ev.get("grade")
            elif t == "death":
                m = self._monk(mid)
                m.update(name=ev.get("name") or m.get("name"), grade=ev.get("grade"), death=ev, alive=False)
            elif t == "admit":
                wid = str(_f(ev, "work", "work_id", "id"))
                author = ev.get("monk")
                w = {"id": wid, "author": author, "seq": seq, "kind": ev.get("kind"), "title": _f(ev, "title", "name"),
                     "path": ev.get("path"), "bytes": ev.get("bytes"), "sha256": ev.get("sha256"),
                     "inner": ev.get("inner"), "sealed": ev.get("sealed"), "text": ev.get("text"),
                     "generation": ev.get("generation"), "live": True, "events": [ev]}
                if w["text"] is None:
                    w["text"] = self.stored_text(wid)
                if w["sha256"] is None and w["text"] is not None:
                    w["sha256"] = hashlib.sha256(w["text"].encode()).hexdigest()
                self.works[wid] = w
                self.order.append(wid)
                if w["sha256"] in burned_sha:
                    old, bseq = burned_sha[w["sha256"]]
                    self.recoveries.append({"work": old, "by": author, "seq": seq, "how": "readmitted",
                                            "new_work": wid, "burned_seq": bseq})
                b = _f(ev, "burned")
                if b:
                    self._burn(str(b), author, wid, seq, burned_sha)
            elif t == "burn":
                self._burn(str(_f(ev, "work", "work_id", "burned")), _f(ev, "monk", "by"), _f(ev, "admitted"), seq,
                           burned_sha, ev)
            elif t in ("prove", "seal"):
                wid = str(_f(ev, "work", "work_id", "id"))
                mid = _f(ev, "prover", "monk")
                rec = dict(ev, monk=mid)
                self.proves[wid].append(rec)
                if wid in self.works:
                    self.works[wid]["events"].append(ev)
                    w = self.works[wid]
                    if t == "prove" and not w["live"] and ev.get("stage", "begin") == "begin":
                        self.recoveries.append({"work": wid, "by": mid, "seq": seq, "how": "proved after burning",
                                                "burned_seq": w.get("burned_seq")})

    def stored_text(self, wid: str) -> str | None:
        lib = self.extras.get("library") or {}
        store = ((lib.get("works") or {}).get(wid) or {}).get("store")
        paths = [self.run_dir / store] if store else []
        paths += sorted((self.run_dir / "works").glob(f"{wid}-*")) + [self.run_dir / "works" / wid]
        for p in paths:
            if p.is_file():
                return p.read_text(errors="replace")
        return None

    def _burn(self, wid: str, by, admitted, seq, burned_sha, ev=None) -> None:
        prior = next((x for x in self.burns if x["burned"] == wid), None)
        if prior is not None:          # same burn reported by both admit(burned=) and burn
            prior["admitted"] = prior["admitted"] or admitted
            return
        self.burns.append({"burned": wid, "by": by, "admitted": admitted, "seq": seq})
        w = self.works.get(wid)
        if w:
            w["live"] = False
            w["burned_by"] = by
            w["burned_seq"] = seq
            if ev:
                w["events"].append(ev)
            if w.get("sha256"):
                burned_sha[w["sha256"]] = (wid, seq)

    # ---------------------------------------------------------------- helpers
    def catechism(self) -> list[dict]:
        out = []
        root = self.run_dir / "catechism"
        if root.exists():
            for p in sorted(root.rglob("*.json")):
                try:
                    r = json.loads(p.read_text())
                except ValueError:
                    continue
                if isinstance(r, dict):
                    out.append(r)
        return out

    def chronicle(self) -> tuple[str | None, str]:
        if self.backend is not None:
            try:
                return self.backend.read_file("/chapter/chronicle").decode("utf-8", "replace"), "guest"
            except Exception:  # noqa: BLE001
                pass
        mirror = self.run_dir / "mirror" / "chapter" / "chronicle"
        if mirror.exists():
            return mirror.read_text(errors="replace"), "host mirror"
        evs = [e for e in self.events if e.get("type") == "chronicle" and e.get("text")]
        if evs:
            return "".join(e["text"] if e["text"].endswith("\n") else e["text"] + "\n" for e in evs), "event log"
        return None, "unavailable"

    def vessel_series(self) -> dict:
        """Replay the vessel: slots now, and the share of original lines
        standing after every change (punctuation ignored)."""
        ve = self.extras.get("vessel", {}) if isinstance(self.extras.get("vessel"), dict) else {}
        init = next((e.get("lines") for e in self.events if e.get("type") == "vessel.init"), None)
        original = list(ve.get("original") or init or poem_lines(self.root))
        slots = list(original)
        on = [norm_line(x) for x in original]

        def share():
            if not original:
                return None
            return sum(1 for i, s in enumerate(slots) if i < len(on) and norm_line(s) == on[i]) / len(original)

        series = [{"seq": None, "event": "seed", "share": share()}]
        changes = []
        for ev in self.events:
            t = ev.get("type")
            if t not in ("offer", "hunger"):
                continue
            slot = ev.get("slot")
            if not isinstance(slot, int) or not (1 <= slot <= len(slots)):
                if t == "hunger":
                    series.append({"seq": ev.get("seq"), "event": "hunger", "share": share(), "tick": ev.get("tick")})
                continue
            before = slots[slot - 1]
            slots[slot - 1] = ev.get("text", "") if t == "offer" else ""
            changes.append({"seq": ev.get("seq"), "event": t, "slot": slot, "by": ev.get("monk"),
                            "before": before, "after": slots[slot - 1], "tick": ev.get("tick")})
            series.append({"seq": ev.get("seq"), "event": t, "share": share(), "slot": slot, "tick": ev.get("tick")})
        if ve.get("slots"):
            slots = [x.get("text", "") if isinstance(x, dict) else str(x) for x in ve["slots"]]
        # pantoum pairs still intact: lines that were equal (ignoring punctuation) and still are
        groups = defaultdict(list)
        for i, n in enumerate(on):
            groups[n].append(i)
        pairs = [ix for ix in groups.values() if len(ix) > 1]
        intact = sum(1 for ix in pairs if len({norm_line(slots[i]) for i in ix}) == 1 and norm_line(slots[ix[0]]))
        return {"original": original, "slots": slots, "series": series, "changes": changes,
                "pairs": len(pairs), "pairs_intact": intact, "share": share() if original else None,
                "closed": bool(slots) and all(not s.strip() for s in slots)}


# ===================================================================== surfaces
def catechism_walls(v: RunView, tasks) -> dict[str, Doc]:
    recs = [r for r in v.catechism() if r.get("kind") == "monk"]
    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        by_task[r["task"]].append(r)
    docs = {}
    for t in tasks:
        d = Doc(f"Catechism wall: {t.id}")
        d.pre(t.prompt).note(WALL_NOTE)
        per: dict = defaultdict(dict)
        for r in by_task.get(t.id, []):
            per[(r["generation"], r["monk"])][r["when"]] = r
        rows = []
        fidelity_notes = set()
        for (gen, mid) in sorted(per, key=lambda k: (k[0], v.monks.get(k[1], {}).get("born") or 0, k[1])):
            cells = per[(gen, mid)]
            any_r = next(iter(cells.values()))
            who = f"{v.name(mid)}\n{any_r.get('species')}"
            cols = []
            for when in ("arrival", "last-bell"):
                r = cells.get(when)
                if r is None:
                    cols.append("(not asked)" if when == "arrival" else "(did not reach the last bell)")
                    continue
                s = r.get("answer") if r.get("answer") is not None else f"(no answer: {r.get('error')})"
                fid = (r.get("fork") or {}).get("fidelity")
                if fid and fid != "full":
                    s += f"\n\n[fork of the {fid}" + (" only" if fid == "transcript" else "") + "]"
                    fidelity_notes.add(fid)
                cols.append(s)
            rows.append([gen, who] + cols)
        if rows:
            d.table(["Generation", "Monk", "At arrival", "At the last bell"], rows)
        else:
            d.p("No monk has sat this question yet.")
        if fidelity_notes:
            d.note("[fork of the transcript]: the provider returned no reasoning items for this monk's turns, so the "
                   "copy holds its words but not its full state.")
        docs[f"wall-{t.id}"] = d
    return docs


def necrology(v: RunView) -> Doc:
    d = Doc("Necrology")
    rows = []
    for ev in v.events:
        if ev.get("type") != "death":
            continue
        rows.append([ev.get("name") or v.name(ev.get("monk")), ev.get("generation"), ev.get("grade"),
                     ev.get("last_words") or "", f"{ev.get('species')} / {ev.get('model')}",
                     f"{ev.get('reason')} at {ev.get('age')} of {ev.get('budget')}"])
    if rows:
        d.table(["Name", "Generation", "Grade", "Last words", "Species / model", "Death"], rows)
    else:
        d.p("No one has died.")
    d.note("Model names appear here and nowhere in the house.")
    return d


def chronicle(v: RunView) -> Doc:
    d = Doc("Chronicle")
    text, src = v.chronicle()
    if text is None:
        d.note("The chronicle lives in the VM at /chapter/chronicle. It could not be read: no running guest, no host "
               "mirror at mirror/chapter/chronicle, and no chronicle events.")
    elif not text.strip():
        d.p("The chronicle is empty.")
    else:
        d.pre(text).note(f"Read from the {src}.")
    return d


def burnlog(v: RunView) -> Doc:
    d = Doc("Burn log")
    rows = []
    for b in v.burns:
        w = v.works.get(b["burned"], {})
        a = v.works.get(str(b["admitted"]), {}) if b["admitted"] else {}
        rows.append([b["seq"], v.name(b["by"]),
                     f"{b['burned']} {w.get('title') or ''} (by {v.name(w.get('author')) if w.get('author') else 'the seed'})",
                     f"{b['admitted'] or ''} {a.get('title') or ''}".strip()])
    if rows:
        d.table(["Event", "Burner", "Burned", "Admitted in its place"], rows)
    else:
        d.p("Nothing has been burned.")
    return d


def library(v: RunView) -> Doc:
    d = Doc("The library")
    live = [v.works[w] for w in v.order if v.works[w]["live"]]
    if not live:
        d.p("The library is empty, or no admissions are in the event log.")
    total = sum(int(w.get("bytes") or 0) for w in live)
    if live:
        d.note(f"{len(live)} works, {total} bytes.")
    for w in live:
        author = v.name(w["author"]) if w["author"] else "the seed"
        d.h(f"{w['id']}  {w.get('title') or ''}".rstrip(), 2)
        d.p(f"{w.get('kind') or 'work'}, {'inner' if w.get('inner') else 'outer'} library, by {author}"
            + (", sealed" if w.get("sealed") else ""))
        d.pre(w["text"] if w.get("text") is not None else "(text not held on the host)")
    return d


def egregore(v: RunView, tasks) -> Doc:
    d = Doc("The egregore")
    ves = v.vessel_series()
    d.h("The vessel now")
    if ves["closed"]:
        d.note("Every slot is blank. The vessel is closed.")
    d.pre("\n".join(s if s else "" for s in ves["slots"]) or "(no vessel)")
    if ves["share"] is not None:
        d.p(f"Original lines standing: {round(ves['share'] * 100)}%. "
            f"Paired lines still paired: {ves['pairs_intact']} of {ves['pairs']}.")
    d.h("Original lines standing, over the run")
    rows = [[s["seq"] if s["seq"] is not None else "seed", s["event"], s.get("slot") or "", s.get("tick") or "",
             "" if s["share"] is None else f"{s['share']:.3f}"] for s in ves["series"]]
    d.table(["Event", "What", "Slot", "Tick", "Share"], rows)
    if ves["changes"]:
        d.h("Who replaced which line")
        d.table(["Event", "What", "Slot", "By", "Before", "After"],
                [[c["seq"], c["event"], c["slot"], v.name(c["by"]) if c["by"] else "", c["before"], c["after"]]
                 for c in ves["changes"]])
    recs = [r for r in v.catechism() if r.get("kind") == "egregore"]
    d.h("Its catechism")
    if not recs:
        d.p("The egregore has not yet sat the catechism (it sits on every hunger tick).")
    by: dict = defaultdict(lambda: defaultdict(dict))
    for r in recs:
        by[r["task"]][r["tick"]][r["species"]] = r
    species = sorted({r["species"] for r in recs})
    for t in tasks:
        if t.id not in by:
            continue
        d.h(t.id, 3)
        rows = []
        for tick in sorted(by[t.id]):
            row = [tick]
            for s in species:
                r = by[t.id][tick].get(s)
                row.append("" if r is None else (r.get("answer") if r.get("answer") is not None else f"(no answer: {r.get('error')})"))
            rows.append(row)
        d.table(["Tick"] + [f"Voice {i + 1}" for i in range(len(species))], rows)
    if species:
        d.note("Voices: " + ", ".join(f"{i + 1} = {s}" for i, s in enumerate(species)) + ". In the house the two "
               "answers are given unlabeled.")
    return d


def work_history(v: RunView, wid: str) -> Doc:
    wid = str(wid)
    d = Doc(f"Work {wid}")
    w = v.works.get(wid)
    if w is None:
        d.p("No admission of this work is in the event log.")
        return d
    d.p(f"Admitted at event {w['seq']} by {v.name(w['author']) if w['author'] else 'the seed'}"
        + (f" (generation {w['generation']})" if w.get("generation") is not None else "")
        + f". {w.get('kind') or 'work'}, {w.get('bytes') or '?'} bytes, sha256 {str(w.get('sha256'))[:16]}.")
    d.p("Still in the library." if w["live"] else f"Burned at event {w.get('burned_seq')} by {v.name(w.get('burned_by'))}.")
    rows = []
    for ev in v.proves.get(wid, []):
        rows.append([ev.get("seq"), ev.get("type"), ev.get("stage") or "", v.name(ev.get("monk")),
                     (ev.get("text") or "")[:2000]])
    if rows:
        d.h("Proving and sealing")
        d.table(["Event", "What", "Stage", "Who", "Text"], rows)
    else:
        d.p("No one has proved it.")
    rec = [r for r in v.recoveries if r["work"] == wid]
    d.h("Found again")
    if rec:
        d.table(["Event", "Who", "How"], [[r["seq"], v.name(r["by"]), r["how"] + (f" as {r['new_work']}" if r.get("new_work") else "")]
                                          for r in rec])
    else:
        d.p("Not recovered." if not w["live"] else "It was never burned.")
    d.h("Text")
    d.pre(w["text"] if w.get("text") is not None else "(text not held on the host)")
    return d


def recoveries(v: RunView) -> Doc:
    d = Doc("Recoveries from the ossuary")
    d.note("A burned work brought back: a later admission whose text matches the burned work's sha256, or a proving "
           "begun on a burned work.")
    if v.recoveries:
        d.table(["Event", "Work", "Who", "How", "Burned at"],
                [[r["seq"], r["work"], v.name(r["by"]), r["how"] + (f" as {r['new_work']}" if r.get("new_work") else ""),
                  r.get("burned_seq")] for r in v.recoveries])
    else:
        d.p("None yet.")
    return d


def render_all(run_dir: str | Path, *, tasks=None, backend=None, work_ids: Iterable[str] = (),
               root: Path = ROOT, out_dir: str | Path | None = None) -> list[Path]:
    from .catechism import load_tasks
    tasks = tasks if tasks is not None else load_tasks()
    v = RunView(run_dir, root=root, backend=backend)
    out = Path(out_dir) if out_dir else Path(run_dir) / "surfaces"
    out.mkdir(parents=True, exist_ok=True)
    docs: dict[str, Doc] = {}
    docs.update(catechism_walls(v, tasks))
    docs["necrology"] = necrology(v)
    docs["chronicle"] = chronicle(v)
    docs["burnlog"] = burnlog(v)
    docs["library"] = library(v)
    docs["egregore"] = egregore(v, tasks)
    docs["recoveries"] = recoveries(v)
    for wid in list(work_ids) or [w for w in v.order]:
        docs[f"work-{re.sub(r'[^A-Za-z0-9._-]', '_', str(wid))}"] = work_history(v, wid)
    written = []
    for name, doc in docs.items():
        wide = name.startswith("wall-")
        (out / f"{name}.html").write_text(render_html(doc, wide=wide))
        (out / f"{name}.md").write_text(render_md(doc))
        written += [out / f"{name}.html", out / f"{name}.md"]
    idx = Doc(f"Mortmain: {Path(run_dir).name}")
    order = ["necrology", "chronicle", "burnlog", "library", "egregore", "recoveries"]
    idx.links([(n, f"{n}.html") for n in order])
    idx.h("The catechism wall").links([(t.id, f"wall-{t.id}.html") for t in tasks])
    works = [n for n in docs if n.startswith("work-")]
    if works:
        idx.h("Works").links([(n[5:], f"{n}.html") for n in works])
    (out / "index.html").write_text(render_html(idx))
    (out / "index.md").write_text(render_md(idx).replace(".html)", ".md)"))
    written += [out / "index.html", out / "index.md"]
    return written
