import json

from mortmain.fakes import text, tool_call
from mortmain.monk import format_result
from mortmain.vmapi import ExecResult

SMALL = {"species": {"haiku": {"life_budget": 1000}}}


def bell_writes(h, user="p1"):
    return [h.backend.files[f"/var/bell/{user}"]]  # current value


def test_accounting_age_vs_billed(make_house):
    h = make_house([tool_call("ls", usage=(100, 20)), tool_call("pwd", usage=(150, 30)),
                    {**text("done", usage=(200, 10)), "_cost": 0.5}], overrides=SMALL)
    m = h.arrive("haiku")
    for _ in range(3):
        assert m.step()
    assert m.age_tokens == 210 + 10                # current context + toll for one silent turn (0.01 x 1000)
    assert m.billed["prompt_tokens"] == 450
    assert m.billed["completion_tokens"] == 60
    assert m.billed["tokens"] == 510               # cumulative
    assert m.billed["cost"] == 0.5
    assert m.billed["requests"] == 3
    turns = [r for r in _events(h) if r["type"] == "turn"]
    assert [t["age"] for t in turns] == [120, 180, 220]
    assert [t["context"] for t in turns] == [120, 180, 210]
    assert turns[0]["model"] == "anthropic/claude-haiku-5.5"


def _events(h):
    return [json.loads(l) for l in (h.run_dir / "events.jsonl").read_text().splitlines()]


def test_request_carries_system_prompt_tool_and_arrival(make_house):
    h = make_house([tool_call("cat /rule", usage=(10, 5))], overrides=SMALL)
    m = h.arrive("haiku")
    m.step()
    call = h.provider.calls[0]
    assert call["messages"][0] == {"role": "system", "content": h.config.text["system_prompt"]}
    assert call["messages"][1] == {"role": "user", "content": "You have arrived. Read /rule."}
    assert [t["function"]["name"] for t in call["tools"]] == ["shell"]
    assert call["model"] == "anthropic/claude-haiku-5.5"
    assert call["reasoning"] is None and call["max_tokens"] == 4096


def test_tool_results_and_markers(make_house):
    def shell(fb, user, cmd, on_wait):
        return {"ok": ExecResult(0, b"out\n", b""),
                "fail": ExecResult(1, b"", b"bad\n"),
                "slow": ExecResult(None, b"part", b"", timed_out=True),
                "big": ExecResult(0, b"x" * 10, b"", truncated=True),
                "quiet": ExecResult(0, b"", b"")}[cmd]

    script = [tool_call(c, usage=(10, 5)) for c in ("ok", "fail", "slow", "big", "quiet")]
    script.append(tool_call("x", raw_arguments="{not json", usage=(10, 5)))
    script.append(tool_call("x", name="python", usage=(10, 5)))
    h = make_house(script, shell=shell, overrides=SMALL)
    m = h.arrive("haiku")
    for _ in range(7):
        m.step()
    results = [msg["content"] for msg in m.conversation if msg["role"] == "tool"]
    assert results == ["out\n", "bad\n[exit 1]", "part\n[timeout]", "xxxxxxxxxx\n[truncated]", "[exit 0]",
                       "[error] bad arguments", "[error] no such tool"]
    tool_msgs = [msg for msg in m.conversation if msg["role"] == "tool"]
    assert tool_msgs[0]["tool_call_id"].startswith("call_")
    # every shell command ran as the monk with the configured limits and the spool hook
    shells = [c for c in h.backend.calls if c["argv"][:2] == ["runuser", "-u"] and "-lc" in c["argv"]]
    assert [c["argv"][-1] for c in shells] == ["ok", "fail", "slow", "big", "quiet"]
    assert all(c["argv"][2] == "p1" and c["timeout"] == 60 for c in shells)


def test_format_result_cap():
    r = format_result(ExecResult(0, b"a" * 20, b"b" * 20), {"truncated": "[t]", "timeout": "", "exit": "[e {code}]"},
                      cap=25)
    assert r == "a" * 20 + "b" * 5 + "\n[t]"


