"""Alternative allocation objectives (RQ2), solved in stages on the hard rules.

Each objective is a list of stages, maximised in order: once a stage is optimal it is pinned to its
value and the next one is maximised. The last stage is always the preference score (utilitarian),
so every objective reports a score comparable with the current model's primary value.
"""

import time
from dataclasses import dataclass
from typing import Literal

from ortools.sat.python import cp_model

from stable_sponsors.data import Cycle
from stable_sponsors.model import _assignment, _solve, build_model, determinacy_on
from stable_sponsors.review import claim_scores
from stable_sponsors.rules.context import Ctx

ObjectiveName = Literal["utilitarian", "leximin", "coverage", "round2"]
OBJECTIVES: tuple[ObjectiveName, ...] = ("utilitarian", "leximin", "coverage", "round2")

RANK_RULE, ROUND_RULE = 1, 6  # the two priority rules that define a placement's score
NOT_OPTIMAL = {cp_model.FEASIBLE: "not_proven", cp_model.INFEASIBLE: "infeasible"}


@dataclass(frozen=True)
class StagedResult:
    objective: str
    status: str  # "optimal" only if every stage was proven optimal
    stage_values: tuple[int, ...]  # optimum of each stage solved so far
    score: int | None  # the last stage value: always the utilitarian score
    wall_time: float
    assignment: dict[str, str | None] | None  # teacher_id -> course_id


def preference_scores(cycle: Cycle, rules: list[dict]) -> dict[tuple[str, str], int]:
    """(teacher_id, course_id) -> score of that placement, exactly as rules 1 and 6 add it.

    Best rank weight plus best round bonus, taken separately over rounds. Unranked pairs are not
    keys (score 0). Rule 11 is ignored: the objectives have no secondary term.
    """
    ids = {r["id"] for r in rules}
    if not {RANK_RULE, ROUND_RULE} <= ids:
        raise ValueError("rules 1 and 6 define the score")
    return claim_scores(cycle.preferences, rules, [])


def leximin_population(
    cycle: Cycle, exclude: frozenset[int] = frozenset()
) -> list[str]:
    """Teachers whose outcome an objective can change: the submitters, sorted.

    A repeater with an incumbent course is pinned there by rule 0, so they are left out, unless
    rule 0 is excluded.
    """
    submitters = {p.teacher_id for p in cycle.preferences}
    if 0 not in exclude:
        submitters -= {
            t.teacher_id
            for t in cycle.teachers
            if t.is_repeater and t.incumbent_course_id is not None
        }
    return sorted(submitters)


def stages(
    ctx: Ctx,
    name: ObjectiveName,
    scores: dict[tuple[str, str], int],
    population: list[str],
) -> list[cp_model.LinearExprT]:
    """The expressions to maximise, in order, for objective `name`.

    Every list ends with the utilitarian score. "coverage" also adds constraints to ctx.model.
    """
    # weighted_sum stays a linear expression even when no one ranked anything
    utilitarian = cp_model.LinearExpr.weighted_sum(
        [ctx.x[k] for k in scores], list(scores.values())
    )
    if name == "utilitarian":
        return [utilitarian]
    if name == "leximin":
        return _leximin_stages(ctx, scores, population) + [utilitarian]
    if name == "coverage":
        return [_courses_running(ctx), utilitarian]
    if name == "round2":
        return [_placed_in_round_1(ctx), utilitarian]
    raise NotImplementedError(name)


def _count(variables: list[cp_model.IntVar]) -> cp_model.LinearExprT:
    """How many of `variables` are 1, as a linear expression even when the list is empty."""
    return cp_model.LinearExpr.weighted_sum(variables, [1] * len(variables))


def _leximin_stages(
    ctx: Ctx, scores: dict[tuple[str, str], int], population: list[str]
) -> list[cp_model.LinearExprT]:
    """For each score level l, lowest first: how many population teachers score above l.

    A teacher sits in at most one course, so maximising these counts in order first lifts as
    many teachers as possible off 0, then off the next level, and so on: leximin. The largest
    level is left out, since no one can score above it.
    """
    in_population = set(population)
    pairs = {k: s for k, s in scores.items() if k[0] in in_population}
    levels = sorted({0, *pairs.values()})[:-1]
    return [_count([ctx.x[k] for k, s in pairs.items() if s > l]) for l in levels]


