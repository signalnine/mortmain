"""Snapshot exports and `mortmain fork`, dry (FakeProvider, FakeBackend)."""
import json

from mortmain import cli
from mortmain.eventlog import iter_records, verify


def _run(tmp_path, lineage, turns, capsys):
    rc = cli.main(["--runs", str(tmp_path), "run", "--lineage", lineage, "--rung", "full", "--dry", "--fake-vm",
                   "--budget", "3000", "--elder-budget", "8000", "--max-turns", str(turns)])
    assert rc == 0
    return json.loads(capsys.readouterr().out)


def test_snapshot_exports_and_fork(tmp_path, capsys):
    _run(tmp_path, "src", 600, capsys)
    src = tmp_path / "src"
    snaps = [r for r in iter_records(src / "events.jsonl") if r["type"] == "snapshot"]
    gens = [r for r in snaps if r["tag"].startswith("gen-") and r["tag"] != "gen-0"]
    assert gens and all(r["export"] == f"snapshots/{r['tag']}.tgz" and r["bytes"] > 0 for r in snaps)
    tag = gens[0]["tag"]
    meta = json.loads((src / "snapshots" / f"{tag}.json").read_text())
    assert meta["state"]["lineage"] == "src" and meta["seq"] < gens[0]["seq"]

    assert cli.main(["--runs", str(tmp_path), "fork", "--from", "src", "--tag", tag, "--lineage", "dst"]) == 0
    capsys.readouterr()
    dst = tmp_path / "dst"
    st = json.loads((dst / "state.json").read_text())
    assert st["lineage"] == "dst" and st["next_seq"] == meta["state"]["next_seq"]
    for mid, n in meta["conversations"].items():
        lines = [x for x in (dst / "conversations" / f"{mid}.jsonl").read_text().split("\n") if x]
        assert len(lines) == n

    out = _run(tmp_path, "dst", 200, capsys)
    recs = list(iter_records(dst / "events.jsonl"))
    fk = [r for r in recs if r["type"] == "fork"]
    assert len(fk) == 1 and fk[0]["source"] == "src" and fk[0]["tag"] == tag
    first_snap = next(r for r in recs if r["type"] == "snapshot")
    assert first_snap["tag"] == tag  # the fork's state is the tag's, not a gen-0
    assert verify(dst / "events.jsonl").ok
    assert not (dst / "fork.json").exists() and (dst / "fork.done.json").exists()
    # the fork resumed the source's monks rather than starting over
    assert {m["monk"] for m in out["monks"]} >= {m["id"] for m in meta["state"]["monks"]}


def test_fork_recasts_the_elder_seat(tmp_path, capsys):
    _run(tmp_path, "src", 600, capsys)
    src = tmp_path / "src"
    tags = [r["tag"] for r in iter_records(src / "events.jsonl") if r["type"] == "snapshot" and r["tag"] != "gen-0"
            and r["tag"].startswith("gen-")]
    meta = json.loads((src / "snapshots" / f"{tags[0]}.json").read_text())
    seat = next(x for x in meta["state"]["extras"]["scheduler"]["seats"] if x["role"] == "elder")
    assert cli.main(["--runs", str(tmp_path), "fork", "--from", "src", "--tag", tags[0], "--lineage", "dst",
                     "--elder", "deepseek", "--elder-lives", "1"]) == 0
    capsys.readouterr()
    st = json.loads((tmp_path / "dst" / "state.json").read_text())
    got = next(x for x in st["extras"]["scheduler"]["seats"] if x["role"] == "elder")
    assert got["species"] == "deepseek" and got["max_lives"] == seat["lives"] + 1
    # the recast seat running to elders_done: tests/test_trial.py::test_dry_elder_trial_from_a_seat
