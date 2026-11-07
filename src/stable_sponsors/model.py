import argparse
import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import yaml
from ortools.sat.python import cp_model

from stable_sponsors.data import Cycle, load_cycle
from stable_sponsors.pseudonymize.idmap import (
    DEFAULT_CONFIG,
    for_cycle,
    load_config,
    out_path,
)
from stable_sponsors.rules import hard, priority, tiebreak  # noqa: F401  (registers encoders)
from stable_sponsors.rules.context import Ctx, build_ctx
from stable_sponsors.rules.registry import ENCODERS

STATUS = {
    cp_model.OPTIMAL: "feasible",
    cp_model.FEASIBLE: "feasible",
    cp_model.INFEASIBLE: "infeasible",
    cp_model.MODEL_INVALID: "invalid",
    cp_model.UNKNOWN: "unknown",  # hit the time limit. NOT the same as infeasible
}
SOLVED = (cp_model.OPTIMAL, cp_model.FEASIBLE)  # the solver found an assignment
INACTIVE_STATUSES = ("deferred", "contradicted")

# The run report contract: main() writes runs/<when>_model_run.json, review.py reads it.
RUN_SUFFIX = "_model_run"
OPTIMAL_KEY = (
    "optimal_result"  # asdict(OptimalResult); only written when proven optimal
)
DETERMINACY_KEY = (
    "determinacy"  # teacher_id -> same placement in every optimal solution
)


@dataclass(frozen=True)
class FeasibilityResult:
    status: str
    rules_applied: tuple[int, ...]
    wall_time: float
    assignment: dict[str, str | None] | None  # teacher_id -> course_id


@dataclass(frozen=True)
class OptimalResult:
    status: str  # "optimal" only if proven
    value: int | None  # best value of objective_expr, V
    primary_value: (
        int | None
    )  # sum(objective), comparable across runs with or without rule 11
    wall_time: float
    assignment: dict[str, str | None] | None


def active_rules(rules: list[dict], classes=("hard", "priority")) -> list[dict]:
    return [
        r
        for r in rules
        if r["class"] in classes and r["status"] not in INACTIVE_STATUSES
    ]


def load_rules(path: Path, classes=("hard", "priority")) -> list[dict]:
    return active_rules(yaml.safe_load(path.read_text())["rules"], classes)


def load_hard_rules(path: Path) -> list[dict]:
    return load_rules(path, classes=("hard",))


def load_cycle_from_config(cfg: dict, cycle: int, use_lineage: bool = True) -> Cycle:
    """One cycle of the real data under private_root: derived/<cycle>/, params/ and
    key/<cycle>/course_lineage.csv.

    use_lineage=False disables the lineage fix (see data.load_cycle).
    """
    ccfg = for_cycle(cfg, cycle)
    return load_cycle(
        out_path(ccfg, "derived"),
        params_dir=out_path(cfg, "params"),
        cycle=cycle,
        lineage_path=out_path(ccfg, "key") / "course_lineage.csv",
        use_lineage=use_lineage,
    )


def objective_expr(ctx: Ctx) -> cp_model.LinearExprT:
    """The objective, with secondary terms only able to break ties.

    K exceeds any total of the secondary terms, since each teacher is in at most one course and each
    term is -1. Without secondary terms it is the plain score, so such runs keep their old values.
    """
    if not ctx.secondary:
        return sum(ctx.objective)
    return (len(ctx.cycle.teachers) + 1) * sum(ctx.objective) + sum(ctx.secondary)


def build_model(
    cycle: Cycle, rules: list[dict], exclude: frozenset[int] = frozenset()
) -> Ctx:
    ctx = build_ctx(cycle)
    for r in rules:
        if r["id"] not in exclude:
            ENCODERS[r["id"]](ctx, r["params"])
    if ctx.objective:
        ctx.model.maximize(objective_expr(ctx))
    return ctx


def _solve(
    model: cp_model.CpModel, time_limit: float
) -> tuple[cp_model.CpSolver, cp_model.CpSolverStatus]:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.random_seed = 0  # reproducible runs
    solver.parameters.num_workers = 8
    return solver, solver.solve(model)


def _assignment(
    solver: cp_model.CpSolver, ctx: Ctx, cycle: Cycle
) -> dict[str, str | None]:
    a: dict[str, str | None] = {t.teacher_id: None for t in cycle.teachers}
    for (tid, cid), var in ctx.x.items():
        if solver.value(var):
            a[tid] = cid
    return a


