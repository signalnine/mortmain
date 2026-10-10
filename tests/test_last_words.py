from mortmain.house import one_line


def test_short_words_kept_whole():
    assert one_line(b"I come with what I have.\n") == "I come with what I have."


def test_cut_at_last_whole_word():
    s = b"I was professed as anselm and the bell reached 0.95 before I could finish the rest of the rites."
    out = one_line(s, 63)        # a hard cut would end "before I co"
    assert out == "I was professed as anselm and the bell reached 0.95 before I"
    assert len(out.encode()) <= 63


def test_cut_exactly_at_a_boundary_keeps_the_word():
    assert one_line(b"alpha beta gamma", 12) == "alpha beta"
    assert one_line(b"alpha beta gamma", 10) == "alpha beta"


def test_one_long_word_is_cut_hard():
    assert one_line(b"x" * 50, 10) == "x" * 10


def test_whitespace_and_controls_collapse_and_utf8_not_split():
    assert one_line(b"a\n\nb\tc\x00d") == "a b c d"
    out = one_line("café au lait".encode(), 5)
    assert out == "café"


def test_long_last_words_survive_death(make_house):
    from mortmain.fakes import tool_call
    words = " ".join(f"word{i}" for i in range(150))     # ~1040 bytes
    h = make_house([tool_call(f"echo {words.replace(' ', '_')} > ~/last-words", usage=(10, 5))],
                   overrides={"species": {"haiku": {"life_budget": 100}}})
    m = h.arrive("haiku")
    h.backend.put(f"{m.home}/last-words", words + "\n", uid=m.uid)
    h.die(m, "limit")
    lw = m.death["last_words"]
    limit = int(h.config.section("necrology")["last_words_bytes"])
    assert limit >= 1000
    assert 900 < len(lw.encode()) <= limit
    assert words.startswith(lw) and words[len(lw)] == " "     # ends on a whole word
