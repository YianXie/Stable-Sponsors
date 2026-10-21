import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import yaml
from ortools.sat.python import cp_model

from stable_sponsors.data import Cycle, load_cycle
from stable_sponsors.pseudonymize.idmap import DEFAULT_CONFIG, load_config, out_path
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

# The run report contract: main() writes runs/<when>_model_run.json, reproduction.py reads it.
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
    value: int | None  # best total score V
    wall_time: float
    assignment: dict[str, str | None] | None


def active_rules(rules: list[dict], classes=("hard", "priority")) -> list[dict]:
    return [r for r in rules if r["class"] in classes and r["status"] != "deferred"]


def load_rules(path: Path, classes=("hard", "priority")) -> list[dict]:
    return active_rules(yaml.safe_load(path.read_text())["rules"], classes)


def load_hard_rules(path: Path) -> list[dict]:
    return load_rules(path, classes=("hard",))


def load_cycle_from_config(cfg: dict, cycle: int) -> Cycle:
    """One cycle of the real data under private_root: derived/, params/ and key/course_lineage.csv."""
    return load_cycle(
        out_path(cfg, "derived"),
        params_dir=out_path(cfg, "params"),
        cycle=cycle,
        lineage_path=out_path(cfg, "key") / "course_lineage.csv",
    )


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

    # One model pinned at the optimum; each teacher's check runs on a copy of it.
    ctx = build_model(cycle, rules, exclude=exclude)
    ctx.model.add(sum(ctx.objective) == base.value)
    if _solve(ctx.model, time_limit)[1] not in SOLVED:
        raise RuntimeError(
            "check model can't reach the optimum: base and check models differ"
        )
    out = {}
    for tid, cid in base.assignment.items():
        model = ctx.model.clone()
        x = {
            c: model.get_bool_var_from_proto_index(ctx.x[(tid, c)].index) for c in ctx.y
        }
        if cid is None:
            model.add(sum(x.values()) >= 1)
        else:
            model.add(x[cid] == 0)
        _, code = _solve(model, time_limit)
        if code != cp_model.INFEASIBLE and code not in SOLVED:
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
    args = ap.parse_args(argv)

    config = load_config(args.config)
    cycle = load_cycle_from_config(config, args.cycle)
    gone = sum(t.is_repeater and t.incumbent_course_id is None for t in cycle.teachers)
    if gone:
        print(
            f"note: {gone} repeater(s) whose prior course was discontinued: no incumbency applied"
        )

    ### Check feasibility of hard rules, optionally excluding some

    all_rules = yaml.safe_load(args.rules.read_text())["rules"]
    hard_rules = active_rules(all_rules, classes=("hard",))
    all_ids = {r["id"] for r in all_rules}
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
        rules = active_rules(all_rules)
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

            report[OPTIMAL_KEY] = asdict(opt)
            report[DETERMINACY_KEY] = det
            report["contested_submitters"] = contested_sub
            report["contested_non_submitters"] = contested_non

    ### Write report to disk

    runs = out_path(config, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{report['when'].replace(':', '')}{RUN_SUFFIX}.json"
    path.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
