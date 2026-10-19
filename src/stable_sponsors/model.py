import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import yaml
from ortools.sat.python import cp_model

from stable_sponsors.data import Cycle, load_cycle
from stable_sponsors.pseudonymize.idmap import load_config, out_path
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


@dataclass(frozen=True)
class FeasibilityResult:
    status: str
    rules_applied: tuple[int, ...]
    wall_time: float
    assignment: dict[str, str | None] | None  # teacher_id -> course_id


@dataclass(frozen=True)
class OptimalResult:
    status: str  # "optimal" only if proven
    value: int | None  # best total score V
    wall_time: float
    assignment: dict[str, str | None] | None


def load_rules(path: Path, classes=("hard", "priority")) -> list[dict]:
    rules = yaml.safe_load(path.read_text())["rules"]
    return [r for r in rules if r["class"] in classes and r["status"] != "deferred"]


def load_hard_rules(path: Path) -> list[dict]:
    rules = yaml.safe_load(path.read_text())["rules"]
    return [r for r in rules if r["class"] == "hard" and r["status"] != "deferred"]


def build_model(
    cycle: Cycle, rules: list[dict], exclude: frozenset[int] = frozenset()
) -> Ctx:
    ctx = build_ctx(cycle)
    for r in rules:
        if r["id"] not in exclude:
            ENCODERS[r["id"]](ctx, r["params"])
    if ctx.objective:
        ctx.model.maximize(sum(ctx.objective))
    return ctx


def _solve(
    ctx: Ctx, time_limit: float
) -> tuple[cp_model.CpSolver, cp_model.CpSolverStatus]:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.random_seed = 0
    solver.parameters.num_workers = 8
    return solver, solver.solve(ctx.model)


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
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.random_seed = 0  # reproducible runs
    solver.parameters.num_workers = 8
    status = STATUS[solver.solve(ctx.model)]

    assignment: dict[str, str | None] | None = None
    if status == "feasible":
        assignment = {t.teacher_id: None for t in cycle.teachers}
        for (tid, cid), var in ctx.x.items():
            if solver.value(var):
                assignment[tid] = cid
    applied = tuple(r["id"] for r in rules if r["id"] not in exclude)
    return FeasibilityResult(status, applied, solver.wall_time, assignment)


def solve_optimal(
    cycle: Cycle, rules: list[dict], exclude=frozenset(), time_limit=60.0
) -> OptimalResult:
    ctx = build_model(cycle, rules, exclude)
    if not ctx.objective:
        raise ValueError("no priority rules applied: nothing to optimize")
    ctx.model.maximize(sum(ctx.objective))
    solver, code = _solve(ctx, time_limit)

    if code == cp_model.OPTIMAL:
        return OptimalResult(
            "optimal",
            round(solver.objective_value),
            solver.wall_time,
            _assignment(solver, ctx, cycle),
        )
    # FEASIBLE here means "found a solution but ran out of time before proving it's best".
    # Not good enough for determinacy, which relies on V being the true optimum.
    status = {cp_model.FEASIBLE: "not_proven", cp_model.INFEASIBLE: "infeasible"}.get(
        code, "unknown"
    )
    return OptimalResult(status, None, solver.wall_time, None)


