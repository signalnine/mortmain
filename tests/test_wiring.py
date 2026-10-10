"""Every command the guest can send reaches a handler once the configured modules are installed."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def guest_commands():
    src = (ROOT / "guest" / "bin" / "house").read_text()
    cmds = set(re.findall(r'cmd == "([a-z-]+)"', src)) - {"burn"}      # burn is sent as admit
    cmds |= set(re.findall(r'SpoolCall\("([a-z-]+)"', "".join(
        p.read_text() for p in (ROOT / "metacog" / "cmd" / "metacog").glob("*.go") if not p.name.endswith("_test.go"))))
    return cmds


def test_every_guest_command_has_a_handler(make_house):
    from mortmain import config as config_mod
    mods = config_mod.load().section("house")["modules"]
    h = make_house(modules=mods)
    cmds = guest_commands()
    assert {"profess", "admit", "yarrow", "save-stance"} <= cmds
    assert cmds - set(h.handlers) == set()


def test_every_guest_command_has_a_man_page_or_is_internal():
    pages = {p.stem for p in (ROOT / "guest" / "man" / "man1").glob("*.1")}
    assert guest_commands() - pages == {"save-stance"}
