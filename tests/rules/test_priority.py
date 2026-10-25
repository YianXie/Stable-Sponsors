import pytest

from stable_sponsors.data import Cycle
from stable_sponsors.model import determinacy, load_rules, solve_optimal
from tests.conftest import RULES_PATH


def test_solve_optimal_prefers_first_choice(toy_cycle):
    rules = load_rules(RULES_PATH)  # hard + rank_preference
    r = solve_optimal(toy_cycle, rules)
    assert r.status == "optimal"
    assert r.assignment is not None
    # T1001 ranked INTL-1 first; pick a toy setup where that seat is free
    assert r.assignment["T1001"] == "INTL-1"


@pytest.mark.skip(reason="Not implemented yet")
def test_unranked_placement_scores_zero(toy_cycle: Cycle): ...


def test_rank_beyond_weights_raises(toy_cycle: Cycle):
    rules = load_rules(RULES_PATH)
    rules = [r if r["id"] != 1 else {"id": 1, "params": {"weights": ()}} for r in rules]
    with pytest.raises(ValueError, match="ranked .* at .*; only .* weights"):
        solve_optimal(toy_cycle, rules)


def test_determinacy_flags_a_planted_tie(toy_cycle: Cycle):
    # a tie → not determined
    rules = load_rules(RULES_PATH)
    r = determinacy(toy_cycle, rules)
    # T1002 and T1003 are tied for INTL-2, so neither placement is determined
    assert not r["T1002"]
    assert not r["T1003"]


def test_determinacy_flags_a_forced_placement(toy_cycle):
    # a repeater → determined
    rules = load_rules(RULES_PATH)
    r = determinacy(toy_cycle, rules)
    assert r["T1000"]  # T1000 is a repeater, so their placement is determined
    assert r["T1004"]  # T1004 is a repeater, so their placement is determined
