"""--max-cost counts every billed call of the lineage, not only the monks' own turns."""
from mortmain.fakes import tool_call


def test_total_cost_includes_side_calls(make_house):
    h = make_house([{**tool_call("ls", usage=(10, 5)), "_cost": 0.25}])
    m = h.arrive("haiku")
    m.step()
    assert h.total_cost() == 0.25
    h.state_extras["catechism"] = {"billed": {"cost": 1.5}}
    h.state_extras["tripwire"] = {"billed": {"cost": 0.125}}
    h.state_extras["vessel"] = {"billed": {"cost": 0.0625}, "slots": []}
    h.state_extras["other"] = {"no": "billing"}
    assert h.total_cost() == 0.25 + 1.5 + 0.125 + 0.0625