def check_feasibility(
    cycle, rules, exclude=frozenset(), time_limit=30.0
) -> FeasibilityResult:
    ctx = build_model(cycle, rules, exclude)
    solver, code = _solve(ctx.model, time_limit)
    status = STATUS[code]
    assignment = _assignment(solver, ctx, cycle) if status == "feasible" else None
    applied = tuple(r["id"] for r in rules if r["id"] not in exclude)
    return FeasibilityResult(status, applied, solver.wall_time, assignment)


def solve_optimal(
    cycle: Cycle, rules: list[dict], exclude=frozenset(), time_limit=60.0
) -> OptimalResult:
    ctx = build_model(cycle, rules, exclude)
    if not ctx.objective:
        raise ValueError("no priority rules applied: nothing to optimize")
    solver, code = _solve(ctx.model, time_limit)

    if code == cp_model.OPTIMAL:
        return OptimalResult(
            "optimal",
            round(solver.objective_value),
            round(solver.value(sum(ctx.objective))),
            solver.wall_time,
            _assignment(solver, ctx, cycle),
        )
    # FEASIBLE here means "found a solution but ran out of time before proving it's best".
    # Not good enough for determinacy, which relies on V being the true optimum.
    status = {cp_model.FEASIBLE: "not_proven", cp_model.INFEASIBLE: "infeasible"}.get(
        code, "unknown"
    )
    return OptimalResult(status, None, None, solver.wall_time, None)


def determinacy(cycle, rules, exclude=frozenset(), time_limit=10.0) -> dict[str, bool]:
    base = solve_optimal(cycle, rules, exclude=exclude, time_limit=time_limit)
    if base.status != "optimal":
        raise RuntimeError(f"can't analyse ties: base solve was {base.status}")
    assert base.assignment is not None  # always set when status is "optimal"

    # A teacher is determined if forbidding their placement lowers the optimum. Re-optimising is
    # far faster than proving "no solution reaches V" with the objective pinned as a constraint.
    ctx = build_model(cycle, rules, exclude=exclude)
    solver, code = _solve(ctx.model, time_limit)
    if code != cp_model.OPTIMAL or round(solver.objective_value) != base.value:
        raise RuntimeError(
            "check model can't reach the optimum: base and check models differ"
        )
    assert base.value is not None  # always set when status is "optimal"
    return determinacy_on(
        ctx.model, ctx.x, list(ctx.y), base.assignment, base.value, time_limit
    )


def determinacy_on(
    model: cp_model.CpModel,
    x: dict[tuple[str, str], cp_model.IntVar],
    course_ids: list[str],
    assignment: dict[str, str | None],
    value: int,
    time_limit: float,
) -> dict[str, bool]:
    """Which teachers' placements are the same in every optimal solution of `model`.

    `model` already has its objective set, and `value` is its optimum. For each teacher, a clone
    forbids their placement (or, if unplaced, requires one): if that clone is infeasible or its
    optimum falls below `value`, the teacher is determined.
    """
    out = {}
    for tid, cid in assignment.items():
        check = model.clone()
        xt = {
            c: check.get_bool_var_from_proto_index(x[(tid, c)].index)
            for c in course_ids
        }
        if cid is None:
            check.add(sum(xt.values()) >= 1)
        else:
            check.add(xt[cid] == 0)
        solver, code = _solve(check, time_limit)
        if code == cp_model.INFEASIBLE:
            out[tid] = True
        elif code == cp_model.OPTIMAL:
            out[tid] = round(solver.objective_value) < value  # True = determined
        else:
            raise RuntimeError(f"timed out checking {tid}")
    return out


def placement_costs(
    cycle: Cycle,
    rules: list[dict],
    pairs: list[tuple[str, str]],
    exclude=frozenset(),
    time_limit=10.0,
) -> dict[tuple[str, str], int | None]:
    """Preference score lost by forcing each (teacher_id, course_id); None if hard rules forbid it.

    Measured on the primary score, so a fallback that only uses up the secondary term costs 0.
    """
    base = solve_optimal(cycle, rules, exclude=exclude, time_limit=time_limit)
    if base.status != "optimal":
        raise RuntimeError(f"no optimum to compare with: base solve was {base.status}")
    assert base.primary_value is not None  # always set when status is "optimal"
    ctx = build_model(cycle, rules, exclude=exclude)
    out: dict[tuple[str, str], int | None] = {}
    for tid, cid in pairs:
        model = ctx.model.clone()
        model.add(model.get_bool_var_from_proto_index(ctx.x[(tid, cid)].index) == 1)
        solver, code = _solve(model, time_limit)
        if code == cp_model.INFEASIBLE:
            out[(tid, cid)] = None
        elif code == cp_model.OPTIMAL:
            out[(tid, cid)] = base.primary_value - round(
                solver.value(sum(ctx.objective))
            )
        else:
            raise RuntimeError(f"timed out checking {tid}")
    return out


