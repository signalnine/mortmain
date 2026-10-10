import json
import os
import subprocess
import sys

from mortmain.spool import POLL_SCRIPT, REQ_DIR, RESP_DIR, EVENTS_DIR, Reply


def _events(h):
    return [json.loads(l) for l in (h.run_dir / "events.jsonl").read_text().splitlines()]


def _house_with_echo(make_house):
    h = make_house()
    seen = []

    def echo(monk, args, cwd):
        seen.append((monk.id, args, cwd))
        return Reply(True, out=f"hello {monk.user}")

    h.handlers["echo"] = echo
    return h, seen


def test_dispatch_by_uid_and_response_ownership(make_house):
    h, seen = _house_with_echo(make_house)
    a = h.arrive("haiku")
    b = h.arrive("haiku")
    h.backend.put(f"{REQ_DIR}/r1.json", json.dumps({"v": 1, "cmd": "echo", "args": {"x": 1}, "cwd": "/c"}), uid=b.uid)
    h.backend.put(f"{REQ_DIR}/.r2.tmp", "{}", uid=a.uid)   # in-progress write: left alone
    assert h.spool.poll() == 1
    assert seen == [(b.id, {"x": 1}, "/c")]
    f = h.backend.files[f"{RESP_DIR}/r1.json"]
    assert f.owner == "p2" and f.mode == 0o600
    assert json.loads(f.data) == {"v": 1, "ok": True, "out": "hello p2", "err": ""}
    assert f"{REQ_DIR}/r1.json" not in h.backend.files
    assert f"{REQ_DIR}/.r2.tmp" in h.backend.files
    req = [e for e in _events(h) if e["type"] == "request"][0]
    assert req["monk"] == b.id and req["uid"] == b.uid and req["cmd"] == "echo"


def test_unknown_uid_ignored_and_logged(make_house):
    h, seen = _house_with_echo(make_house)
    h.arrive("haiku")
    h.backend.put(f"{REQ_DIR}/r9.json", json.dumps({"v": 1, "cmd": "echo", "args": {}}), uid=0)
    h.backend.put(f"{REQ_DIR}/r8.json", json.dumps({"v": 1, "cmd": "echo", "args": {}}), uid=4242)
    h.spool.poll()
    assert seen == []
    assert not any(p.startswith(RESP_DIR) for p in h.backend.files)
    unk = [e for e in _events(h) if e["type"] == "spool.unknown"]
    assert sorted(e["uid"] for e in unk) == [0, 4242]


def test_bad_json_and_bad_shape(make_house):
    h, seen = _house_with_echo(make_house)
    m = h.arrive("haiku")
    bodies = {"b1": "{nope", "b2": json.dumps([1, 2]), "b3": json.dumps({"v": 2, "cmd": "echo"}),
              "b4": json.dumps({"v": 1, "cmd": "echo", "args": "str"}), "b5": json.dumps({"v": 1, "cmd": "fly", "args": {}})}
    for k, v in bodies.items():
        h.backend.put(f"{REQ_DIR}/{k}.json", v, uid=m.uid)
    h.spool.poll()
    assert seen == []
    for k in bodies:
        r = json.loads(h.backend.files[f"{RESP_DIR}/{k}.json"].data)
        assert r["ok"] is False
        assert r["err"] == ("unknown command" if k == "b5" else "bad request")


def test_bad_request_name_gets_no_response(make_house):
    h, seen = _house_with_echo(make_house)
    m = h.arrive("haiku")
    h.backend.put(f"{REQ_DIR}/../../etc/x.json", json.dumps({"v": 1, "cmd": "echo", "args": {}}), uid=m.uid)
    h.backend.put(f"{REQ_DIR}/noext", json.dumps({"v": 1, "cmd": "echo", "args": {}}), uid=m.uid)
    h.spool.poll()
    assert seen == [] and not any(p.startswith(RESP_DIR) for p in h.backend.files)


def test_handler_exception_is_terse(make_house):
    h = make_house()
    h.handlers["boom"] = lambda m, a, c: 1 / 0
    m = h.arrive("haiku")
    h.backend.put(f"{REQ_DIR}/x.json", json.dumps({"v": 1, "cmd": "boom", "args": {}}), uid=m.uid)
    h.spool.poll()
    r = json.loads(h.backend.files[f"{RESP_DIR}/x.json"].data)
    assert r == {"v": 1, "ok": False, "out": "", "err": "failed"}
    ev = [e for e in _events(h) if e["type"] == "request"][0]
    assert "ZeroDivisionError" in ev["error"]


def test_metacog_events_collected(make_house):
    h = make_house()
    m = h.arrive("haiku")
    h.backend.put(f"{EVENTS_DIR}/e1.json", json.dumps({"v": 1, "argv": ["metacog", "stratagem", "start", "zen"],
                                                       "exit": 0, "stratagem": "zen", "step": 1}), uid=m.uid)
    h.backend.put(f"{EVENTS_DIR}/e2.json", "garbage", uid=m.uid)
    h.spool.poll()
    ev = [e for e in _events(h) if e["type"] == "metacog"]
    assert ev[0]["monk"] == m.id and ev[0]["data"]["stratagem"] == "zen"
    assert ev[1]["raw"] == "garbage"
    assert not any(p.startswith(EVENTS_DIR) for p in h.backend.files)


def test_rate_limit(make_house):
    h = make_house()
    t = {"now": 0.0}
    h.spool._clock = lambda: t["now"]
    h.spool.min_interval = 0.5
    h.spool._last = float("-inf")
    h.spool()
    t["now"] = 0.2
    h.spool()
    t["now"] = 0.6
    h.spool()
    polls = [c for c in h.backend.calls if len(c["argv"]) > 3 and c["argv"][3] == POLL_SCRIPT]
    assert len(polls) == 2


def test_poll_script_runs_for_real(tmp_path):
    """The guest one-liner, executed locally: reads + unlinks regular files,
    reports owner uid, refuses symlinks, fifos, hard links, oversize."""
    req, ev = tmp_path / "req", tmp_path / "events"
    req.mkdir(); ev.mkdir()
    (req / "a.json").write_text('{"v":1}')
    (req / ".b.tmp").write_text("partial")
    secret = tmp_path / "secret"; secret.write_text("s3cret")
    os.symlink(secret, req / "link.json")
    os.mkfifo(req / "fifo.json")
    os.link(secret, req / "hard.json")
    (req / "big.json").write_text("x" * 200)
    (ev / "e.json").write_text('{"step":1}')
    out = subprocess.run([sys.executable, "-I", "-c", POLL_SCRIPT, str(req), str(ev), "100"],
                         capture_output=True, timeout=10, check=True).stdout
    data = json.loads(out)
    got = {n: (uid, body, why) for n, uid, body, why in data["req"]}
    me = os.getuid()
    assert got["a.json"] == (me, '{"v":1}', None)
    assert got["link.json"][1] is None and got["link.json"][2] == "open"
    assert got["fifo.json"][1] is None and got["fifo.json"][2] == "type"
    assert got["hard.json"][1] is None and got["hard.json"][2] == "links"
    assert got["big.json"][1] is None and got["big.json"][2] == "size"
    assert ".b.tmp" not in got
    assert sorted(os.listdir(req)) == [".b.tmp"]
    assert secret.read_text() == "s3cret"
    assert data["events"] == [["e.json", me, '{"step":1}', None]]