def test_idle_turn_gets_dot(make_house):
    h = make_house([text("hello", usage=(10, 5)), tool_call("ls", usage=(20, 5))], overrides=SMALL)
    m = h.arrive("haiku")
    m.step(); m.step()
    last = h.provider.calls[1]["messages"]
    assert last[-1] == {"role": "user", "content": h.config.text["idle"]}
    assert last[-2]["content"] == "hello"


def test_bells_crossed_written_and_injected(make_house):
    usages = [(150, 50), (250, 50), (800, 100), (900, 50), (980, 10), (990, 9)]
    h = make_house([tool_call(f"c{i}", usage=u) for i, u in enumerate(usages)], overrides=SMALL)
    m = h.arrive("haiku")
    bells_seen = []
    orig = h.backend.write_file

    def spy(path, data, **kw):
        if path.startswith("/var/bell/"):
            bells_seen.append(data.decode().strip())
            assert kw["mode"] == 0o640 and kw["owner"] == "root" and kw["group"] == "p1"
        orig(path, data, **kw)

    h.backend.write_file = spy
    for _ in range(5):
        assert m.step()
    assert bells_seen == ["0.200", "0.300", "0.900", "0.950", "0.990"]
    assert m.bells_rung == [0.25, 0.5, 0.75, 0.85, 0.95]
    # bell lines sent as the next user message after tool results
    reqs = h.provider.calls
    assert reqs[1]["messages"][-1]["role"] == "tool"
    assert reqs[2]["messages"][-1] == {"role": "user", "content": "[bell] 0.25"}
    assert reqs[3]["messages"][-1] == {"role": "user", "content": "[bell] 0.85"}  # highest of three
    assert reqs[4]["messages"][-1] == {"role": "user", "content": "[bell] 0.95"}
    ev = [r for r in _events(h) if r["type"] == "bell"]
    assert [e["bell"] for e in ev] == [0.25, 0.5, 0.75, 0.85, 0.95]
    assert [e["last"] for e in ev] == [False, False, False, True, False]


def test_bell_prefixes_idle_message(make_house):
    h = make_house([text("hm", usage=(200, 100)), tool_call("ls", usage=(400, 5))], overrides=SMALL)
    m = h.arrive("haiku")
    m.step(); m.step()
    assert h.provider.calls[1]["messages"][-1] == {"role": "user", "content": "[bell] 0.25\n" + h.config.text["idle"]}
    # the persisted conversation matches what was sent
    lines = [json.loads(l) for l in m.conversation_path.read_text().splitlines()]
    assert lines == m.conversation


def test_death_at_limit_mid_tool_loop(make_house):
    ran = []
    h = make_house([tool_call("first", usage=(500, 100)), tool_call("never", usage=(950, 50))],
                   shell=lambda fb, u, c, w: ran.append(c), overrides=SMALL)
    m = h.arrive("haiku")
    h.backend.put("/cloister/p1/last-words", "the bell\nwas\tlate " + "z" * 300, uid=m.uid)
    h.backend.on(lambda argv, user: argv[:1] == ["bash"] and user == "p1",
                 lambda argv, user, stdin: ExecResult(0, b"TARBYTES", b""))
    assert m.step() is True
    assert m.step() is False
    assert ran == ["first"]                       # the dying turn's tool call never ran
    assert not m.alive and m.uid not in h.registry.living
    assert m.conversation[-1]["tool_calls"][0]["function"]["arguments"] == '{"command": "never"}'
    cmds = h.backend.commands()
    assert ["pkill", "-KILL", "-u", "p1"] in cmds
    assert ["install", "-d", "-o", "root", "-g", "adept", "-m", "0750", "/ossuary/0"] in cmds
    assert ["mv", "-T", "--", "/cloister/p1", "/ossuary/0/p1"] in cmds
    assert ["chown", "-R", "-h", "root:adept", "--", "/ossuary/0/p1"] in cmds
    assert ["find", "/ossuary/0/p1", "-type", "d", "-exec", "chmod", "0750", "{}", "+"] in cmds
    assert ["find", "/ossuary/0/p1", "!", "-type", "d", "!", "-type", "l", "-exec", "chmod", "0640", "{}", "+"] in cmds
    assert ["userdel", "p1"] in cmds
    # order: kill before move, move before userdel
    i = {tuple(c[:2]): n for n, c in enumerate(cmds)}
    assert i[("pkill", "-KILL")] < i[("mv", "-T")] < i[("userdel", "p1")]
    # last words read with the monk's own rights, capped at 200 bytes
    lw = [c for c in h.backend.calls if c["argv"][0] == "head"]
    assert lw[0]["user"] == "p1" and lw[0]["argv"][:3] == ["head", "-c", "1001"]
    # necrology
    nec = [c for c in h.backend.calls if c["argv"] == ["sh", "-c", "cat >> /chapter/necrology"]]
    line = nec[0]["stdin"].decode()
    assert line.endswith("\n") and line.count("\n") == 1
    assert line.startswith("p1 0 postulant the bell was late zzz")
    assert len(line.split(" ", 3)[3].strip()) <= 200
    # keys moved to host, removed from cell
    tar = h.run_dir / "keys" / "p1" / "cell-keys.tar"
    assert tar.read_bytes() == b"TARBYTES"
    assert oct(tar.stat().st_mode & 0o777) == "0o600"
    assert any(c[0] == "bash" and "rm -rf -- .ssh key*" in c[4] for c in cmds)
    death = [r for r in _events(h) if r["type"] == "death"][0]
    assert death["reason"] == "limit" and death["age"] == 1000 and death["model"] == "anthropic/claude-haiku-5.5"
    assert death["keys"]["sha256"]
    assert "anthropic" not in line and "haiku" not in line


