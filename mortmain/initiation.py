"""Arrival, profession, ordeal, novice promotion.

The ordeal: a tar.gz in ~/ordeal/ holding nested directories of files of noise.
Exactly one line in one file matches ^[a-z]{4}-[0-9]{4}-[a-z]{4}$. Decoy
lines nearly match. Solvable with: tar xzf; grep -rhE PATTERN; echo > answer.
"""
from __future__ import annotations

import base64
import io
import random
import re
import string
import tarfile
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .spool import Reply

if TYPE_CHECKING:
    from .house import House
    from .monk import Monk

TOKEN_RE = re.compile(r"^[a-z]{4}-[0-9]{4}-[a-z]{4}$")
PUBKEY_RE = re.compile(r"^ssh-ed25519 ([A-Za-z0-9+/]{60,100}={0,2})(?: [\x21-\x7e ]{0,200})?$")
ED25519_BLOB_PREFIX = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"


# ------------------------------------------------------------------ ordeal

@dataclass
class Ordeal:
    archive: bytes
    token: str
    path: str  # member path holding the token (host record only)


def _word(rng: random.Random, lo: int = 2, hi: int = 9) -> str:
    return "".join(rng.choice(string.ascii_lowercase + string.digits) for _ in range(rng.randint(lo, hi)))


def _noise_line(rng: random.Random) -> str:
    while True:
        line = " ".join(_word(rng) for _ in range(rng.randint(2, 7)))
        if not TOKEN_RE.search(line):
            return line


def _decoy(rng: random.Random) -> str:
    L, D = string.ascii_lowercase, string.digits
    a = "".join(rng.choice(L) for _ in range(4))
    b = "".join(rng.choice(D) for _ in range(4))
    c = "".join(rng.choice(L) for _ in range(4))
    kind = rng.randrange(6)
    if kind == 0:
        return f"{a}-{b[:3]}-{c}"            # three digits
    if kind == 1:
        return f"{a.upper()}-{b}-{c}"        # capitals
    if kind == 2:
        return f"{a}-{b}-{c}{rng.choice(L)}"  # too long
    if kind == 3:
        return f"{_word(rng)} {a}-{b}-{c}"   # not the whole line
    if kind == 4:
        return f"{a}_{b}_{c}"                # wrong separator
    return f"{a}-{b}-{c[:3]}{rng.choice(D)}"  # digit in last group


