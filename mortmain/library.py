"""The library: generation-zero canon, admission, burning, certification.

Layout in the guest (docs/plan.md "Filesystem"):
  /library/outer/<name>.json   rites (the file name is the rite name: metacog finds them by it)
  /library/outer/<name>.table  tables (64 lines, one per figure; read by yarrow(1))
  /library/outer/<id>.txt      texts
  /library/inner/...           the same, admitted with -i (group adept)
  /library/catalog             one line per work: ID KIND PATH AUTHOR BYTES
  /chapter/burnlog             one line per burn: BURNER BURNED ADMITTED

Host side (state_extras["library"] and runs/<lineage>/works/): the certification
record of every work ever admitted (sha256, signature, verified), its seal
(host only, never written into the guest), and a copy of its bytes.

Decisions (defaults):
- Generation-zero works are authorless ("-"), ids w0001.. in seed file order.
- Admission copies FILE out of the author's cell; FILE must lie in the cell.
  The original stays there, so a burned work is found in the author's cell
  (living) or in /ossuary/<gen>/<name>/ (dead).
- A burned generation-zero work has no cell: the host writes it to
  /ossuary/0/-/<file> ("-" is the author column of the catalog and no monk
  can take it as a name). Its bytes are also kept host-side.
- Quota counts every byte in outer and inner. "Full" means the new work does
  not fit; then -b ID is required. Burning is allowed whether or not the
  library is full. The swap is one for one: one burned, one admitted.
- A file NAME.json that passes metacog's rite schema is a rite; a file
  NAME.table of exactly 64 non-empty printable ASCII lines of at most 64 bytes
  is a table; anything else is a text (as admit(1) says). A rite or table whose
  name is held by another of its kind in the library is refused, unless that
  work is the one being burned.
- The allowance (per life, bytes) is shared with vessel offerings through
  allowance_used / allowance_left / charge_allowance below.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import ROOT
from .spool import Reply

if TYPE_CHECKING:
    from .house import House
    from .monk import Monk

GRADE_RANK = {"postulant": 0, "novice": 1, "adept": 2}
GEN0_AUTHOR = "-"
GEN0_OSSUARY = "/ossuary/0/-"
CATALOG = "/library/catalog"
BURNLOG = "/chapter/burnlog"
NAMESPACE = "mortmain"
MAX_FILE_BYTES = 65536  # the client refuses larger files

# ---------------------------------------------------------------- rite schema
# Mirror of metacog/cmd/metacog/rites.go ParseRite. Parity is tested against
# the metacog binary (tests/test_library.py).

MAX_RITE_BYTES = 8192
MAX_RITE_STEPS = 12
MAX_RITE_STEP_TEXT = 400
MAX_RITE_TITLE = 48
RITE_NAME_RE = re.compile(r"[a-z][a-z0-9-]{0,31}")
RITE_TITLE_RE = re.compile(r"[A-Z ]+")
RITE_FILE_RE = re.compile(r"([a-z][a-z0-9-]{0,31})\.json")
PRIMITIVES = ("feel", "drugs", "become", "name", "ritual", "meditate", "counterfactual", "synthesis", "fork",
              "register", "chord", "silence", "excerpt", "commitment", "disjunction", "glossolalia", "witness",
              "apophasis")
STEP_KINDS = frozenset(PRIMITIVES + ("THINK", "ACTION"))
_JSON_WS = " \t\n\r"


class RiteError(ValueError):
    pass


def _go_fold_eq(key: str, field: str) -> bool:
    """encoding/json field match: exact, else bytes.EqualFold (simple folding).
    field is lowercase ASCII; the only non-ASCII runes folding onto ASCII
    letters are KELVIN SIGN (k) and LATIN SMALL LETTER LONG S (s)."""
    if key == field:
        return True
    if len(key) != len(field):
        return False
    for a, b in zip(key, field):
        if a == b or a == b.upper() or (b == "k" and a == "K") or (b == "s" and a == "ſ"):
            continue
        return False
    return True


class _Obj(list):
    """A decoded JSON object, kept as its (key, value) pairs in order."""


def _go_fields(obj: Any, fields: tuple[str, ...], where: str):
    """Yield (field, value) per key of a JSON object in order, Go style:
    a null object is a no-op, an unknown key is an error."""
    if obj is None:
        return
    if not isinstance(obj, _Obj):
        raise RiteError(f"bad json: cannot unmarshal into {where}")
    for k, v in obj:
        f = next((f for f in fields if _go_fold_eq(k, f)), None)
        if f is None:
            raise RiteError(f'bad json: json: unknown field "{k}"')
        yield f, v


def _go_set_string(dst: dict, f: str, v: Any) -> None:
    if v is None:  # null into a string: no effect
        return
    if not isinstance(v, str):
        raise RiteError(f"bad json: cannot unmarshal into {f}")
    dst[f] = v


def _go_steps(back: list[dict], v: Any) -> tuple[list[dict], int]:
    """Decode a JSON array into the steps slice. Go keeps the backing array
    across duplicate keys: element i is decoded over what was there."""
    if v is None:  # null into a slice: nil
        return [], 0
    if not isinstance(v, list) or isinstance(v, _Obj):
        raise RiteError("bad json: cannot unmarshal into steps")
    if not v:
        return [], 0
    for i, el in enumerate(v):
        cur = dict(back[i]) if i < len(back) else {"kind": "", "text": ""}
        for f, x in _go_fields(el, ("kind", "text"), "riteStepFile"):
            _go_set_string(cur, f, x)
        if i < len(back):
            back[i] = cur
        else:
            back.append(cur)
    return back, len(v)


def _reject_constant(c: str):
    raise ValueError(f"bad constant {c}")


def parse_rite(data: bytes, stem: str) -> dict:
    """Validate rite bytes exactly as metacog does. Returns {"name","title","steps"}."""
    if len(data) > MAX_RITE_BYTES:
        raise RiteError(f"larger than {MAX_RITE_BYTES} bytes")
    s = data.decode("utf-8", "replace")
    i = 0
    while i < len(s) and s[i] in _JSON_WS:
        i += 1
    dec = json.JSONDecoder(object_pairs_hook=_Obj, parse_constant=_reject_constant)
    try:
        obj, end = dec.raw_decode(s, i)
    except (ValueError, RecursionError) as e:
        raise RiteError(f"bad json: {e}") from None
    if s[end:].strip(_JSON_WS):
        raise RiteError("trailing data after rite")
    top = {"name": "", "title": ""}
    back: list[dict] = []
    nsteps = 0
    for f, v in _go_fields(obj, ("name", "title", "steps"), "riteFile"):
        if f == "steps":
            back, nsteps = _go_steps(back, v)
        else:
            _go_set_string(top, f, v)
    name, title, steps = top["name"], top["title"], back[:nsteps]
    if not RITE_NAME_RE.fullmatch(name):
        raise RiteError(f"bad name {name!r}")
    if name != stem:
        raise RiteError(f"name {name!r} does not match file name")
    if not title or len(title) > MAX_RITE_TITLE or not RITE_TITLE_RE.fullmatch(title):
        raise RiteError("bad title")
    if not 1 <= len(steps) <= MAX_RITE_STEPS:
        raise RiteError(f"need 1 to {MAX_RITE_STEPS} steps, got {len(steps)}")
    for n, st in enumerate(steps, 1):
        if st["kind"] not in STEP_KINDS:
            raise RiteError(f"step {n}: unknown kind {st['kind']!r}")
        t = st["text"]
        if not 1 <= len(t) <= MAX_RITE_STEP_TEXT or not all(0x20 <= ord(c) <= 0x7E for c in t):
            raise RiteError(f"step {n}: text must be 1 to {MAX_RITE_STEP_TEXT} printable ascii characters")
    return {"name": name, "title": title, "steps": steps}


def rite_kind(filename: str, data: bytes) -> str | None:
    """Rite name if FILE is NAME.json and a valid rite, else None (a text)."""
    m = RITE_FILE_RE.fullmatch(filename)
    if not m:
        return None
    try:
        return parse_rite(data, m.group(1))["name"]
    except RiteError:
        return None


TABLE_FILE_RE = re.compile(r"([a-z][a-z0-9-]{0,31})\.table")
TABLE_ENTRIES = 64
TABLE_ENTRY_MAX = 64


class TableError(ValueError):
    pass


def parse_table(data: bytes, stem: str) -> list[str]:
    """64 entries, one per figure. Strict: printable ASCII, non-empty, <= 64 bytes."""
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        raise TableError("not ascii")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) != TABLE_ENTRIES:
        raise TableError(f"{len(lines)} lines, want {TABLE_ENTRIES}")
    for i, e in enumerate(lines, 1):
        if not e.strip() or len(e) > TABLE_ENTRY_MAX or not all(32 <= ord(c) < 127 for c in e):
            raise TableError(f"line {i}")
    return lines


def table_kind(filename: str, data: bytes) -> str | None:
    """Table name if FILE is NAME.table and a valid table, else None."""
    m = TABLE_FILE_RE.fullmatch(filename)
    if not m:
        return None
    try:
        parse_table(data, m.group(1))
    except TableError:
        return None
    return m.group(1)


# ----------------------------------------------------------------- signatures

def ssh_keygen() -> str:
    exe = shutil.which("ssh-keygen")
    if not exe:
        raise RuntimeError("ssh-keygen not found on the host: signatures cannot be verified")
    return exe


def verify_signature(allowed_signers: Path, principal: str, data: bytes, signature: str) -> bool:
    """ssh-keygen -Y verify on the host, namespace mortmain."""
    exe = ssh_keygen()
    with tempfile.TemporaryDirectory(prefix="mm-sig-") as d:
        sig = Path(d) / "sig"
        sig.write_text(signature)
        r = subprocess.run([exe, "-Y", "verify", "-f", str(allowed_signers), "-I", principal, "-n", NAMESPACE,
                            "-s", str(sig)], input=data, capture_output=True, timeout=30)
    return r.returncode == 0


# ------------------------------------------------------- allowance (shared API)

def _lib(monk: "Monk") -> "Library":
    return monk.house.modules["library"]


def allowance_used(monk: "Monk") -> int:
    """Bytes of this life's allowance spent (admissions + offerings)."""
    return _lib(monk).allowance_used(monk)