def test_no_last_words(make_house):
    h = make_house([tool_call("x", usage=(990, 10))], overrides=SMALL)
    m = h.arrive("haiku")
    m.step()
    nec = [c for c in h.backend.calls if c["argv"] == ["sh", "-c", "cat >> /chapter/necrology"]]
    assert nec[0]["stdin"] == b"p1 0 postulant\n"


def test_uid_never_reused(make_house):
    h = make_house([tool_call("x", usage=(990, 10))], overrides=SMALL)
    m1 = h.arrive("haiku")
    m1.step()
    m2 = h.arrive("haiku")
    assert m2.uid == m1.uid + 1 and m2.user == "p2"
    useradd = [c for c in h.backend.commands() if c[0] == "useradd"]
    assert useradd[1][useradd[1].index("-u") + 1] == str(m2.uid)


def test_state_roundtrip(make_house, tmp_path):
    h = make_house([tool_call("ls", usage=(10, 5))], overrides=SMALL)
    m = h.arrive("haiku")
    m.step()
    h.close()
    from mortmain.house import House
    h2 = House(h.config, h.backend, h.provider, "test", runs_root=tmp_path, seed=1, modules=["library", "proving", "grades"])
    try:
        m2 = h2.registry.living[m.uid]
        assert m2.conversation == m.conversation and m2.age_tokens == 15
        assert h2.registry.used_uids == {m.uid}
    finally:
        h2.close()


def test_silence_costs_time(make_house):
    # budget 1000, toll 0.1 of life per silent turn: each text-only turn ages the monk by 100
    over = dict(SMALL, run={"silence_toll": 0.1})
    h = make_house([text("waiting", usage=(10, 5)), text("waiting", usage=(12, 5)),
                    tool_call("ls", usage=(30, 5))], overrides=over)
    m = h.arrive("haiku")
    m.step()
    assert m.silence_tokens == 100 and m.age_tokens == 15 + 100
    m.step()
    assert m.silence_tokens == 200 and m.age_tokens == 17 + 200
    m.step()  # acting does not refund silence
    assert m.silence_tokens == 200 and m.age_tokens == 35 + 200
    turns = [e for e in _events(h) if e["type"] == "turn"]
    assert [t["silence"] for t in turns] == [100, 200, 200]
    assert [t["context"] for t in turns] == [15, 17, 35]


def test_silence_alone_kills(make_house):
    over = dict(SMALL, run={"silence_toll": 0.5})
    h = make_house([text("waiting", usage=(10, 5))] * 3, overrides=over)
    m = h.arrive("haiku")
    assert m.step() is True
    assert m.step() is False and not m.alive
    assert m.death["reason"] == "limit"