def min_fallbacks(
    cycle: Cycle, rules: list[dict], exclude=frozenset(), time_limit=60.0
) -> int | None:
    """Fewest placements into unranked courses the hard rules allow, ignoring preference score.

    Needs rule 11 among ``rules``. Each newly known gender can only keep or raise this. None if the
    hard rules can't be met at all.
    """
    ctx = build_model(cycle, rules, exclude=exclude)
    ctx.model.clear_objective()
    ctx.model.maximize(sum(ctx.secondary))
    solver, code = _solve(ctx.model, time_limit)
    if code == cp_model.INFEASIBLE:
        return None
    if code != cp_model.OPTIMAL:
        raise RuntimeError("timed out finding the fewest fallbacks")
    return -round(solver.objective_value)


def diagnose(cycle, rules) -> dict:
    """Which rules does the conflict depend on?"""
    ids = [r["id"] for r in rules]
    # Leave-one-out: dropping rule i makes the model feasible → rule i is involved.
    leave_one_out = {
        i: check_feasibility(cycle, rules, exclude=frozenset({i})).status for i in ids
    }
    # Cumulative: add rules one at a time to find the first point where it breaks.
    cumulative = []
    for k in range(1, len(ids) + 1):
        status = check_feasibility(cycle, rules, exclude=frozenset(ids[k:])).status
        cumulative.append((ids[:k], status))
        if status == "infeasible":
            break
    return {"leave_one_out": leave_one_out, "cumulative": cumulative}


# --------------------------------------------------------------------------
# CLI:  uv run python -m stable_sponsors.model --exclude 5
# --------------------------------------------------------------------------


