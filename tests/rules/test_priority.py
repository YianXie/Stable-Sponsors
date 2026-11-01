from dataclasses import replace

import pytest

from stable_sponsors.data import Cycle
from stable_sponsors.model import determinacy, load_rules, solve_optimal
from stable_sponsors.rules.context import build_ctx
from stable_sponsors.rules.priority import unranked_fallback
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


def test_rule_11_penalises_only_unranked_non_incumbent_courses(toy_cycle: Cycle):
    ctx = build_ctx(toy_cycle)
    unranked_fallback(ctx, {})
    # 3 submitters (T1001-T1003) x 4 courses - 6 rankings = 6 unranked pairs; repeaters aren't submitters
    assert len(ctx.secondary) == 6
    assert ctx.objective == []


def test_rule_11_skips_a_submitting_repeaters_incumbent_course(toy_cycle: Cycle):
    teachers = tuple(
        replace(
            t, is_repeater=True, prior_course_id="INTL-3", incumbent_course_id="INTL-3"
        )
        if t.teacher_id == "T1001"
        else t
        for t in toy_cycle.teachers
    )
    ctx = build_ctx(replace(toy_cycle, teachers=teachers))
    unranked_fallback(ctx, {})
    assert len(ctx.secondary) == 5
