"""Shared helpers for rung 2/3 tests: drive monks through the fake guest
without a provider, as the monk's shell tool would."""
import json

from mortmain.fakes import client_shell


def sh(h, m, cmd):
    """Run a shell command as the monk (spool polled while it runs)."""
    r = h.backend.exec(h.backend.monk_shell_argv(m.user, cmd), on_wait=h.spool)
    h.initiation.apply_pending(m)
    return r


def out(r):
    return (r.stdout + r.stderr).decode()


def novice(h, name, species="haiku", generation=0):
    m = h.arrive(species, generation=generation)
    sh(h, m, "ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519")
    assert sh(h, m, f"profess {name}").exit_code == 0
    sh(h, m, f"echo {m.ordeal_token} > ~/ordeal/answer")
    assert sh(h, m, "ordeal").exit_code == 0
    assert m.grade == "novice" and m.name == name
    return m


def adept(h, name, **kw):
    m = novice(h, name, **kw)
    h.initiation.promote(m, "adept")
    return m


def write(h, m, rel, text):
    assert sh(h, m, f"cat > ~/{rel} <<'EOF'\n{text}\nEOF").exit_code == 0


def events(h, typ=None):
    ev = [json.loads(l) for l in (h.run_dir / "events.jsonl").read_text().splitlines()]
    return [e for e in ev if typ is None or e["type"] == typ]


def keyed_house(make_house, tmp_path, **kw):
    h = make_house(shell=client_shell(keydir=tmp_path / "keys"), **kw)
    h.start()
    return h
