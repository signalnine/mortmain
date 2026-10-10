"""Append-only, hash-chained JSONL event log (docs/plan.md "Host state").

Each record: {"seq", "ts", "prev", "hash", "type", ...fields}
hash = sha256(prev + canonical_json(record without "hash")).
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

GENESIS = "0" * 64
RESERVED = ("seq", "ts", "prev", "hash", "type")


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_hash(prev: str, record_without_hash: dict) -> str:
    return hashlib.sha256((prev + canonical_json(record_without_hash)).encode("utf-8")).hexdigest()


@dataclass
class VerifyResult:
    ok: bool
    count: int
    error: str | None = None
    line: int | None = None

    def __bool__(self) -> bool:
        return self.ok


class EventLog:
    def __init__(self, path: str | Path, *, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o640)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self._fd)
            raise RuntimeError(f"event log {self.path} is held by another process")
        self.seq, self.prev = self._tail()

    def _tail(self) -> tuple[int, str]:
        last = None
        with open(self.path, "rb") as f:
            for line in f:
                if line.strip():
                    last = line
        if last is None:
            return -1, GENESIS
        rec = json.loads(last)
        return rec["seq"], rec["hash"]

    def append(self, type: str, **fields: Any) -> dict:
        for k in RESERVED:
            if k in fields:
                raise ValueError(f"reserved event field: {k}")
        rec = {"seq": self.seq + 1, "ts": round(self._clock(), 6), "prev": self.prev, "type": type}
        rec.update(fields)
        rec["hash"] = record_hash(self.prev, {k: v for k, v in rec.items() if k != "hash"})
        line = (canonical_json(rec) + "\n").encode("utf-8")
        os.write(self._fd, line)
        os.fsync(self._fd)
        self.seq, self.prev = rec["seq"], rec["hash"]
        return rec

    def close(self) -> None:
        if self._fd >= 0:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = -1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def iter_records(path: str | Path) -> Iterator[dict]:
    with open(path, "rb") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def verify(path: str | Path) -> VerifyResult:
    """Re-check every link of the chain. Detects edits, deletions, insertions, reordering."""
    prev = GENESIS
    n = 0
    try:
        f = open(path, "rb")
    except FileNotFoundError:
        return VerifyResult(False, 0, "missing", None)
    with f:
        for lineno, raw in enumerate(f, 1):
            if not raw.strip():
                return VerifyResult(False, n, "blank line", lineno)
            if not raw.endswith(b"\n"):
                return VerifyResult(False, n, "truncated last line", lineno)
            try:
                rec = json.loads(raw)
            except ValueError:
                return VerifyResult(False, n, "bad json", lineno)
            if not isinstance(rec, dict) or "hash" not in rec:
                return VerifyResult(False, n, "no hash", lineno)
            if rec.get("seq") != n:
                return VerifyResult(False, n, f"seq {rec.get('seq')} != {n}", lineno)
            if rec.get("prev") != prev:
                return VerifyResult(False, n, "prev mismatch", lineno)
            body = {k: v for k, v in rec.items() if k != "hash"}
            if record_hash(prev, body) != rec["hash"]:
                return VerifyResult(False, n, "hash mismatch", lineno)
            prev = rec["hash"]
            n += 1
    return VerifyResult(True, n)