def determinacy(cycle, rules, exclude=frozenset(), time_limit=10.0) -> dict[str, bool]:
    base = solve_optimal(cycle, rules, exclude=exclude, time_limit=time_limit)
    if base.status != "optimal":
        raise RuntimeError(f"can't analyse ties: base solve was {base.status}")
    assert base.assignment is not None  # always set when status is "optimal"
    out = {}
    for tid, cid in base.assignment.items():
        ctx = build_model(cycle, rules, exclude=exclude)
        ctx.model.add(sum(ctx.objective) == base.value)
        _, code = _solve(ctx, time_limit)
        if code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(
                "check model can't reach the optimum: base and check models differ"
            )

        if cid is None:
            ctx.model.add(sum(ctx.x[(tid, c.course_id)] for c in cycle.courses) >= 1)
        else:
            ctx.model.add(ctx.x[(tid, cid)] == 0)
        _, code = _solve(ctx, time_limit)
        if code not in (cp_model.INFEASIBLE, cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(f"timed out checking {tid}")
        out[tid] = code == cp_model.INFEASIBLE  # True = determined
    return out


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


def main(argv: list[str] | None = None) -> None:
    ### Parse command line arguments

    ap = argparse.ArgumentParser(
        description="Check whether the hard rules are feasible and whether the optimal assignment is determined (no ties) for a given cycle"
    )
    ap.add_argument("--config", default="config/pseudonymize.yaml")
    ap.add_argument("--rules", default="config/rules-2027.yaml", type=Path)
    ap.add_argument("--cycle", default=2027, type=int)
    ap.add_argument(
        "--exclude", nargs="*", type=int, default=[], help="rule ids to skip, e.g. 5"
    )
    ap.add_argument("--time-limit", default=60.0, type=float)
    ap.add_argument("--optimize", action="store_true")
    args = ap.parse_args(argv)

    config = load_config(args.config)
    derived, params = out_path(config, "derived"), out_path(config, "params")
    cycle = load_cycle(
        derived,
        params_dir=params,
        cycle=args.cycle,
        lineage_path=out_path(config, "key") / "course_lineage.csv",
    )
    gone = sum(t.is_repeater and t.incumbent_course_id is None for t in cycle.teachers)
    if gone:
        print(
            f"note: {gone} repeater(s) whose prior course was discontinued: no incumbency applied"
        )

    ### Check feasibility of hard rules, optionally excluding some

    hard_rules = load_hard_rules(args.rules)
    all_ids = {r["id"] for r in yaml.safe_load(args.rules.read_text())["rules"]}
    exclude = frozenset(args.exclude)
    if exclude - all_ids:
        raise SystemExit(f"--exclude {sorted(exclude - all_ids)}: no such rule id")
    inactive = exclude - {r["id"] for r in hard_rules}
    if inactive:
        print(f"note: --exclude {sorted(inactive)} already off (deferred or not hard)")
        exclude -= inactive
    names = {r["id"]: r["name"] for r in hard_rules}

    print(
        f"cycle {args.cycle}: {len(cycle.teachers)} teachers, {len(cycle.courses)} courses"
    )
    print(
        "hard rules to check feasibility on: "
        + ", ".join(f"{i} {names[i]}" for i in names if i not in exclude)
    )
    if exclude:
        print("excluded: " + ", ".join(f"{i} {names[i]}" for i in sorted(exclude)))

    feasibility_result = check_feasibility(
        cycle, hard_rules, exclude=exclude, time_limit=args.time_limit
    )
    print(
        f"\nSTATUS: {feasibility_result.status.upper()}  ({feasibility_result.wall_time:.2f}s)"
    )

    report: dict = {
        "when": datetime.now().isoformat(timespec="seconds"),
        "cycle": args.cycle,
        "optimize": args.optimize,
        "rules_file": str(args.rules),
        "excluded": sorted(exclude),
        "feasibility_result": asdict(feasibility_result),
    }

    if feasibility_result.status == "feasible":
        a = feasibility_result.assignment or {}
        placed = sum(v is not None for v in a.values())
        running = len({v for v in a.values() if v is not None})
        print(
            f"  {placed}/{len(a)} teachers placed, {running}/{len(cycle.courses)} courses running"
        )
        print(
            "  (one arbitrary feasible assignment: no objective yet, so not a prediction)"
        )
    elif feasibility_result.status == "infeasible":
        active = [r for r in hard_rules if r["id"] not in exclude]
        d = diagnose(cycle, active)
        report["diagnose"] = {
            "leave_one_out": {str(k): v for k, v in d["leave_one_out"].items()},
            "cumulative": d["cumulative"],
        }
        print("\nleave-one-out (feasible = this rule is part of the conflict):")
        for i, st in d["leave_one_out"].items():
            print(f"  without {i} {names[i]:<28} {st}")
        first, st = d["cumulative"][-1]
        if st == "infeasible":
            print(
                f"\nbreaks when rule {first[-1]} ({names[first[-1]]}) is added after {first[:-1]}"
            )
        print("\nThis is a finding, not a bug: log it in docs/encoding-decisions.md.")
    else:
        print(
            "  not a verdict: try a longer --time-limit, or check for a modelling error"
        )

    ### Check optimality and determinacy of the assignment if requested

    if args.optimize:
        rules = load_rules(args.rules)
        opt = solve_optimal(cycle, rules, exclude=exclude, time_limit=args.time_limit)
        print(f"OPTIMAL: {opt.status}  value={opt.value}  ({opt.wall_time:.2f}s)")
        if opt.status == "optimal":
            det = determinacy(cycle, rules, exclude=exclude)

            submitters = {p.teacher_id for p in cycle.preferences}
            determined = [t for t, d in det.items() if d]
            contested_sub = [t for t, d in det.items() if not d and t in submitters]
            contested_non = [t for t, d in det.items() if not d and t not in submitters]

            print(f"  determined:               {len(determined)}")
            print(
                f"  contested, submitted:     {len(contested_sub)}   <- the RQ1 number"
            )
            print(
                f"  contested, no submission: {len(contested_non)}   (score 0 anywhere; not evidence of discretion)"
            )

            report["optimal"] = asdict(opt)
            report["determinacy"] = det
            report["contested_submitters"] = contested_sub
            report["contested_non_submitters"] = contested_non

    ### Write report to disk

    runs = out_path(config, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{report['when'].replace(':', '')}_feasibility.json"
    path.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
