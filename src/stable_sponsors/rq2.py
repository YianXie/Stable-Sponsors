"""RQ2: allocate one cycle under each objective and by random serial dictatorship, and compare
the results with the office's allocation.

Writes ``private_root/runs/<when>_rq2_run.json`` (which may hold T### IDs, like
``*_model_run.json``). The console gets two tables of counts and the path written, nothing else:
no teacher IDs and no gender.

    uv run python -m stable_sponsors.rq2 --determinacy
"""

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import yaml

from stable_sponsors.data import Cycle
from stable_sponsors.metrics import agreement, allocation_metrics, summarise
from stable_sponsors.model import load_cycle_from_config, load_rules
from stable_sponsors.objectives import (
    OBJECTIVES,
    RANK_RULE,
    ROUND_RULE,
    ObjectiveName,
    leximin_population,
    objective_determinacy,
    preference_scores,
    solve_objective,
)
from stable_sponsors.pseudonymize.idmap import (
    DEFAULT_CONFIG,
    REPO_ROOT,
    for_cycle,
    load_config,
    out_path,
)
from stable_sponsors.review import Assignment, load_office, score
from stable_sponsors.serial import random_orders, serial_dictatorship, submitters

DEFAULT_RULES = Path("config/rules-2027-v3.1.yaml")  # frozen; never edit it
RUN_SUFFIX = "_rq2_run"
NA = "—"  # a cell with no value: not computed, or not meaningful for that column


def _git(*args: str) -> str | None:
    """Output of a git command in the repo, or None if git fails."""
    try:
        done = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout


def provenance(paths: list[Path]) -> dict:
    """The code commit, whether the tree has uncommitted changes, and one hash of the inputs.

    The hash covers each file's name and bytes, in sorted path order, so it does not depend on
    where private_root is.
    """
    commit, status = _git("rev-parse", "HEAD"), _git("status", "--porcelain")
    h = hashlib.sha256()
    for p in sorted(Path(p) for p in paths):
        data = p.read_bytes()
        # Name and length first, so no two different file sets hash the same.
        h.update(f"{p.name}\0{len(data)}\0".encode())
        h.update(data)
    return {
        "commit": commit.strip() if commit is not None else None,
        "dirty": bool(status.strip()) if status is not None else None,
        "inputs_sha256": h.hexdigest(),
    }


def _excluded(rules_path: Path, exclude: list[int]) -> frozenset[int]:
    """The active hard rules to leave out. Refuses rules 1 and 6 and anything not a hard rule."""
    asked = frozenset(exclude)
    if asked & {RANK_RULE, ROUND_RULE}:
        raise SystemExit(
            f"--exclude {RANK_RULE} or {ROUND_RULE}: they define the score"
        )
    every = yaml.safe_load(rules_path.read_text())["rules"]
    hard = {r["id"] for r in every if r["class"] == "hard"}
    if asked - hard:
        raise SystemExit(f"--exclude {sorted(asked - hard)}: no such hard rule")
    # A deferred or contradicted hard rule is already off: excluding it changes nothing.
    return asked & {r["id"] for r in load_rules(rules_path)}


def _input_paths(config: dict, cycle_no: int, rules_path: Path) -> list[Path]:
    derived = out_path(for_cycle(config, cycle_no), "derived")
    params = out_path(config, "params")
    return [
        *(
            derived / f"{n}.csv"
            for n in ("teachers", "courses", "preferences", "placements")
        ),
        params / "teacher_params.csv",
        params / "course_params.csv",
        rules_path,
    ]


def _office(config: dict, cycle: Cycle, cycle_no: int) -> Assignment:
    """The office's allocation, with None for every cycle teacher it left unplaced."""
    placements = out_path(for_cycle(config, cycle_no), "derived") / "placements.csv"
    return {t.teacher_id: None for t in cycle.teachers} | load_office(
        placements, cycle_no
    )


def run_rq2(
    config: dict,
    cycle_no: int,
    rules_path: Path,
    exclude: frozenset[int],
    objectives: list[ObjectiveName],
    n_orders: int,
    seed: int,
    time_limit: float,
    with_determinacy: bool,
    lineage: bool,
) -> dict:
    """Every allocation, its metrics and its agreement with the office, as the report dict."""
    cycle = load_cycle_from_config(config, cycle_no, use_lineage=lineage)
    rules = load_rules(rules_path)
    scores = preference_scores(cycle, rules)
    population = leximin_population(cycle, exclude)
    office = _office(config, cycle, cycle_no)

    def metrics(a: Assignment) -> dict:
        return allocation_metrics(cycle, a, scores, population, rules=rules)

    report: dict = {
        "when": datetime.now().isoformat(timespec="seconds"),
        "cycle": cycle_no,
        "rules_file": str(rules_path),
        "excluded": sorted(exclude),
        "lineage": lineage,
        "provenance": provenance(_input_paths(config, cycle_no, rules_path)),
        "office": {"metrics": metrics(office)},
        "objectives": {},
    }

    for name in objectives:
        result = solve_objective(cycle, rules, name, exclude, time_limit)
        entry: dict = {"result": asdict(result)}
        if result.assignment is None:
            # Not proven optimal: no allocation to measure, and not a verdict either.
            entry["metrics"] = entry["agreement_with_office"] = None
        else:
            entry["metrics"] = metrics(result.assignment)
            entry["agreement_with_office"] = agreement(result.assignment, office)
            if with_determinacy:
                det = objective_determinacy(cycle, rules, name, exclude, time_limit)
                who = set(submitters(cycle))
                contested = {t for t, d in det.items() if not d and t in who}
                entry["determinacy"] = det
                # score() wants the office's placements only: a None would count as a course.
                placed = {t: c for t, c in office.items() if c is not None}
                entry["review"] = score(result.assignment, det, placed, contested)
        report["objectives"][name] = entry

    # The baseline: submitters pick one at a time, in n seeded random orders.
    per_order = [
        serial_dictatorship(cycle, rules, order, exclude, time_limit)
        for order in random_orders(submitters(cycle), n_orders, seed)
    ]
    report["rsd"] = {
        "orders": n_orders,
        "seed": seed,
        "summary": summarise([metrics(a) for a in per_order]),
        "agreement_with_office": summarise([agreement(a, office) for a in per_order]),
    }
    return report


