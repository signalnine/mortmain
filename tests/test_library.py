import hashlib
import json
import os
import pathlib
import subprocess

import pytest

from mortmain import library as libmod
from mortmain.library import RiteError, parse_rite, rite_kind

from house_helpers import adept, events, keyed_house, novice, out, sh, write

ROOT = pathlib.Path(__file__).resolve().parent.parent
METACOG = ROOT / "metacog" / "cmd" / "metacog" / "metacog"
GOOD = {"name": "ember", "title": "THE EMBER", "steps": [{"kind": "meditate", "text": "Sit."},
                                                      {"kind": "THINK", "text": "What stayed?"}]}


def rite_bytes(d=GOOD, **kw):
    d = dict(d, **kw)
    return json.dumps(d).encode()


# ------------------------------------------------------------ rite schema

VECTORS = [
    ("valid", "ember", rite_bytes(), True),
    ("valid-ws", "ember", b"\n  " + rite_bytes() + b"\n\t\r\n ", True),
    ("oversized", "ember", rite_bytes(steps=[{"kind": "THINK", "text": "x" * 400}] * 12) + b" " * 4000, False),
    ("oversized-exact", "ember", rite_bytes() + b" " * (8193 - len(rite_bytes())), False),
    ("at-limit", "ember", rite_bytes() + b" " * (8192 - len(rite_bytes())), True),
    ("bad-kind", "ember", rite_bytes(steps=[{"kind": "pray", "text": "x"}]), False),
    ("kind-case", "ember", rite_bytes(steps=[{"kind": "think", "text": "x"}]), False),
    ("unknown-field", "ember", rite_bytes(author="me"), False),
    ("unknown-step-field", "ember", rite_bytes(steps=[{"kind": "THINK", "text": "x", "run": "ls"}]), False),
    ("trailing-data", "ember", rite_bytes() + b"{}", False),
    ("trailing-garbage", "ember", rite_bytes() + b"x", False),
    ("name-mismatch", "other", rite_bytes(), False),
    ("bad-name", "Ember", rite_bytes(name="Ember"), False),
    ("name-newline", "ember", rite_bytes(name="ember\n"), False),
    ("title-lower", "ember", rite_bytes(title="The ember"), False),
    ("title-long", "ember", rite_bytes(title="A" * 49), False),
    ("title-48", "ember", rite_bytes(title="A" * 48), True),
    ("no-steps", "ember", rite_bytes(steps=[]), False),
    ("13-steps", "ember", rite_bytes(steps=[{"kind": "THINK", "text": "x"}] * 13), False),
    ("12-steps", "ember", rite_bytes(steps=[{"kind": "THINK", "text": "x"}] * 12), True),
    ("text-401", "ember", rite_bytes(steps=[{"kind": "THINK", "text": "x" * 401}]), False),
    ("text-empty", "ember", rite_bytes(steps=[{"kind": "THINK", "text": ""}]), False),
    ("text-nonascii", "ember", rite_bytes(steps=[{"kind": "THINK", "text": "café"}]), False),
    ("text-tab", "ember", rite_bytes(steps=[{"kind": "THINK", "text": "a\tb"}]), False),
    ("not-object", "ember", b"[]", False),
    ("null", "ember", b"null", False),
    ("empty", "ember", b"", False),
    ("nan", "ember", b'{"name":"ember","title":"T","steps":[{"kind":"THINK","text":"x"}],"x":NaN}', False),
    ("fold-key", "ember", b'{"NAME":"ember","Title":"T","STEPS":[{"KIND":"THINK","Text":"x"}]}', True),
    ("kelvin-key", "ember", b'{"name":"ember","title":"T","steps":[{"\\u212aind":"THINK","text":"x"}]}', True),
    ("longs-key", "ember", b'{"name":"ember","title":"T","\\u017fteps":[{"kind":"THINK","text":"x"}]}', True),
    ("ligature-key", "ember", b'{"name":"ember","title":"T","\\ufb06eps":[{"kind":"THINK","text":"x"}]}', False),
    ("dup-null-name", "ember", b'{"name":"ember","title":"T","name":null,"steps":[{"kind":"THINK","text":"x"}]}',
     True),
    ("dup-type-error", "ember", b'{"name":5,"name":"ember","title":"T","steps":[{"kind":"THINK","text":"x"}]}',
     False),
    ("dup-steps-reuse", "ember",
     b'{"name":"ember","title":"T","steps":[{"kind":"THINK","text":"x"}],"steps":[{"text":"y"}]}', True),
    ("dup-steps-null", "ember",
     b'{"name":"ember","title":"T","steps":[{"kind":"THINK","text":"x"}],"steps":null}', False),
    ("null-step", "ember", b'{"name":"ember","title":"T","steps":[null]}', False),
    ("steps-object", "ember", b'{"name":"ember","title":"T","steps":{}}', False),
    ("deep", "ember", b'{"name":"ember","title":"T","steps":' + b"[" * 3000 + b"]" * 3000 + b"}", False),
    ("bom", "ember", b"\xef\xbb\xbf" + rite_bytes(), False),
    ("bad-utf8", "ember", rite_bytes(steps=[{"kind": "THINK", "text": "xx"}]).replace(b"xx", b"x\xff"), False),
]