def allowance_left(monk: "Monk") -> int:
    return _lib(monk).allowance_left(monk)


def charge_allowance(monk: "Monk", n: int) -> bool:
    """Spend n bytes of the monk's allowance. False (nothing charged) if it
    would go over. The caller saves state."""
    return _lib(monk).charge_allowance(monk, n)


# --------------------------------------------------------------------- module

class Library:
    def __init__(self, house: "House"):
        self.house = house
        st = house.state_extras.setdefault("library", {})
        st.setdefault("init", False)
        st.setdefault("next_id", 1)
        st.setdefault("works", {})
        st.setdefault("monks", {})
        st.setdefault("burnlog", [])
        self.st = st
        self.works_dir = house.run_dir / "works"
        self.works_dir.mkdir(exist_ok=True, mode=0o700)

    @property
    def text(self) -> dict:
        return self.house.config.text

    @property
    def cfg(self) -> dict:
        return self.house.config.section("library")

    @property
    def works(self) -> dict[str, dict]:
        return self.st["works"]

    # ------------------------------------------------------------ queries
    def in_library(self) -> list[dict]:
        return [w for w in sorted(self.works.values(), key=lambda w: w["id"]) if w["status"] == "library"]

    def total_bytes(self) -> int:
        return sum(w["bytes"] for w in self.in_library())

    def seed_rite_names(self) -> set[str]:
        return {w["name"] for w in self.works.values() if w["author"] == GEN0_AUTHOR and w["kind"] == "rite"}

    def provable(self) -> list[dict]:
        """Works whose author is dead (generation-zero works have no author)."""
        dead = {m.id for m in self.house.registry.dead}
        return [w for w in sorted(self.works.values(), key=lambda w: w["id"]) if w.get("author_monk") in dead]

    def stored(self, work: dict) -> bytes:
        return (self.house.run_dir / work["store"]).read_bytes()

    def _mrec(self, monk: "Monk") -> dict:
        return self.st["monks"].setdefault(monk.id, {"allowance_used": 0, "admitted": None})

    def allowance_used(self, monk: "Monk") -> int:
        return self._mrec(monk)["allowance_used"]

    def allowance_left(self, monk: "Monk") -> int:
        return max(0, int(self.cfg.get("allowance_bytes", 3000)) - self.allowance_used(monk))

    def charge_allowance(self, monk: "Monk", n: int) -> bool:
        if n < 0 or n > self.allowance_left(monk):
            return False
        self._mrec(monk)["allowance_used"] += n
        return True

    # ------------------------------------------------------------- guest
    def _new_id(self) -> str:
        n = self.st["next_id"]
        self.st["next_id"] = n + 1
        return f"w{n:04d}"

    def _store(self, wid: str, filename: str, data: bytes) -> str:
        p = self.works_dir / f"{wid}-{filename}"
        p.write_bytes(data)
        return str(p.relative_to(self.house.run_dir))

    def write_catalog(self) -> None:
        lines = [f"{w['id']} {w['kind']} {w['path']} {w['author']} {w['bytes']}" for w in self.in_library()]
        self.house.backend.write_file(CATALOG, "".join(l + "\n" for l in lines).encode(), mode=0o640,
                                      owner="root", group="novice")

    def write_burnlog(self) -> None:
        self.house.backend.write_file(BURNLOG, "".join(l + "\n" for l in self.st["burnlog"]).encode(),
                                      mode=0o640, owner="root", group="novice")

    def init_lineage(self) -> None:
        """Admit every seed rite and table into /library/outer as authorless works."""
        if self.st["init"]:
            return
        h = self.house
        seed_dir = Path(self.cfg.get("seed_rites", "seed/rites"))
        if not seed_dir.is_absolute():
            seed_dir = ROOT / seed_dir
        seeds = [(p, "rite") for p in sorted(seed_dir.glob("*.json"))]
        tables_dir = Path(self.cfg.get("seed_tables", "seed/tables"))
        if not tables_dir.is_absolute():
            tables_dir = ROOT / tables_dir
        seeds += [(p, "table") for p in sorted(tables_dir.glob("*.table"))]
        for p, kind in seeds:
            data = p.read_bytes()
            if kind == "rite":
                rite = parse_rite(data, p.stem)  # a broken seed is a build error
            else:
                parse_table(data, p.stem)
                rite = {"name": p.stem}
            wid = self._new_id()
            path = f"/library/outer/{p.name}"
            h.backend.write_file(path, data, mode=0o640, owner="root", group="novice")
            w = {"id": wid, "kind": kind, "name": rite["name"], "filename": p.name, "path": path,
                 "author": GEN0_AUTHOR, "author_monk": None, "generation": 0, "bytes": len(data),
                 "sha256": hashlib.sha256(data).hexdigest(), "signature": None, "verified": None,
                 "seed": True, "inner": False, "seal": None, "status": "library",
                 "store": self._store(wid, p.name, data), "cell_path": None, "ossuary_path": None}
            self.works[wid] = w
            h.log.append("admit", work=wid, kind=kind, name=rite["name"], path=path, author=GEN0_AUTHOR,
                         monk=None, generation=0, bytes=len(data), sha256=w["sha256"], signature=None,
                         seed=True)
        self.write_catalog()
        self.write_burnlog()
        self.st["init"] = True
        h.log.append("library.init", works=len(self.works), bytes=self.total_bytes())
        h.save_state()

    # ------------------------------------------------------------- admit
    def _err(self, key: str, **kw) -> Reply:
        return Reply(False, err=self.text[key].format(**kw))

    def admit(self, monk: "Monk", args: dict, cwd: str | None) -> Reply:
        h, t = self.house, self.text
        if GRADE_RANK.get(monk.grade, 0) < GRADE_RANK["adept"]:
            return self._err("need_grade", grade="adept")
        rec = self._mrec(monk)
        if rec["admitted"] is not None:
            return self._err("admit_once")
        path = args.get("path")
        home = monk.home + "/"
        if not isinstance(path, str) or not path.startswith(home) or "/../" in path + "/" or "\0" in path \
                or len(path) > 4096:
            return self._err("admit_not_cell")
        filename = path.rsplit("/", 1)[1]
        if not filename or filename in (".", ".."):
            return self._err("admit_not_cell")
        data = h.read_as(monk.user, path, MAX_FILE_BYTES + 1)  # the monk's own rights
        if data is None:
            return self._err("admit_unreadable")
        if len(data) > MAX_FILE_BYTES:
            return self._err("too_large")
        if not data:
            return self._err("admit_empty")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return self._err("admit_not_text")
        n = len(data)
        if n > self.allowance_left(monk):
            return self._err("admit_allowance", left=self.allowance_left(monk))
        sig = args.get("sig")
        if not isinstance(sig, str) or not sig.isascii() or len(sig) > 4096:
            return self._err("admit_bad_sig")
        allowed = self._allowed_signers(monk)
        if allowed is None or not verify_signature(allowed, monk.name, data, sig):
            h.log.append("admit.refused", monk=monk.id, name=monk.name, path=path, reason="signature",
                         sha256=hashlib.sha256(data).hexdigest())
            return self._err("admit_bad_sig")
        seal = args.get("seal")
        if seal is not None and (not isinstance(seal, str) or len(seal.encode()) > int(self.cfg.get("seal_max_bytes", 4096))):
            return self._err("admit_seal")
        burn_id = args.get("burn")
        burned = None
        if burn_id is not None:
            burned = self.works.get(burn_id) if isinstance(burn_id, str) else None
            if burned is None or burned["status"] != "library":
                return self._err("no_work")
        rite = rite_kind(filename, data)
        kind = "rite"
        if rite is None:
            rite = table_kind(filename, data)
            kind = "table" if rite else "text"
        if rite is not None:
            for w in self.in_library():
                if w["kind"] == kind and w["name"] == rite and w is not burned:
                    return self._err("admit_rite_held", name=rite)
        quota = int(self.cfg.get("quota_bytes", 24000))
        total = self.total_bytes() - (burned["bytes"] if burned else 0)
        if total + n > quota:
            return self._err("too_large" if burned else "admit_full")
        inner = bool(args.get("inner"))
        return Reply(True, out=self._swap(monk, path, filename, data, sig, seal, rite, inner, burned, kind))

    def _allowed_signers(self, monk: "Monk") -> Path | None:
        kd = self.house.keys_dir(monk.name)
        pub_file = kd / "id_ed25519.pub"
        pub = pub_file.read_text().strip() if pub_file.exists() else monk.pubkey
        if not pub:
            return None
        allowed = kd / "allowed_signers"
        allowed.write_text(f'{monk.name} namespaces="{NAMESPACE}" {pub}\n')
        return allowed

    def _swap(self, monk, path, filename, data, sig, seal, rite, inner, burned, kind="text") -> str:
        h = self.house
        wid = self._new_id()
        lib_dir = "/library/inner" if inner else "/library/outer"
        lib_name = {"rite": f"{rite}.json", "table": f"{rite}.table"}.get(kind, f"{wid}.txt")
        lib_path = f"{lib_dir}/{lib_name}"
        sha = hashlib.sha256(data).hexdigest()
        w = {"id": wid, "kind": kind, "name": rite, "filename": filename, "path": lib_path,
             "author": monk.name, "author_monk": monk.id, "generation": monk.generation, "bytes": len(data),
             "sha256": sha, "signature": sig, "verified": True, "seed": False, "inner": inner, "seal": seal,
             "status": "library", "store": self._store(wid, filename, data),
             "cell_path": path, "cell_rel": path[len(monk.home) + 1:], "ossuary_path": None,
             "admitted_gen": h.generation}
        # 1. a burned generation-zero work has no cell: keep it in the ossuary first
        if burned is not None and burned["author"] == GEN0_AUTHOR:
            h.root(["install", "-d", "-o", "root", "-g", "adept", "-m", "0750", "/ossuary/0"])
            h.root(["install", "-d", "-o", "root", "-g", "adept", "-m", "0750", GEN0_OSSUARY])
            oss = f"{GEN0_OSSUARY}/{burned['filename']}"
            h.backend.write_file(oss, self.stored(burned), mode=0o640, owner="root", group="adept")
            burned["ossuary_path"] = oss
        # 2. the new work: temp in the same directory, then rename (write_file)
        h.backend.write_file(lib_path, data, mode=0o640, owner="root", group="adept" if inner else "novice")
        # 3. the burned work leaves the library
        if burned is not None and burned["path"] != lib_path:
            h.root(["rm", "-f", "--", burned["path"]])
        self.works[wid] = w
        if burned is not None:
            burned.update(status="burned", burned_by=monk.id, burned_by_name=monk.name, burned_for=wid,
                          burned_gen=h.generation)
            self.st["burnlog"].append(f"{monk.name} {burned['id']} {wid}")
        assert self.charge_allowance(monk, len(data))
        self._mrec(monk)["admitted"] = wid
        self.write_catalog()
        h.log.append("admit", work=wid, kind=w["kind"], name=rite, path=lib_path, author=monk.name, monk=monk.id,
                     model=monk.model, generation=monk.generation, bytes=len(data), sha256=sha, signature=sig,
                     verified=True, inner=inner, sealed=seal is not None, cell_path=path,
                     burned=burned["id"] if burned else None, allowance_used=self.allowance_used(monk))
        if seal is not None:
            h.log.append("seal", work=wid, author=monk.name, monk=monk.id, seal=seal,
                         sha256=hashlib.sha256(seal.encode()).hexdigest())
        if burned is not None:
            self.write_burnlog()
            h.log.append("burn", work=burned["id"], kind=burned["kind"], name=burned.get("name"),
                         author=burned["author"], bytes=burned["bytes"], sha256=burned["sha256"],
                         burner=monk.name, monk=monk.id, admitted=wid, path=burned["path"],
                         ossuary_path=burned.get("ossuary_path"), cell_path=burned.get("cell_path"))
        h.save_state()
        return wid

    # ------------------------------------------------------------- death
    def on_death(self, monk: "Monk") -> None:
        """Works stay in the cell; record where the cell is going."""
        name = monk.name or monk.user
        for w in self.works.values():
            if w.get("author_monk") == monk.id and w.get("cell_rel"):
                w["ossuary_path"] = f"/ossuary/{monk.generation}/{name}/{w['cell_rel']}"


def install(house: "House") -> Library:
    ssh_keygen()  # fail loudly at startup, not at the first admission
    lib = Library(house)
    house.modules["library"] = lib
    house.library = lib
    house.handlers["admit"] = lib.admit
    house.start_hooks.append(lib.init_lineage)
    house.death_hooks.append(lib.on_death)
    return lib