# --------------------------------------------------------------------------
# Console tables: counts only.
# --------------------------------------------------------------------------


def _fmt(v: object) -> str:
    if v is None:
        return NA
    if isinstance(v, float):
        return f"{v:g}" if v.is_integer() else f"{v:.1f}"
    return str(v)


def _range(stats: dict | None) -> str:
    """'mean (min–max)' of a summarise() entry."""
    if stats is None:
        return NA
    return f"{_fmt(float(stats['mean']))} ({_fmt(stats['min'])}–{_fmt(stats['max'])})"


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def _column(entry: dict, row: str, with_determinacy: bool) -> str:
    """One objective's cell. An objective not proven optimal shows its status instead."""
    if entry["metrics"] is None:
        return entry["result"]["status"]
    if row == "same_placement":
        return _fmt(entry["agreement_with_office"]["same_placement"])
    if with_determinacy and row == "determined":
        return _fmt(sum(entry["determinacy"].values()))
    if with_determinacy and row == "determined_match":
        return _fmt(entry["review"]["determined_match"])
    return _fmt(entry["metrics"][row])


def tables(report: dict, with_determinacy: bool) -> str:
    """The metrics table and the rank_hist table, as markdown."""
    names = list(report["objectives"])
    header = ["metric", "office", *names, "RSD mean (min–max)"]
    office, rsd = report["office"]["metrics"], report["rsd"]
    scalar = [k for k in office if k != "rank_hist"]
    extra = ["same_placement"] + (
        ["determined", "determined_match"] if with_determinacy else []
    )

    rows = []
    for row in scalar + extra:
        office_cell = _fmt(office[row]) if row in office else NA
        if row in office:
            rsd_cell = _range(rsd["summary"].get(row))
        elif row == "same_placement":
            rsd_cell = _range(rsd["agreement_with_office"].get(row))
        else:
            rsd_cell = NA  # no determinacy for serial dictatorship
        cells = [_column(report["objectives"][n], row, with_determinacy) for n in names]
        rows.append([row, office_cell, *cells, rsd_cell])

    hists = [office["rank_hist"]] + [
        (e["metrics"] or {}).get("rank_hist", {}) for e in report["objectives"].values()
    ]
    rsd_hist = rsd["summary"].get("rank_hist", {})
    labels = sorted({k for h in hists for k in h} | set(rsd_hist))
    hist_rows = []
    for label in labels:
        cells = [
            e["result"]["status"]
            if e["metrics"] is None
            else _fmt(e["metrics"]["rank_hist"].get(label, 0))
            for e in report["objectives"].values()
        ]
        rsd_cell = _range(rsd_hist[label]) if label in rsd_hist else "0"
        hist_rows.append(
            [label, _fmt(office["rank_hist"].get(label, 0)), *cells, rsd_cell]
        )
    return _table(header, rows) + "\n\n" + _table(["rank_hist", *header[1:]], hist_rows)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])  # pyright: ignore[reportOptionalMemberAccess]
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--rules", default=DEFAULT_RULES, type=Path)
    ap.add_argument("--cycle", default=2027, type=int)
    ap.add_argument(
        "--exclude", nargs="*", type=int, default=[], help="hard rule ids to skip"
    )
    ap.add_argument("--time-limit", default=60.0, type=float, help="seconds per solve")
    ap.add_argument(
        "--objectives", nargs="*", choices=OBJECTIVES, default=list(OBJECTIVES)
    )
    ap.add_argument("--orders", default=20, type=int, help="random serial orders")
    ap.add_argument("--seed", default=0, type=int)
    ap.add_argument(
        "--determinacy",
        action="store_true",
        help="also check which placements are the same in every optimal solution",
    )
    ap.add_argument(
        "--no-lineage",
        dest="lineage",
        action="store_false",
        help="disable the lineage fix: match repeaters' prior course by code",
    )
    args = ap.parse_args(argv)

    config = load_config(args.config)
    report = run_rq2(
        config,
        args.cycle,
        args.rules,
        _excluded(args.rules, args.exclude),
        args.objectives,
        args.orders,
        args.seed,
        args.time_limit,
        args.determinacy,
        args.lineage,
    )
    runs = out_path(config, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{report['when'].replace(':', '')}{RUN_SUFFIX}.json"
    path.write_text(json.dumps(report, indent=2))
    print(tables(report, args.determinacy))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