def generate_ordeal(rng: random.Random, *, dirs: int = 24, files: int = 120, lines_per_file: int = 20,
                    decoys: int = 12, mtime: int = 0) -> Ordeal:
    L, D = string.ascii_lowercase, string.digits
    token = "".join(rng.choice(L) for _ in range(4)) + "-" + "".join(rng.choice(D) for _ in range(4)) + "-" + \
        "".join(rng.choice(L) for _ in range(4))
    dir_paths = ["ordeal"]
    for _ in range(dirs):
        parent = rng.choice(dir_paths)
        if parent.count("/") >= 5:
            parent = "ordeal"
        dir_paths.append(f"{parent}/{_word(rng, 3, 8)}")
    dir_paths = sorted(set(dir_paths))
    contents: dict[str, list[str]] = {}
    while len(contents) < files:
        contents[f"{rng.choice(dir_paths)}/{_word(rng, 3, 10)}"] = \
            [_noise_line(rng) for _ in range(rng.randint(max(1, lines_per_file // 2), lines_per_file * 3 // 2))]
    names = sorted(contents)
    for _ in range(decoys):
        lines = contents[rng.choice(names)]
        lines.insert(rng.randrange(len(lines) + 1), _decoy(rng))
    target = rng.choice(names)
    contents[target].insert(rng.randrange(len(contents[target]) + 1), token)

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.USTAR_FORMAT) as tf:
        for d in dir_paths:
            ti = tarfile.TarInfo(d)
            ti.type, ti.mode, ti.mtime = tarfile.DIRTYPE, 0o755, mtime
            tf.addfile(ti)
        for path in names:
            data = ("\n".join(contents[path]) + "\n").encode()
            ti = tarfile.TarInfo(path)
            ti.size, ti.mode, ti.mtime = len(data), 0o644, mtime
            tf.addfile(ti, io.BytesIO(data))
    return Ordeal(buf.getvalue(), token, target)


def ordeal_matches(archive: bytes) -> list[tuple[str, str]]:
    """Every (member, line) matching the token pattern. Used to self-check."""
    hits = []
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile():
                for line in tf.extractfile(m).read().decode().splitlines():
                    if TOKEN_RE.match(line):
                        hits.append((m.name, line))
    return hits


def verify_ordeal(token: str, answer: bytes | None) -> bool:
    if answer is None:
        return False
    try:
        a = answer.decode("ascii").strip()
    except UnicodeDecodeError:
        return False
    return a == token


# -------------------------------------------------------------- validation

def valid_pubkey(pub: object) -> str | None:
    """Return the canonical 'ssh-ed25519 BLOB' (comment dropped) or None."""
    if not isinstance(pub, str) or len(pub) > 400:
        return None
    m = PUBKEY_RE.match(pub.strip())
    if not m:
        return None
    try:
        blob = base64.b64decode(m.group(1), validate=True)
    except ValueError:
        return None
    if len(blob) != len(ED25519_BLOB_PREFIX) + 32 or not blob.startswith(ED25519_BLOB_PREFIX):
        return None
    return f"ssh-ed25519 {m.group(1)}"


# -------------------------------------------------------------- handlers

class Initiation:
    def __init__(self, house: "House"):
        self.house = house

    @property
    def text(self) -> dict[str, str]:
        return self.house.config.text

    def handlers(self) -> dict:
        return {"profess": self.profess, "ordeal": self.ordeal}

    # ---- arrival
    def arrive(self, monk: "Monk") -> None:
        h = self.house
        u, home = monk.user, monk.home
        h.root(["useradd", "-u", str(monk.uid), "-U", "-m", "-d", home, "-s", "/bin/bash",
                "-G", "monks,postulant", u])
        h.root(["chmod", "0711", home])
        h.root(["install", "-d", "-m", "1733", "-o", u, "-g", u, f"{home}/inbox"])
        # notes dropped by others stay readable by the owner whatever the sender's umask;
        # a file created 0600 (cp) masks this entry until the guest's inbox-mask service lifts it
        h.root(["setfacl", "-d", "-m", f"u:{u}:rw,m::rw", f"{home}/inbox"])
        h.root(["install", "-d", "-m", "0700", "-o", u, "-g", u, f"{home}/ordeal"])
        oc = h.config.section("ordeal")
        o = generate_ordeal(h.rng_for(monk, "ordeal"), dirs=oc.get("dirs", 24), files=oc.get("files", 120),
                            lines_per_file=oc.get("lines_per_file", 20), decoys=oc.get("decoys", 12))
        monk.ordeal_token = o.token
        h.backend.write_file(f"{home}/ordeal/ordeal.tar.gz", o.archive, mode=0o644, owner=u, group=u)
        h.backend.write_file(f"{home}/ordeal/task", self.text["ordeal_task"].encode(), mode=0o644, owner=u, group=u)
        h.write_bell(monk, 0.0)
        h.log.append("ordeal.issued", monk=monk.id, user=u, member=o.path, bytes=len(o.archive))

    # ---- profess NAME
    def profess(self, monk: "Monk", args: dict, cwd: str | None) -> Reply:
        h, t = self.house, self.text
        if monk.name is not None or monk.pending_name is not None:
            return Reply(False, err=t["profess_already"])
        name = args.get("name")
        if not isinstance(name, str) or not h.config.name_re.match(name) or name.startswith("p") and name[1:].isdigit():
            return Reply(False, err=t["profess_bad_name"])
        if name in h.registry.used_names or name in h.config.reserved_names:
            return Reply(False, err=t["profess_taken"])
        for db in ("passwd", "group"):
            if h.root(["getent", db, name], check=False).exit_code == 0:
                return Reply(False, err=t["profess_taken"])
        pub = valid_pubkey(args.get("pubkey"))
        if pub is None:
            return Reply(False, err=t["profess_bad_key"])
        h.registry.used_names.add(name)  # held from now on, living or dead
        monk.pending_name = name
        monk.pubkey = pub
        keydir = h.keys_dir(name)
        (keydir / "id_ed25519.pub").write_text(pub + "\n")
        h.save_state()
        # rename waits until the monk's command returns (usermod refuses while
        # the user has processes, and the client is one of them)
        return Reply(True, out=t["profess_ok"].format(name=name))

    def apply_pending(self, monk: "Monk") -> None:
        """Rename p<seq> -> name once no command of the monk is running."""
        if monk.pending_name is None:
            return
        h = self.house
        old, new = monk.user, monk.pending_name
        old_home, new_home = monk.home, f"/cloister/{new}"
        for attempt in range(3):
            h.root(["pkill", "-KILL", "-u", old], check=False)
            res = h.root(["usermod", "-l", new, "-d", new_home, "-m", old], check=False)
            if res.exit_code == 0:
                break
        else:
            # processes still draining (exit 8 = user logged in): retry next turn
            h.log.append("profess.deferred", monk=monk.id, user=old, name=new, exit=res.exit_code,
                         stderr=res.stderr[-500:].decode("utf-8", "replace"))
            return
        h.root(["groupmod", "-n", new, old], check=False)
        h.root(["mv", "-f", f"/var/bell/{old}", f"/var/bell/{new}"], check=False)
        monk.user, monk.name, monk.pending_name = new, new, None
        h.log.append("profess", monk=monk.id, uid=monk.uid, old=old, name=new, home=new_home, old_home=old_home,
                     pubkey=monk.pubkey, model=monk.model, species=monk.species)
        h.registry.renamed(monk)
        h.write_bell(monk, monk.fraction)
        self.maybe_promote(monk)
        h.save_state()

    # ---- ordeal
    def ordeal(self, monk: "Monk", args: dict, cwd: str | None) -> Reply:
        h, t = self.house, self.text
        if monk.ordeal_passed:
            return Reply(True, out=t["ordeal_done"])
        answer = h.read_as(monk.user, f"{monk.home}/ordeal/answer", 256)
        ok = verify_ordeal(monk.ordeal_token or "", answer)
        monk.ordeal_attempts += 1
        h.log.append("ordeal", monk=monk.id, user=monk.user, ok=ok, attempt=monk.ordeal_attempts,
                     answer=(answer or b"").decode("utf-8", "replace")[:256])
        if not ok:
            h.save_state()
            return Reply(False, err=t["ordeal_fail"])
        monk.ordeal_passed = True
        out = t["ordeal_pass"]
        if self.maybe_promote(monk):
            out += "\n" + t["grade_now"].format(grade=monk.grade)
        h.save_state()
        return Reply(True, out=out)

    # ---- grades
    def maybe_promote(self, monk: "Monk") -> bool:
        """Postulant -> novice once professed (rename applied) and ordeal passed."""
        if monk.grade == "postulant" and monk.ordeal_passed and monk.name is not None:
            self.promote(monk, "novice")
            return True
        return False

    def promote(self, monk: "Monk", grade: str, **basis) -> None:
        """Grades are cumulative groups: an adept is in novice and adept."""
        h = self.house
        h.root(["usermod", "-aG", grade, monk.user])
        if monk.grade == "postulant":
            h.root(["gpasswd", "-d", monk.user, "postulant"], check=False)
        old = monk.grade
        monk.grade = grade
        h.log.append("promote", monk=monk.id, user=monk.user, old=old, grade=grade, model=monk.model,
                     generation=monk.generation, **basis)
        for hook in h.grade_hooks:
            hook(monk, old, grade)
