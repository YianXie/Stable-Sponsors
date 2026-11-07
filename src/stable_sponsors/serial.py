"""Random serial dictatorship (RQ2 baseline), on the hard rules.

Teachers pick in a given order. Each takes their best-scoring ranked course that still leaves the
hard rules satisfiable for everyone, or else stays unplaced if that is satisfiable. Averaging over
random orders gives the baseline the objectives are compared with.
"""

import random

from ortools.sat.python import cp_model

from stable_sponsors.data import Cycle
from stable_sponsors.model import _assignment, _solve, build_model
from stable_sponsors.objectives import preference_scores
from stable_sponsors.rules.context import Ctx

SOLVED = (cp_model.OPTIMAL, cp_model.FEASIBLE)


def submitters(cycle: Cycle) -> list[str]:
    """Sorted IDs of the teachers with at least one preference: the ones who pick."""
    return sorted({p.teacher_id for p in cycle.preferences})


def random_orders(teacher_ids: list[str], n: int, seed: int = 0) -> list[list[str]]:
    """n shuffles of the sorted IDs from one seeded RNG, so the same call gives the same orders."""
    rng = random.Random(seed)
    orders = []
    for _ in range(n):
        order = sorted(teacher_ids)
        rng.shuffle(order)
        orders.append(order)
    return orders


def _options(
    ctx: Ctx, scores: dict[tuple[str, str], int], tid: str
) -> list[cp_model.BoundedLinearExpression]:
    """What teacher `tid` would choose, best first: each ranked course, then unplaced.

    Courses go by score, highest first, with ties broken by course ID.
    """
    ranked = sorted(
        (cid for t, cid in scores if t == tid), key=lambda c: (-scores[(tid, c)], c)
    )
    courses = [c.course_id for c in ctx.cycle.courses]
    unplaced = sum(ctx.x[(tid, c)] for c in courses) == 0
    return [ctx.x[(tid, c)] == 1 for c in ranked] + [unplaced]


def _is_feasible(model: cp_model.CpModel, tid: str, time_limit: float) -> bool:
    """Whether `model` can be satisfied. A timeout is not an answer, so it raises."""
    _, code = _solve(model, time_limit)
    if code in SOLVED:
        return True
    if code == cp_model.INFEASIBLE:
        return False
    raise RuntimeError(f"timed out checking {tid}")


def serial_dictatorship(
    cycle: Cycle,
    rules: list[dict],
    order: list[str],
    exclude: frozenset[int] = frozenset(),
    time_limit: float = 10.0,
) -> dict[str, str | None]:
    """teacher_id -> course_id (or None) when the submitters pick in `order`.

    Uses the hard rules in `rules` (minus `exclude`); rules 1 and 6 only give the scores.
    """
    if sorted(order) != submitters(cycle):
        raise ValueError("order must be a permutation of the submitters")
    ctx = build_model(cycle, [r for r in rules if r["class"] == "hard"], exclude)
    scores = preference_scores(cycle, rules)
    for tid in order:
        for option in _options(ctx, scores, tid):
            # Try the option on a copy, so a rejected one leaves no trace.
            trial = ctx.model.clone()
            trial.add(option)
            if _is_feasible(trial, tid, time_limit):
                ctx.model.add(option)  # t keeps this choice for everyone after them
                break
        # No feasible option (rule 0 or 4 forces an unranked seat): t stays free.
    # One last solve places the non-submitters and free teachers, all at score 0.
    solver, code = _solve(ctx.model, time_limit)
    if code not in SOLVED:
        raise RuntimeError("no allocation satisfies the hard rules")
    return _assignment(solver, ctx, cycle)
