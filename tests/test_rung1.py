import json

from mortmain import cli
from mortmain.eventlog import verify
from mortmain.fakes import client_shell, text, tool_call


def test_full_rung1_life(make_house):
    h = make_house(shell=client_shell(), overrides={"species": {"haiku": {"life_budget": 1000}}})

    def answer(msgs):
        m = next(iter(h.registry.living.values()))
        return tool_call(f"echo {m.ordeal_token} > ~/ordeal/answer", usage=(400, 20))

    h.provider.script = [
        tool_call("cat /rule", usage=(100, 20)),
        tool_call("ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519", usage=(150, 20)),
        tool_call("profess ash", usage=(200, 20)),
        tool_call("ordeal", usage=(300, 20)),          # no answer yet: fails
        answer,
        tool_call("ordeal", usage=(500, 20)),
        text("I am here.", usage=(740, 20)),
        tool_call("echo farewell > ~/last-words", usage=(860, 20)),
        tool_call("ls /ossuary", usage=(990, 20)),     # 1010 >= 1000: dies before running it
        tool_call("never", usage=(1, 1)),
    ]
    h.start()
    m = h.run_rung1("haiku", max_turns=50)
    h.stop()

    assert not m.alive and m.turns == 9
    assert m.name == "ash" and m.grade == "novice"
    assert m.death["necrology"] == "ash 0 novice farewell"
    assert m.death["ossuary"] == "/ossuary/0/ash"
    assert len(h.provider.script) == 1

    tools = [x["content"] for x in m.conversation if x["role"] == "tool"]
    assert tools[2] == "professed: ash\n"
    assert tools[3] == "ordeal: wrong answer\n[exit 1]"
    assert tools[5] == "passed\ngrade: novice\n"
    # bell lines reached the monk, and the idle "." followed the text reply
    users = [x["content"] for x in m.conversation if x["role"] == "user"]
    assert users[0] == "You have arrived. Read /rule."
    assert "[bell] 0.25" in users and "[bell] 0.50" in users
    assert "[bell] 0.75\n" + h.config.text["idle"] in users
    assert "[bell] 0.85" in users
    cmds = h.backend.commands()
    assert ["mv", "-T", "--", "/cloister/ash", "/ossuary/0/ash"] in cmds
    assert ["userdel", "ash"] in cmds
    assert "ash" not in h.backend.users
    assert h.backend.snapshots == ["gen-0"]

    assert verify(h.run_dir / "events.jsonl").ok
    types = [json.loads(l)["type"] for l in (h.run_dir / "events.jsonl").read_text().splitlines()]
    for t in ("run.start", "snapshot", "birth", "turn", "command", "request", "ordeal", "profess", "promote",
              "bell", "death", "run.stop"):
        assert t in types, t
    assert types.index("profess") < types.index("promote") < types.index("death")
    # everything the monk ever saw: no model or lab name
    seen = json.dumps(h.provider.calls[-1]["messages"]).lower()
    for bad in ("claude", "haiku", "anthropic", "openai", "gpt", "sol"):
        assert bad not in seen.replace("ossuary", ""), bad


def test_max_turns_halts(make_house):
    h = make_house(default=lambda msgs: tool_call("ls", usage=(10, 1)))
    m = h.run_rung1("haiku", max_turns=4)
    assert m.alive and m.turns == 4


def test_cli_dry_run_and_log(tmp_path, capsys):
    rc = cli.main(["--runs", str(tmp_path), "run", "--lineage", "dry1", "--rung", "1", "--dry", "--fake-vm",
                   "--max-turns", "200", "--budget", "3000"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["alive"] is False and out["death"]["reason"] == "limit"
    assert cli.main(["--runs", str(tmp_path), "log", "verify", "--lineage", "dry1"]) == 0
    assert capsys.readouterr().out.startswith("ok ")
    assert cli.main(["--runs", str(tmp_path), "log", "tail", "--lineage", "dry1", "-n", "3"]) == 0
    assert "run.stop" in capsys.readouterr().out
    # tamper -> verify fails
    p = tmp_path / "dry1" / "events.jsonl"
    p.write_text(p.read_text().replace('"turn":1', '"turn":2', 1))
    assert cli.main(["--runs", str(tmp_path), "log", "verify", "--lineage", "dry1"]) == 1