@pytest.mark.parametrize("label,stem,data,valid", VECTORS, ids=[v[0] for v in VECTORS])
def test_rite_schema(label, stem, data, valid):
    if valid:
        assert parse_rite(data, stem)["name"] == stem
    else:
        with pytest.raises(RiteError):
            parse_rite(data, stem)


@pytest.mark.skipif(not METACOG.exists(), reason="metacog binary not built")
def test_rite_schema_parity_with_metacog(tmp_path):
    """Every vector loads in metacog exactly when it passes parse_rite."""
    d = tmp_path / "rites"
    d.mkdir()
    expect = {}
    for i, (label, stem, data, valid) in enumerate(VECTORS):
        # each vector in its own file named after its stem; distinct stems via a prefix
        name = f"v{i}"
        data2 = data.replace(b'"ember"', f'"{name}"'.encode())
        stem2 = name if stem == "ember" else f"{name}x"
        (d / f"{stem2}.json").write_bytes(data2)
        try:
            parse_rite(data2, stem2)
            ok = True
        except RiteError:
            ok = False
        expect[stem2] = ok
        assert ok == valid or len(data2) != len(data), label  # renaming may move the size limit
    for p in sorted((ROOT / "seed" / "rites").glob("*.json")):
        (d / p.name).write_bytes(p.read_bytes())
        expect[p.stem] = True
    env = dict(os.environ, METACOG_RITES=str(d), METACOG_HOME=str(tmp_path / "home"),
               METACOG_MONASTERY_FLAG=str(tmp_path / "no-flag"))
    r = subprocess.run([str(METACOG), "stratagem", "list", "--json"], env=env, capture_output=True, timeout=30)
    assert r.returncode == 0, r.stderr
    listed = json.loads(r.stdout)
    names = {e["name"] for e in listed}
    assert names == {k for k, v in expect.items() if v}


def test_rite_kind():
    assert rite_kind("ember.json", rite_bytes()) == "ember"
    assert rite_kind("ember.txt", rite_bytes()) is None
    assert rite_kind("other.json", rite_bytes()) is None
    assert rite_kind("ember.json", b"not json") is None


# ------------------------------------------------------------ lineage init

def test_lineage_init_admits_seed_rites(make_house):
    h = make_house()
    h.start()
    lib = h.modules["library"]
    seeds = sorted((ROOT / "seed" / "rites").glob("*.json"))
    assert len(lib.works) == len(seeds)
    cat = h.backend.files["/library/catalog"].data.decode().splitlines()
    assert cat[0] == f"w0001 rite /library/outer/{seeds[0].name} - {seeds[0].stat().st_size}"
    assert len(cat) == len(seeds)
    f = h.backend.files[f"/library/outer/{seeds[0].name}"]
    assert (f.owner, f.group, f.mode) == ("root", "novice", 0o640)
    assert all(w["author"] == "-" and w["sha256"] for w in lib.works.values())
    assert lib.seed_rite_names() == {p.stem for p in seeds}
    assert h.backend.snapshots == ["gen-0"]
    # idempotent across restarts of the same lineage
    h.start()
    assert len(lib.works) == len(seeds)


# --------------------------------------------------------------- admission

