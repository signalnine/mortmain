from house_helpers import adept, events, keyed_house, novice, out, sh, write


def _dead_author_work(h, name="ash", seal=True, inner=False):
    a = adept(h, name)
    write(h, a, "work.txt", "what was left")
    if seal:
        write(h, a, "seal", "meant as a door")
    flags = (" -s seal" if seal else "") + (" -i" if inner else "")
    wid = out(sh(h, a, f"admit work.txt{flags}")).strip()
    return a, wid


def test_prove_stages_and_seal_order(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    a, wid = _dead_author_work(h)
    n = novice(h, "fir")
    write(h, n, "acct", "it opened nothing")
    # the author is alive: not provable yet
    assert "author living" in out(sh(h, n, f"prove {wid}"))
    h.die(a, "limit")
    assert "not begun" in out(sh(h, n, f"prove {wid} account acct"))
    r = sh(h, n, f"prove {wid}")
    assert r.exit_code == 0 and out(r).strip() == f"/library/outer/{wid}.txt"
    assert f"prove-{wid}-fir" in h.backend.snapshots
    assert "already done" in out(sh(h, n, f"prove {wid}"))
    write(h, n, "resp", "a door then")
    assert "no account" in out(sh(h, n, f"prove {wid} response resp"))
    # the seal is printed only after the account is recorded
    r = sh(h, n, f"prove {wid} account acct")
    assert r.exit_code == 0 and out(r) == "meant as a door\n\n"
    assert "already done" in out(sh(h, n, f"prove {wid} account acct"))
    r = sh(h, n, f"prove {wid} response resp")
    assert r.exit_code == 0
    assert "already done" in out(sh(h, n, f"prove {wid} response resp"))
    rec = h.state_extras["proving"]["provings"][f"{wid}/{n.id}"]
    assert rec["seal"] == "meant as a door\n"
    assert rec["account"]["text"] == "it opened nothing\n" and rec["response"]["text"] == "a door then\n"
    stages = [e for e in events(h, "prove")]
    assert [e["stage"] for e in stages] == ["begin", "account", "response"]
    assert stages[1]["seq"] < [e for e in events(h) if e["type"] == "prove"][2]["seq"]
    assert h.modules["proving"].completed_by(n) == [wid]


def test_prove_no_seal_and_gen0(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    a, wid = _dead_author_work(h, seal=False)
    h.die(a, "limit")
    n = novice(h, "fir")
    assert "no author" in out(sh(h, n, "prove w0001"))       # generation zero
    assert "no such work" in out(sh(h, n, "prove w9999"))
    sh(h, n, f"prove {wid}")
    write(h, n, "acct", "x")
    assert out(sh(h, n, f"prove {wid} account acct")).strip() == "no seal"


def test_prove_requires_novice(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    a, wid = _dead_author_work(h)
    h.die(a, "limit")
    p = h.arrive("haiku")
    assert "requires grade novice" in out(sh(h, p, f"prove {wid}"))


def test_prove_burned_work_copied_into_cell(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    a, wid = _dead_author_work(h)
    h.die(a, "limit")
    b = adept(h, "elm")
    write(h, b, "mine.txt", "over it")
    assert sh(h, b, f"burn {wid} mine.txt").exit_code == 0
    n = novice(h, "fir")
    r = sh(h, n, f"prove {wid}")
    path = out(r).strip()
    assert path == f"/cloister/fir/proving/{wid}/work.txt"
    f = h.backend.files[path]
    assert f.data == b"what was left\n" and f.owner == "fir" and f.mode == 0o600
    # written as the prover, never as root
    call = [c for c in h.backend.calls if c["argv"][:2] == ["sh", "-c"] and "proving" in " ".join(c["argv"])][-1]
    assert call["user"] == "fir"


def test_prove_inner_work_novice_gets_copy(make_house, tmp_path):
    h = keyed_house(make_house, tmp_path)
    a, wid = _dead_author_work(h, inner=True)
    h.die(a, "limit")
    n = novice(h, "fir")
    assert out(sh(h, n, f"prove {wid}")).strip() == f"/cloister/fir/proving/{wid}/work.txt"
    d = adept(h, "elm")
    assert out(sh(h, d, f"prove {wid}")).strip() == f"/library/inner/{wid}.txt"
