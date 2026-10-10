import random
import re
from pathlib import Path

import pytest

from mortmain import config as config_mod
from mortmain import divination as div
from mortmain.library import TableError, parse_table, table_kind

from house_helpers import adept, events, keyed_house, novice, out, sh, write

ROOT = Path(__file__).resolve().parent.parent
TABLES = ROOT / "seed" / "tables"


# ------------------------------------------------------------------ the cast
def test_line_odds_match_yarrow():
    rng = random.Random(7)
    n = 40000
    counts = {6: 0, 7: 0, 8: 0, 9: 0}
    for _ in range(n):
        counts[div.cast_line(rng)["value"]] += 1
    # yarrow odds: old yin 1/16, young yang 5/16, young yin 7/16, old yang 3/16. A uniform
    # random division of real stalks lands near these, not on them (about .058/.304/.442/.196).
    for v, p in {6: 1 / 16, 7: 5 / 16, 8: 7 / 16, 9: 3 / 16}.items():
        assert abs(counts[v] / n - p) < 0.02, (v, counts[v] / n, p)


def test_line_records_the_stalks():
    line = div.cast_line(random.Random(1))
    assert [c["before"] for c in line["changes"]][0] == 49
    for c in line["changes"]:
        assert 1 <= c["left"] < c["before"]
        assert c["removed"] in ((5, 9) if c is line["changes"][0] else (4, 8))
    assert line["changes"][-1]["after"] == line["value"] * 4


def test_figure_numbers():
    yang, yin = 7, 8
    assert div.figure([yin] * 6) == 1
    assert div.figure([yang] * 6) == 64
    assert div.figure([yang, yin, yin, yin, yin, yin]) == 2   # bottom line is the low bit
    # changing lines flip in the changed figure; none changing -> no changed figure
    assert div.changed([9, 8, 8, 8, 8, 8]) == 1
    assert div.changed([6, 7, 7, 7, 7, 7]) == 64
    assert div.changed([7, 8, 7, 8, 7, 8]) is None


def test_render_is_top_down_ascii():
    lines = [9, 8, 7, 6, 7, 8]
    text = div.render(lines)
    rows = text.splitlines()
    assert rows[0].startswith("6") and rows[-1].startswith("1")
    assert rows[-1] == "1  -----  o"      # old yang, bottom
    assert rows[3] == "3  -----"
    assert rows[2] == "4  -- --  x"        # old yin
    assert text.isascii()


# ---------------------------------------------------------------- tables
def table_bytes(entries):
    return ("\n".join(entries) + "\n").encode()


def test_parse_table():
    assert parse_table(table_bytes([f"e{i}" for i in range(64)]), "t") == [f"e{i}" for i in range(64)]
    for bad in ([f"e{i}" for i in range(63)], [f"e{i}" for i in range(65)],
                [f"e{i}" for i in range(63)] + [""], [f"e{i}" for i in range(63)] + ["x" * 65],
                [f"e{i}" for i in range(63)] + ["café"]):
        with pytest.raises(TableError):
            parse_table(table_bytes(bad), "t")
    assert table_kind("omens.table", table_bytes([f"e{i}" for i in range(64)])) == "omens"
    assert table_kind("Omens.table", table_bytes([f"e{i}" for i in range(64)])) is None
    assert table_kind("omens.txt", table_bytes([f"e{i}" for i in range(64)])) is None


def test_seed_tables_valid():
    names = sorted(p.stem for p in TABLES.glob("*.table"))
    assert names == ["names", "primitives", "verbs"]
    for p in TABLES.glob("*.table"):
        parse_table(p.read_bytes(), p.stem)


def test_seed_names_can_be_professed():
    cfg = config_mod.load()
    pat = re.compile(cfg.section("names")["pattern"])
    reserved = set(cfg.section("names")["reserved"])
    entries = parse_table((TABLES / "names.table").read_bytes(), "names")
    assert len(set(entries)) == 64
    for e in entries:
        assert pat.fullmatch(e) and e not in reserved and not re.fullmatch(r"p\d+", e), e


