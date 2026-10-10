import json

import pytest

from mortmain.eventlog import GENESIS, EventLog, iter_records, verify


def _write(path, n=5):
    with EventLog(path) as log:
        for i in range(n):
            log.append("turn", monk="m0001", i=i, text="ünïcode")
    return path


def test_chain_appends_and_verifies(tmp_path):
    p = _write(tmp_path / "e.jsonl")
    recs = list(iter_records(p))
    assert [r["seq"] for r in recs] == list(range(5))
    assert recs[0]["prev"] == GENESIS
    assert all(recs[i]["prev"] == recs[i - 1]["hash"] for i in range(1, 5))
    r = verify(p)
    assert r.ok and r.count == 5


def test_reopen_continues_chain(tmp_path):
    p = _write(tmp_path / "e.jsonl", 3)
    with EventLog(p) as log:
        rec = log.append("death", monk="m0001")
    assert rec["seq"] == 3
    assert verify(p).count == 4


def test_second_writer_refused(tmp_path):
    p = tmp_path / "e.jsonl"
    with EventLog(p):
        with pytest.raises(RuntimeError):
            EventLog(p)


def test_reserved_fields_rejected(tmp_path):
    with EventLog(tmp_path / "e.jsonl") as log:
        with pytest.raises(ValueError):
            log.append("turn", hash="x")


def _lines(p):
    return p.read_text().splitlines(keepends=True)


@pytest.mark.parametrize("tamper", ["edit", "delete", "swap", "append_forged", "truncate", "rehash_one"])
def test_tamper_detected(tmp_path, tamper):
    p = _write(tmp_path / "e.jsonl")
    lines = _lines(p)
    if tamper == "edit":
        r = json.loads(lines[2]); r["i"] = 99; lines[2] = json.dumps(r) + "\n"
    elif tamper == "delete":
        del lines[2]
    elif tamper == "swap":
        lines[1], lines[2] = lines[2], lines[1]
    elif tamper == "append_forged":
        lines.append(json.dumps({"seq": 5, "ts": 0, "prev": "f" * 64, "type": "x", "hash": "0" * 64}) + "\n")
    elif tamper == "truncate":
        lines[-1] = lines[-1][:-10]
    elif tamper == "rehash_one":
        # recompute an edited record's own hash: the next link still breaks
        from mortmain.eventlog import record_hash
        r = json.loads(lines[2]); r["i"] = 99
        r["hash"] = record_hash(r["prev"], {k: v for k, v in r.items() if k != "hash"})
        lines[2] = json.dumps(r) + "\n"
    p.write_text("".join(lines))
    r = verify(p)
    assert not r.ok, r


def test_fsync_called(tmp_path, monkeypatch):
    import mortmain.eventlog as el
    calls = []
    real = el.os.fsync
    monkeypatch.setattr(el.os, "fsync", lambda fd: (calls.append(fd), real(fd)))
    with EventLog(tmp_path / "e.jsonl") as log:
        log.append("x")
    assert calls
