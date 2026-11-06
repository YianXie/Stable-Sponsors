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


def _coverage_cycle():  # A seats 2–4, B seats 2. T1–T4 rank A#1; T3, T4 also rank B#7
    return cycle(
        [
            ("T1", "A", 1),
            ("T2", "A", 1),
            ("T3", "A", 1),
            ("T4", "A", 1),
            ("T3", "B", 7),
            ("T4", "B", 7),
        ],
        [course("A", 2, 4), course("B", 2, 2)],
    )


def _round2_cycle():  # all 2–2. Y takes T3 (r1 #1 = 27) and T4 (r2 #1 = 17); W takes both at r1 #7 (21)
    return cycle(
        [
            ("T1", "X", 1),
            ("T2", "X", 1),
            ("T3", "Y", 1),
            ("T4", "Y", 1, "intl_r2"),
            ("T3", "W", 7),
            ("T4", "W", 7),
        ],
        [course("X"), course("Y"), course("W")],
    )


def test_leximin_raises_the_worst_off():
    r = solve_objective(lex_cycle(), RULES, "leximin")
    assert r.assignment == {"T1": "Y", "T2": "X"} and r.score == 46


def test_leximin_determinacy_sees_a_tie():
    c = cycle(
        [("T1", "X", 1), ("T1", "Y", 2), ("T2", "X", 1), ("T2", "Y", 2)],
        [course("X", 1, 1), course("Y", 1, 1)],
    )
    assert objective_determinacy(c, RULES, "leximin") == {"T1": False, "T2": False}


def test_coverage_runs_more_courses_than_utilitarian():
    assert solve_objective(_coverage_cycle(), RULES, "utilitarian").score == 108
    r = solve_objective(_coverage_cycle(), RULES, "coverage")
    assert r.stage_values == (2, 96)
    assert r.assignment == {"T1": "A", "T2": "A", "T3": "B", "T4": "B"}


def test_coverage_determinacy_keeps_the_course_count_pin():
    # without the pin, forbidding T3 from B re-optimises to 108 and T3 looks contested
    assert objective_determinacy(_coverage_cycle(), RULES, "coverage")["T3"] is True


def test_coverage_ignores_a_course_with_no_sponsors():
    c = cycle([("T1", "A", 1), ("T2", "A", 1)], [course("A"), course("Z")])
    no_capacity = [r for r in RULES if r["id"] != 9]
    assert solve_objective(c, no_capacity, "coverage").stage_values[0] == 1


def test_round2_keeps_everyone_in_round_1():
    assert solve_objective(_round2_cycle(), RULES, "utilitarian").score == 98
    r = solve_objective(_round2_cycle(), RULES, "round2")
    assert r.stage_values == (4, 96) and r.assignment["T4"] == "W"