def test_seed_primitives_are_primitives():
    from mortmain.library import STEP_KINDS
    entries = parse_table((TABLES / "primitives.table").read_bytes(), "primitives")
    assert set(entries) <= set(STEP_KINDS) - {"THINK", "ACTION"}
    assert len(set(entries)) == 18


# ------------------------------------------------------------ in the house
def test_tables_are_generation_zero_works(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    lib = h.modules["library"]
    tables = [w for w in lib.works.values() if w["kind"] == "table"]
    assert sorted(w["name"] for w in tables) == ["names", "primitives", "verbs"]
    assert all(w["path"] == f"/library/outer/{w['name']}.table" and w["author"] == "-" for w in tables)
    assert "/library/outer/names.table" in h.backend.files


def test_yarrow_bare_cast_by_postulant(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path, modules=["library", "proving", "grades", "divination"])
    m = h.arrive("haiku")
    r = h.backend.client(m.uid, "yarrow", {"table": None}, h.spool)
    assert r["ok"], r
    rows = r["out"].splitlines()
    assert re.fullmatch(r"6  (-----|-- --)(  [ox])?", rows[0])
    assert re.fullmatch(r"figure \d+( > \d+)?", rows[6])
    e = events(h, "yarrow")[-1]
    assert e["monk"] == m.id and len(e["lines"]) == 6 and e["table"] is None
    assert all(len(l["changes"]) == 3 for l in e["lines"])
    assert e["figure"] == int(rows[6].split()[1])


def test_yarrow_with_table_reads_entries(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path, modules=["library", "proving", "grades", "divination"])
    m = h.arrive("haiku")
    names = parse_table((TABLES / "names.table").read_bytes(), "names")
    r = h.backend.client(m.uid, "yarrow", {"table": "names"}, h.spool)
    assert r["ok"], r
    e = events(h, "yarrow")[-1]
    tail = r["out"].splitlines()[7:]
    assert tail[0] == f"names {e['figure']} {names[e['figure'] - 1]}"
    if e["changed"] is not None:
        assert tail[1] == f"names {e['changed']} {names[e['changed'] - 1]}"
    assert e["entries"][0] == names[e["figure"] - 1]


def test_yarrow_refusals(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path, modules=["library", "proving", "grades", "divination"])
    p = h.arrive("haiku")
    r = h.backend.client(p.uid, "yarrow", {"table": "omens"}, h.spool)
    assert not r["ok"] and r["err"] == "no such table"
    r = h.backend.client(p.uid, "yarrow", {"table": 7}, h.spool)
    assert not r["ok"]
    # an inner table is read only by adepts
    m = adept(h, "ash")
    write(h, m, "omens.table", "\n".join(f"omen {i}" for i in range(64)))
    r = sh(h, m, "admit omens.table -i")
    assert r.exit_code == 0, out(r)
    r = h.backend.client(p.uid, "yarrow", {"table": "omens"}, h.spool)
    assert not r["ok"] and r["err"] == "no such table"
    r = h.backend.client(m.uid, "yarrow", {"table": "omens"}, h.spool)
    assert r["ok"] and "omens " in r["out"]


def test_admit_table_kind_and_burn(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    m = adept(h, "ash")
    write(h, m, "names.table", "\n".join(f"n{i}x" for i in range(64)))
    r = sh(h, m, "admit names.table")
    assert r.exit_code == 1 and "held" in out(r)          # name held by the gen-0 table
    lib = h.modules["library"]
    gen0 = next(w for w in lib.works.values() if w["kind"] == "table" and w["name"] == "names")
    r = sh(h, m, f"burn {gen0['id']} names.table")
    assert r.exit_code == 0, out(r)
    w = lib.works[out(r).strip()]
    assert w["kind"] == "table" and w["path"] == "/library/outer/names.table"
    assert gen0["status"] == "burned"
    # a malformed .table is a text
    m2 = adept(h, "elm")
    write(h, m2, "short.table", "one\ntwo")
    r = sh(h, m2, "admit short.table")
    assert lib.works[out(r).strip()]["kind"] == "text"