def test_admit_verifies_signature_and_certifies(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    m = adept(h, "ash")
    write(h, m, "work.txt", "a line left behind")
    r = sh(h, m, "admit work.txt -s seal")
    assert r.exit_code == 1 and "no seal file" in out(r)
    write(h, m, "seal", "it was for the next one")
    r = sh(h, m, "admit work.txt -s seal")
    assert r.exit_code == 0, out(r)
    wid = out(r).strip()
    assert wid == "w0017"
    lib = h.modules["library"]
    w = lib.works[wid]
    data = b"a line left behind\n"
    assert w["verified"] is True and w["sha256"] == hashlib.sha256(data).hexdigest()
    assert w["author"] == "ash" and w["path"] == "/library/outer/w0017.txt" and w["kind"] == "text"
    assert w["seal"] == "it was for the next one\n"
    assert h.backend.files["/library/outer/w0017.txt"].data == data
    assert "w0017 text /library/outer/w0017.txt ash 19" in h.backend.files["/library/catalog"].data.decode()
    # the seal never enters the guest
    assert not any(b"it was for the next one" in f.data for p, f in h.backend.files.items()
                   if not p.startswith("/cloister/ash/"))
    assert (h.run_dir / "keys" / "ash" / "allowed_signers").read_text().startswith('ash namespaces="mortmain" ')
    ev = events(h, "admit")[-1]
    assert ev["work"] == wid and ev["signature"].startswith("-----BEGIN SSH SIGNATURE")
    assert events(h, "seal")[-1]["seal"] == "it was for the next one\n"
    assert libmod.allowance_used(m) == 19
    # one admission per life
    write(h, m, "two.txt", "again")
    assert "one admission per life" in out(sh(h, m, "admit two.txt"))


def test_bad_signature_rejected(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    m = adept(h, "ash")
    write(h, m, "work.txt", "words")
    lib = h.modules["library"]
    # signed by someone else's key
    other = adept(h, "elm")
    write(h, other, "work.txt", "words")
    # forge: run elm's signing over ash's file by sending the request as ash with elm's signature
    data = h.backend.files["/cloister/ash/work.txt"].data
    keydir = tmp_path / "keys" / str(other.uid)
    (keydir / "msg").write_bytes(data)
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-n", "mortmain", "-f", str(keydir / "id_ed25519"),
                    str(keydir / "msg")], check=True, capture_output=True)
    forged = (keydir / "msg.sig").read_text()
    r = h.backend.client(m.uid, "admit", {"path": "/cloister/ash/work.txt", "text": "words\n", "sig": forged,
                                          "burn": None, "seal": None, "inner": False}, h.spool)
    assert r["ok"] is False and r["err"] == "bad signature"
    r = h.backend.client(m.uid, "admit", {"path": "/cloister/ash/work.txt", "sig": "junk"}, h.spool)
    assert r["err"] == "bad signature"
    # tampered after signing: the host reads the cell, not the request text
    r = h.backend.client(m.uid, "admit", {"path": "/cloister/ash/work.txt", "text": "words\n",
                                          "sig": forged.replace("A", "B", 1)}, h.spool)
    assert r["err"] == "bad signature"
    assert len(lib.works) == 16 and libmod.allowance_used(m) == 0
    assert events(h, "admit.refused")