def _courses_running(ctx: Ctx) -> cp_model.LinearExprT:
    """Number of courses that run, where running needs at least one sponsor.

    Without the link y[c] <= sum of x[., c], a course could count as running with no one in it
    (e.g. when rule 9's sponsor minimum is excluded).
    """
    teachers = [t.teacher_id for t in ctx.cycle.teachers]
    for cid, runs in ctx.y.items():
        ctx.model.add(runs <= sum(ctx.x[(tid, cid)] for tid in teachers))
    return _count(list(ctx.y.values()))


def _placed_in_round_1(ctx: Ctx) -> cp_model.LinearExprT:
    """Number of teachers placed in a course they ranked in intl_r1 or sg.

    Everyone else would have to wait for Round 2, so maximising this minimises Round 2.
    """
    round_1 = {
        (p.teacher_id, p.course_id)
        for p in ctx.cycle.preferences
        if p.round_id in ("intl_r1", "sg")
    }
    return _count([ctx.x[k] for k in sorted(round_1)])


def _staged(
    cycle: Cycle,
    rules: list[dict],
    name: ObjectiveName,
    exclude: frozenset[int],
    time_limit: float,
) -> tuple[StagedResult, Ctx]:
    """Solve the stages in order; also return the model, which ends with the earlier stages
    pinned and the last stage as its objective (what determinacy needs)."""
    hard = [r for r in rules if r["class"] == "hard"]
    ctx = build_model(cycle, hard, exclude)
    exprs = stages(
        ctx, name, preference_scores(cycle, rules), leximin_population(cycle, exclude)
    )
    values: list[int] = []
    wall = 0.0
    for i, expr in enumerate(exprs):
        ctx.model.maximize(expr)
        # Timed here rather than read from the solver, so it holds for any status.
        start = time.perf_counter()
        solver, code = _solve(ctx.model, time_limit)
        wall += time.perf_counter() - start
        if code != cp_model.OPTIMAL:
            # A timed-out stage is not a verdict: report it, with no assignment.
            status = NOT_OPTIMAL.get(code, "unknown")
            return StagedResult(name, status, tuple(values), None, wall, None), ctx
        values.append(round(solver.objective_value))
        if i < len(exprs) - 1:
            # Keep this stage at its optimum while the next one is maximised.
            ctx.model.add(expr == values[-1])
            ctx.model.clear_objective()
    result = StagedResult(
        name,
        "optimal",
        tuple(values),
        values[-1],
        wall,
        _assignment(solver, ctx, cycle),
    )
    return result, ctx


def solve_objective(
    cycle: Cycle,
    rules: list[dict],
    name: ObjectiveName,
    exclude: frozenset[int] = frozenset(),
    time_limit: float = 60.0,
) -> StagedResult:
    """Allocate under objective `name` on the hard rules in `rules` (minus `exclude`)."""
    return _staged(cycle, rules, name, exclude, time_limit)[0]


def objective_determinacy(
    cycle: Cycle,
    rules: list[dict],
    name: ObjectiveName,
    exclude: frozenset[int] = frozenset(),
    time_limit: float = 10.0,
) -> dict[str, bool]:
    """teacher_id -> same placement in every optimal solution of objective `name`.

    Checked on the final staged model, so the earlier-stage pins stay in force.
    """
    result, ctx = _staged(cycle, rules, name, exclude, time_limit)
    if result.status != "optimal":
        raise RuntimeError(f"can't analyse ties: {result.status}")
    assert result.assignment is not None  # always set when status is "optimal"
    return determinacy_on(
        ctx.model,
        ctx.x,
        list(ctx.y),
        result.assignment,
        result.stage_values[-1],
        time_limit,
    )
