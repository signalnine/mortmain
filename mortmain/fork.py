"""Fork a lineage from a snapshot export (House.snapshot, [snapshots] export).

    python -m mortmain fork --from L --tag gen-3 --lineage L2
    python -m mortmain run --lineage L2 --rung full --image vm/images/gen0.qcow2 ...

The new lineage gets the host state as of the tag (state.json, each monk's
conversation cut to its length then, the keys of monks dead by then, the
works in the library then, the secret) and a pending import: on its first
start the House boots a fresh overlay of gen0 and extracts the tag's house
trees over it. Its event log starts fresh with a "fork" record naming the
source; the source lineage is not touched. No VM image is needed.

`elder` / `elder_lives` recast the scheduler's elder seat for births after the
tag: its species, and how many more elder lives before the run ends (the elder
seat trial: one house state, a different elder each time). A living elder at
the tag keeps its species. `dst_root` puts the new lineage under another runs
root (a trial's directory).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

PENDING = "fork.json"


def fork(runs_root: Path, src: str, tag: str, dst: str, dst_root: Path | None = None,
         elder: str | None = None, elder_lives: int | None = None) -> Path:
    s, d = runs_root / src, (dst_root or runs_root) / dst
    tgz, meta_path = s / "snapshots" / f"{tag}.tgz", s / "snapshots" / f"{tag}.json"
    if not tgz.exists() or not meta_path.exists():
        raise FileNotFoundError(f"{src}: no export for {tag} (snapshots/{tag}.tgz/.json)")
    if d.exists():
        raise FileExistsError(f"{d} exists")
    meta = json.loads(meta_path.read_text())
    st = meta["state"]
    st["lineage"] = dst
    if elder is not None or elder_lives is not None:
        seats = ((st.get("extras") or {}).get("scheduler") or {}).get("seats") or []
        seat = next((x for x in seats if x["role"] == "elder"), None)
        if seat is None:
            raise ValueError(f"{src} {tag}: no elder seat to recast")
        if elder is not None:
            seat["species"] = elder
        if elder_lives is not None:
            seat["max_lives"] = seat["lives"] + elder_lives
    (d / "snapshots").mkdir(parents=True)
    (d / "conversations").mkdir()
    (d / "keys").mkdir(mode=0o700)
    shutil.copy2(tgz, d / "snapshots" / tgz.name)
    shutil.copy2(meta_path, d / "snapshots" / meta_path.name)
    (d / "state.json").write_text(json.dumps(st, indent=1))
    if (s / "secret").exists():
        shutil.copy2(s / "secret", d / "secret")
    for mid, n in meta["conversations"].items():
        p = s / "conversations" / f"{mid}.jsonl"
        if p.exists():
            lines = [x for x in p.read_text().split("\n") if x.strip()][:n]
            (d / "conversations" / p.name).write_text("".join(x + "\n" for x in lines))
    for m in st["monks"]:
        kp = ((m.get("death") or {}).get("keys") or {}).get("path")
        if kp and (s / kp).parent.is_dir():
            shutil.copytree(s / kp.rsplit("/", 1)[0], d / kp.rsplit("/", 1)[0], dirs_exist_ok=True)
    works = (st.get("extras", {}).get("library", {}) or {}).get("works", {})
    if (s / "works").is_dir():
        (d / "works").mkdir()
        for p in (s / "works").iterdir():
            if p.name.split("-", 1)[0].split(".", 1)[0] in works:
                shutil.copy2(p, d / "works" / p.name)
    for sub in ("catechism", "tripwire"):
        (d / sub).mkdir()
    (d / PENDING).write_text(json.dumps({"from": src, "tag": tag, "seq": meta["seq"],
                                          "sha256": hashlib.sha256(tgz.read_bytes()).hexdigest()}))
    return d