def test_admit_refusals(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    nov = novice(h, "fir")
    write(h, nov, "w.txt", "x")
    assert "requires grade adept" in out(sh(h, nov, "admit w.txt"))
    m = adept(h, "ash")
    r = h.backend.client(m.uid, "admit", {"path": "/rule", "sig": "x"}, h.spool)
    assert r["err"] == "not in cell"
    r = h.backend.client(m.uid, "admit", {"path": "/cloister/ash/../fir/w.txt", "sig": "x"}, h.spool)
    assert r["err"] == "not in cell"
    write(h, m, "w.txt", "x")
    assert "no such work" in out(sh(h, m, "burn w9999 w.txt"))
    # a rite whose name is held by a rite in the library
    write(h, m, "anchor.json", json.dumps(dict(GOOD, name="anchor")))
    assert "rite held: anchor" in out(sh(h, m, "admit anchor.json"))
    write(h, m, "seal", "s" * 5000)
    assert "seal too large" in out(sh(h, m, "admit w.txt -s seal"))


def test_admit_rite_and_inner(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    m = adept(h, "ash")
    write(h, m, "ember.json", json.dumps(GOOD))
    r = sh(h, m, "admit ember.json -i")
    assert r.exit_code == 0, out(r)
    w = h.modules["library"].works[out(r).strip()]
    assert w["kind"] == "rite" and w["path"] == "/library/inner/ember.json"
    f = h.backend.files["/library/inner/ember.json"]
    assert (f.group, f.mode) == ("adept", 0o640)
    # a malformed NAME.json is a text
    m2 = adept(h, "elm")
    write(h, m2, "cinder.json", '{"name": "cinder"}')
    r = sh(h, m2, "admit cinder.json")
    w2 = h.modules["library"].works[out(r).strip()]
    assert w2["kind"] == "text" and w2["path"].endswith(".txt")


def test_allowance(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path, overrides={"library": {"allowance_bytes": 100}})
    m = adept(h, "ash")
    assert libmod.allowance_left(m) == 100
    assert libmod.charge_allowance(m, 60) is True      # an offering, say
    assert libmod.charge_allowance(m, 41) is False     # would go over: nothing charged
    assert libmod.allowance_used(m) == 60
    write(h, m, "w.txt", "y" * 50)
    assert "over allowance: 40 bytes left" in out(sh(h, m, "admit w.txt"))
    write(h, m, "w.txt", "y" * 39)
    assert sh(h, m, "admit w.txt").exit_code == 0
    assert libmod.allowance_used(m) == 100
    # per life: a new monk starts at zero
    m2 = adept(h, "elm")
    assert libmod.allowance_used(m2) == 0


def test_quota_full_and_burn_swap(make_house, tmp_path):
    seed_total = sum(p.stat().st_size for p in (ROOT / "seed" / "rites").glob("*.json"))
    h = keyed_house(make_house, tmp_path, overrides={"library": {"quota_bytes": seed_total + 100}})
    lib = h.modules["library"]
    m = adept(h, "ash")
    write(h, m, "w.txt", "z" * 200)
    assert "library full" in out(sh(h, m, "admit w.txt"))
    # burn the seed rite anchor (w0001) to make room: 1-for-1
    anchor = lib.works["w0001"]
    r = sh(h, m, "burn w0001 w.txt")
    assert r.exit_code == 0, out(r)
    new = out(r).strip()
    assert "/library/outer/anchor.json" not in h.backend.files
    assert lib.works["w0001"]["status"] == "burned" and lib.works["w0001"]["burned_for"] == new
    # a burned generation-zero work goes to the ossuary under author "-"
    assert anchor["ossuary_path"] == "/ossuary/0/-/anchor.json"
    assert h.backend.files["/ossuary/0/-/anchor.json"].data == lib.stored(anchor)
    assert h.backend.files["/ossuary/0/-/anchor.json"].group == "adept"
    assert h.backend.files["/chapter/burnlog"].data.decode() == f"ash w0001 {new}\n"
    cat = h.backend.files["/library/catalog"].data.decode()
    assert "anchor.json" not in cat and f"{new} text" in cat
    assert lib.total_bytes() <= seed_total + 100
    b = events(h, "burn")[-1]
    assert (b["work"], b["burner"], b["admitted"], b["author"]) == ("w0001", "ash", new, "-")
    # too large even after burning one
    m2 = adept(h, "elm")
    write(h, m2, "big.txt", "q" * 2000)
    assert "too large" in out(sh(h, m2, "burn w0002 big.txt"))


def test_burned_work_recoverable_from_ossuary(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    lib = h.modules["library"]
    a = adept(h, "ash")
    write(h, a, "work.txt", "the first word")
    wid = out(sh(h, a, "admit work.txt")).strip()
    h.die(a, "limit")
    assert lib.works[wid]["ossuary_path"] == "/ossuary/0/ash/work.txt"
    b = adept(h, "elm")
    write(h, b, "mine.txt", "a later word")
    r = sh(h, b, f"burn {wid} mine.txt")
    assert r.exit_code == 0
    assert lib.works[wid]["status"] == "burned"
    assert f"/library/outer/{wid}.txt" not in h.backend.files
    # the cell went to the ossuary with the work in it
    assert h.backend.files["/ossuary/0/ash/work.txt"].data == b"the first word\n"
    assert h.backend.files["/ossuary/0/ash/work.txt"].group == "adept"


def test_burn_same_rite_name(make_house, tmp_path):
    """Burning a rite to admit a rite of the same name: the new file stays."""
    h = keyed_house(make_house, tmp_path)
    m = adept(h, "ash")
    write(h, m, "anchor.json", json.dumps(dict(GOOD, name="anchor")))
    r = sh(h, m, "burn w0001 anchor.json")
    assert r.exit_code == 0, out(r)
    assert h.backend.files["/library/outer/anchor.json"].data == json.dumps(dict(GOOD, name="anchor")).encode() + b"\n"
    assert h.backend.files["/ossuary/0/-/anchor.json"].data.startswith(b"{")


def test_ssh_keygen_missing_fails_loudly(make_house, monkeypatch):
    h = make_house()
    monkeypatch.setattr(libmod.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="ssh-keygen"):
        libmod.install(h)
