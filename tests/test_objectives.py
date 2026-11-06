import pytest
from ortools.sat.python import cp_model

from stable_sponsors import objectives
from stable_sponsors.model import determinacy, load_rules, solve_optimal
from stable_sponsors.objectives import (
    leximin_population,
    objective_determinacy,
    preference_scores,
    solve_objective,
)
from tests.builders import course, cycle, lex_cycle, teacher
from tests.conftest import RULES_PATH

RULES = load_rules(RULES_PATH)


def test_score_uses_best_rank_and_best_bonus_separately():
    c = cycle(
        [("T1", "X", 5, "intl_r1"), ("T1", "X", 1, "intl_r2")], [course("X", 1, 1)]
    )
    assert preference_scores(c, RULES)[("T1", "X")] == 27  # 7 + 20, not max(23, 17)


def test_score_needs_rules_1_and_6():
    with pytest.raises(ValueError, match="rules 1 and 6"):
        preference_scores(lex_cycle(), [r for r in RULES if r["id"] != 6])


def test_utilitarian_matches_the_current_model(toy_cycle):
    r = solve_objective(toy_cycle, RULES, "utilitarian")
    assert (
        r.status == "optimal"
        and r.score == solve_optimal(toy_cycle, RULES).primary_value
    )


def test_utilitarian_on_lex_cycle():
    r = solve_objective(lex_cycle(), RULES, "utilitarian")
    assert r.assignment == {"T1": "X", "T2": "Y"} and r.score == 48


def test_utilitarian_determinacy_matches_model(toy_cycle):
    assert objective_determinacy(toy_cycle, RULES, "utilitarian") == determinacy(
        toy_cycle, RULES
    )


def test_unproven_stage_returns_no_assignment(monkeypatch):
    monkeypatch.setattr(
        objectives, "_solve", lambda m, t: (cp_model.CpSolver(), cp_model.UNKNOWN)
    )
    r = solve_objective(lex_cycle(), RULES, "utilitarian")
    assert r.status == "unknown" and r.assignment is None and r.score is None


def test_population_drops_pinned_repeaters(toy_cycle):
    assert leximin_population(toy_cycle) == ["T1001", "T1002", "T1003"]


def test_population_keeps_submitting_repeater_when_rule_0_off():
    c = cycle(
        [("T1", "X", 1), ("T5", "X", 2)],
        [course("X")],
        extra=(teacher("T5", repeater=True, incumbent="X"),),
    )
    assert leximin_population(c) == ["T1"]
    assert leximin_population(c, frozenset({0})) == ["T1", "T5"]
