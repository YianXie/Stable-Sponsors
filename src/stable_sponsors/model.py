import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import yaml
from ortools.sat.python import cp_model

from stable_sponsors.data import Cycle, load_cycle
from stable_sponsors.pseudonymize.idmap import load_config, out_path
from stable_sponsors.rules import hard  # noqa: F401  (registers encoders)
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
    return ctx


def check_feasibility(
    cycle, rules, exclude=frozenset(), time_limit=30.0
) -> FeasibilityResult:
    ctx = build_model(cycle, rules, exclude)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.random_seed = 0  # reproducible runs
    solver.parameters.num_workers = 8
    status = STATUS[solver.solve(ctx.model)]

    assignment = None
    if status == "feasible":
        assignment = {t.teacher_id: None for t in cycle.teachers}
        for (tid, cid), var in ctx.x.items():
            if solver.value(var):
                assignment[tid] = cid
    applied = tuple(r["id"] for r in rules if r["id"] not in exclude)
    return FeasibilityResult(status, applied, solver.wall_time, assignment)


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
    ap = argparse.ArgumentParser(
        description="Check whether the hard rules are feasible."
    )
    ap.add_argument("--config", default="config/pseudonymize.yaml")
    ap.add_argument("--rules", default="config/rules-2027.yaml", type=Path)
    ap.add_argument("--cycle", default=2027, type=int)
    ap.add_argument(
        "--exclude", nargs="*", type=int, default=[], help="rule ids to skip, e.g. 5"
    )
    ap.add_argument("--time-limit", default=30.0, type=float)
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    derived, params = out_path(cfg, "derived"), out_path(cfg, "params")
    cycle = load_cycle(derived, params_dir=params, cycle=args.cycle)

    rules = load_hard_rules(args.rules)
    all_ids = {r["id"] for r in yaml.safe_load(args.rules.read_text())["rules"]}
    exclude = frozenset(args.exclude)
    if exclude - all_ids:
        raise SystemExit(f"--exclude {sorted(exclude - all_ids)}: no such rule id")
    inactive = exclude - {r["id"] for r in rules}
    if inactive:
        print(f"note: --exclude {sorted(inactive)} already off (deferred or not hard)")
        exclude -= inactive
    names = {r["id"]: r["name"] for r in rules}

    print(
        f"cycle {args.cycle}: {len(cycle.teachers)} teachers, {len(cycle.courses)} courses"
    )
    print("rules: " + ", ".join(f"{i} {names[i]}" for i in names if i not in exclude))
    if exclude:
        print("excluded: " + ", ".join(f"{i} {names[i]}" for i in sorted(exclude)))

    result = check_feasibility(
        cycle, rules, exclude=exclude, time_limit=args.time_limit
    )
    print(f"\nSTATUS: {result.status.upper()}  ({result.wall_time:.2f}s)")

    report: dict = {
        "when": datetime.now().isoformat(timespec="seconds"),
        "cycle": args.cycle,
        "rules_file": str(args.rules),
        "excluded": sorted(exclude),
        "result": asdict(result),
    }
    if result.status == "feasible":
        a = result.assignment or {}
        placed = sum(v is not None for v in a.values())
        running = len({v for v in a.values() if v is not None})
        print(
            f"  {placed}/{len(a)} teachers placed, {running}/{len(cycle.courses)} courses running"
        )
        print(
            "  (one arbitrary feasible assignment: no objective yet, so not a prediction)"
        )
    elif result.status == "infeasible":
        active = [r for r in rules if r["id"] not in exclude]
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

    runs = out_path(cfg, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{report['when'].replace(':', '')}_feasibility.json"
    path.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