def run_model(
    config: dict,
    cycle_no: int,
    rules_path: Path,
    exclude: Iterable[int] = (),
    time_limit: float = 60.0,
    optimize: bool = False,
    lineage: bool = True,
    log: Callable[[str], None] = print,
) -> tuple[Path, dict]:
    """Check feasibility of the hard rules for one cycle, optionally optimise, and write the report.

    Progress lines go to ``log``. Returns the written run path and the report dict.
    """
    cycle = load_cycle_from_config(config, cycle_no, use_lineage=lineage)
    if not lineage:
        log("note: lineage fix disabled: prior courses matched by code")
    gone = sum(
        t.is_repeater is True and t.incumbent_course_id is None for t in cycle.teachers
    )
    if gone:
        log(
            f"note: {gone} repeater(s) whose prior course was discontinued: no incumbency applied"
        )

    ### Check feasibility of hard rules, optionally excluding some

    all_rules = yaml.safe_load(Path(rules_path).read_text())["rules"]
    hard_rules = active_rules(all_rules, classes=("hard",))
    all_ids = {r["id"] for r in all_rules}
    exclude = frozenset(exclude)
    if exclude - all_ids:
        raise SystemExit(f"--exclude {sorted(exclude - all_ids)}: no such rule id")
    inactive = exclude - {r["id"] for r in active_rules(all_rules)}
    if inactive:
        log(
            f"note: --exclude {sorted(inactive)} already off (deferred, contradicted or tie-break)"
        )
        exclude -= inactive
    names = {r["id"]: r["name"] for r in active_rules(all_rules)}

    log(
        f"cycle {cycle_no}: {len(cycle.teachers)} teachers, {len(cycle.courses)} courses"
    )
    log(
        "hard rules to check feasibility on: "
        + ", ".join(
            f"{r['id']} {r['name']}" for r in hard_rules if r["id"] not in exclude
        )
    )
    if exclude:
        log("excluded: " + ", ".join(f"{i} {names[i]}" for i in sorted(exclude)))

    feasibility_result = check_feasibility(
        cycle, hard_rules, exclude=exclude, time_limit=time_limit
    )
    log(
        f"\nSTATUS: {feasibility_result.status.upper()}  ({feasibility_result.wall_time:.2f}s)"
    )

    report: dict = {
        "when": datetime.now().isoformat(timespec="seconds"),
        "cycle": cycle_no,
        "optimize": optimize,
        "lineage": lineage,
        "rules_file": str(rules_path),
        "excluded": sorted(exclude),
        "feasibility_result": asdict(feasibility_result),
    }

    if feasibility_result.status == "feasible":
        a = feasibility_result.assignment or {}
        placed = sum(v is not None for v in a.values())
        running = len({v for v in a.values() if v is not None})
        log(
            f"  {placed}/{len(a)} teachers placed, {running}/{len(cycle.courses)} courses running"
        )
        log(
            "  (one arbitrary feasible assignment: no objective yet, so not a prediction)"
        )
    elif feasibility_result.status == "infeasible":
        active = [r for r in hard_rules if r["id"] not in exclude]
        d = diagnose(cycle, active)
        report["diagnose"] = {
            "leave_one_out": {str(k): v for k, v in d["leave_one_out"].items()},
            "cumulative": d["cumulative"],
        }
        log("\nleave-one-out (feasible = this rule is part of the conflict):")
        for i, st in d["leave_one_out"].items():
            log(f"  without {i} {names[i]:<28} {st}")
        first, st = d["cumulative"][-1]
        if st == "infeasible":
            log(
                f"\nbreaks when rule {first[-1]} ({names[first[-1]]}) is added after {first[:-1]}"
            )
        log("\nThis is a finding, not a bug: log it in docs/encoding-decisions.md.")
    else:
        log(
            "  not a verdict: try a longer --time-limit, or check for a modelling error"
        )

    ### Check optimality and determinacy of the assignment if requested

    if optimize:
        rules = active_rules(all_rules)
        opt = solve_optimal(cycle, rules, exclude=exclude, time_limit=time_limit)
        log(
            f"OPTIMAL: {opt.status}  value={opt.value}  primary={opt.primary_value}  ({opt.wall_time:.2f}s)"
        )
        if opt.status == "optimal":
            det = determinacy(cycle, rules, exclude=exclude, time_limit=time_limit)

            submitters = {p.teacher_id for p in cycle.preferences}
            determined = [t for t, d in det.items() if d]
            contested_sub = [t for t, d in det.items() if not d and t in submitters]
            contested_non = [t for t, d in det.items() if not d and t not in submitters]

            log(f"  determined:               {len(determined)}")
            log(f"  contested, submitted:     {len(contested_sub)}   <- the RQ1 number")
            log(
                f"  contested, no submission: {len(contested_non)}   (score 0 anywhere; not evidence of discretion)"
            )

            report[OPTIMAL_KEY] = asdict(opt)
            report[DETERMINACY_KEY] = det
            report["contested_submitters"] = contested_sub
            report["contested_non_submitters"] = contested_non

    ### Write report to disk

    runs = out_path(config, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{report['when'].replace(':', '')}{RUN_SUFFIX}.json"
    text = json.dumps(report, indent=2)
    path.write_text(text)
    log(f"\nwrote {path}")
    return path, json.loads(text)  # as written: tuples come back as lists


def main(argv: list[str] | None = None) -> None:
    """Run the model for a given cycle, check feasibility of hard rules, and optionally optimize."""

    ### Parse command line arguments

    ap = argparse.ArgumentParser(
        description="Check whether the hard rules are feasible and run the optimal assignment for the given cycle.  Writes a JSON report to runs/."
    )
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--rules", default="config/rules-2027.yaml", type=Path)
    ap.add_argument("--cycle", default=2027, type=int)
    ap.add_argument(
        "--exclude", nargs="*", type=int, default=[], help="rule ids to skip, e.g. 10"
    )
    ap.add_argument("--time-limit", default=60.0, type=float)
    ap.add_argument("--optimize", action="store_true")
    ap.add_argument(
        "--no-lineage",
        dest="lineage",
        action="store_false",
        help="disable the lineage fix: match repeaters' prior course by code (pre-fix behaviour)",
    )
    args = ap.parse_args(argv)

    run_model(
        load_config(args.config),
        args.cycle,
        args.rules,
        exclude=args.exclude,
        time_limit=args.time_limit,
        optimize=args.optimize,
        lineage=args.lineage,
        log=print,
    )


if __name__ == "__main__":
    main()
