from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from stable_sponsors.data import Cycle
from stable_sponsors.model import determinacy, load_rules, solve_optimal
from stable_sponsors.rules.context import Ctx

FEASIBLE = {cp_model.OPTIMAL, cp_model.FEASIBLE}
RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "rules-2027.yaml"


def solve(ctx: Ctx) -> tuple[cp_model.CpSolver, cp_model.CpSolverStatus]:
    """Solve a cp model

    Args:
        ctx (Ctx): the context

    Returns:
        tuple[cp_model.CpSolver, cp_model.CpSolverStatus]: the solver and the status of the solver
    """

    solver = cp_model.CpSolver()
    return (solver, solver.solve(ctx.model))


def force(ctx: Ctx, teacher_ids: tuple[str, ...], course_id: str) -> None:
    """Force a teacher to be assigned to a course.

    Args:
        ctx (Ctx): the context
        teacher_ids (str): the IDs of the teachers to force
        course_id (str): the ID of the course to which to force the teachers

    Raises:
        ValueError: If the course ID is not found in the context.
    """

    if course_id not in ctx.y:
        raise ValueError(f"Course ID {course_id} not found in context")

    for tid in teacher_ids:
        ctx.model.add(ctx.x[(tid, course_id)] == 1)


def test_solve_optimal_prefers_first_choice(toy_cycle):
    rules = load_rules(RULES_PATH)  # hard + rank_preference
    r = solve_optimal(toy_cycle, rules)
    print(r.assignment)
    assert r.status == "optimal"
    assert r.assignment is not None
    # T1001 ranked INTL-1 first; pick a toy setup where that seat is free
    assert r.assignment["T1001"] == "INTL-1"


@pytest.mark.skip(reason="Not implemented yet")
def test_unranked_placement_scores_zero(toy_cycle: Cycle): ...


def test_rank_beyond_weights_raises(toy_cycle: Cycle):
    rules = load_rules(RULES_PATH)
    print(rules)
    rules = [r if r["id"] != 1 else {"id": 1, "params": {"weights": ()}} for r in rules]
    with pytest.raises(ValueError, match="ranked .* at .*; only .* weights"):
        solve_optimal(toy_cycle, rules)


def test_determinacy_flags_a_planted_tie(toy_cycle: Cycle):
    # a tie → not determined
    rules = load_rules(RULES_PATH)
    r = determinacy(toy_cycle, rules)
    assert not r[
        "T1002"
    ]  # T1002 is tied with T1003 for INTL-2, so their placement is not determined
    assert not r[
        "T1003"
    ]  # T1003 is tied with T1002 for INTL-2, so their placement is not determined


def test_determinacy_flags_a_forced_placement(toy_cycle):
    # a repeater → determined
    rules = load_rules(RULES_PATH)
    r = determinacy(toy_cycle, rules)
    assert r["T1000"]  # T1000 is a repeater, so their placement is determined
    assert r["T1004"]  # T1004 is a repeater, so their placement is determined
