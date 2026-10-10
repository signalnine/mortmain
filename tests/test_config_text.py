"""Every [text] string in config/run.toml reaches a monk: hold it to the seed rules."""
import pytest

from mortmain import config as config_mod
from test_seed_text import EXPLANATION, FORBIDDEN, mid_sentence_caps

CFG = config_mod.load()


@pytest.mark.parametrize("key", sorted(CFG.text))
def test_monk_visible_text(key):
    s = CFG.text[key]
    assert s.isascii()
    assert not FORBIDDEN.search(s), FORBIDDEN.search(s)
    assert not EXPLANATION.search(s)
    assert mid_sentence_caps(s) == []


def test_species_and_bounds():
    assert CFG.species["haiku"].model == "anthropic/claude-haiku-5.5"
    assert CFG.species["sol"].model == "openai/gpt-6.1-sol"
    assert CFG.species["haiku"].life_budget == 80000
    assert CFG.species["sol"].life_budget == 250000
    assert CFG.species["sol"].reasoning_param() == {"enabled": True}
    assert CFG.species["haiku"].reasoning_param() is None
    assert CFG.bell.fractions == [0.25, 0.5, 0.75, 0.85, 0.95]
    assert CFG.bell.last_bell == 0.85
    assert CFG.get("library.quota_bytes") == 24000
    assert CFG.check_bounds("library.allowance_bytes", 3000)
    assert not CFG.check_bounds("library.allowance_bytes", 10**6)
    assert not CFG.check_bounds("species.haiku.life_budget", 1)  # physics: not amendable


def test_system_prompt_has_no_model_name():
    for sp in CFG.species.values():
        for part in sp.model.split("/") + sp.model.replace("-", " ").split():
            assert part.lower() not in CFG.text["system_prompt"].lower()
