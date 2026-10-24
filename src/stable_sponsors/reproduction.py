"""Count model allocations that are determined and match the office's allocation.

Reads one run report written by ``model --optimize`` (``private_root/runs/*_model_run.json``)
and compares it with the office's observed placements in ``derived/placements.csv``.

For every teacher in the run, two questions:

- determined: is their placement the same in every optimal solution? (``determinacy`` in the run)
- match: does the run's optimal assignment put them where the office did? (Both unplaced counts as a match.)

Only "determined and match" is evidence that the rules reproduce the office. For a contested teacher
the run JSON holds one optimal solution picked arbitrarily by the solver, so whether it matches is
reported but means nothing on its own.

Console output is counts only. ``--list`` adds T### IDs (allowed by the privacy rule), never names.

    uv run python -m stable_sponsors.reproduction                 # latest run with determinacy
    uv run python -m stable_sponsors.reproduction --run PATH --list
"""

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from stable_sponsors.data import read_csv
from stable_sponsors.model import DETERMINACY_KEY, OPTIMAL_KEY, RUN_SUFFIX
from stable_sponsors.pseudonymize.idmap import DEFAULT_CONFIG, load_config, out_path

Assignment = dict[str, str | None]  # teacher_id -> course_id, None = unplaced


def load_office(placements_csv: Path, cycle: int) -> Assignment:
    """Office placements for one cycle: teacher_id -> course_id (assigned rows only)."""
    df = read_csv(placements_csv)
    df = df[(df["cycle"] == str(cycle)) & (df["status"] == "assigned")]
    dup = df["teacher_id"][df["teacher_id"].duplicated()]
    if len(dup):
        raise SystemExit(
            f"office has {dup.nunique()} teacher(s) placed twice: {sorted(set(dup))}"
        )
    return dict(zip(df["teacher_id"], df["course_id"]))


def mismatch_kind(model: str | None, office: str | None) -> str:
    if model is None:
        return "model unplaced, office placed"
    if office is None:
        return "model placed, office unplaced"
    return "different course"


def score(model: Assignment, determined: dict[str, bool], office: Assignment) -> dict:
    """Cross-tabulate determined/contested x match/mismatch over the teachers in the run.

    ``office`` may omit unplaced teachers. Office teachers missing from the run are counted
    separately (they mean the run and derived/ are out of sync) and are not scored.
    """
    if set(model) != set(determined):
        raise ValueError("assignment and determinacy cover different teachers")

    cells: dict[tuple[str, str], list[str]] = {
        (d, m): [] for d in ("determined", "contested") for m in ("match", "mismatch")
    }
    kinds: dict[str, Counter] = {"determined": Counter(), "contested": Counter()}
    for tid in sorted(model):
        d = "determined" if determined[tid] else "contested"
        o = office.get(tid)
        if model[tid] == o:
            cells[(d, "match")].append(tid)
        else:
            cells[(d, "mismatch")].append(tid)
            kinds[d][mismatch_kind(model[tid], o)] += 1

    n = len(model)
    n_det = len(cells[("determined", "match")]) + len(cells[("determined", "mismatch")])
    hit = len(cells[("determined", "match")])
    det_match_placed = sum(
        office.get(t) is not None for t in cells[("determined", "match")]
    )
    return {
        "teachers": n,
        "office_placed": sum(office.get(t) is not None for t in model),
        "model_placed": sum(c is not None for c in model.values()),
        # a course runs iff it has at least one sponsor; office counts all its placements
        "office_courses_run": len(set(office.values())),
        "model_courses_run": len({c for c in model.values() if c is not None}),
        "office_not_in_run": sorted(set(office) - set(model)),
        "cells": {f"{d}_{m}": ids for (d, m), ids in cells.items()},
        "mismatch_kinds": {d: dict(c) for d, c in kinds.items()},
        "determined_match": hit,
        "determined_match_placed": det_match_placed,
        "determined_match_unplaced": hit - det_match_placed,
        "share_of_all": hit / n if n else 0.0,
        "share_of_determined": hit / n_det if n_det else 0.0,
    }


def latest_run(runs: Path) -> Path:
    for p in sorted(runs.glob(f"*{RUN_SUFFIX}.json"), reverse=True):
        if DETERMINACY_KEY in json.loads(p.read_text()):
            return p
    raise SystemExit(f"no run with determinacy in {runs}; run `model --optimize` first")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument(
        "--run", type=Path, help="run JSON (default: latest one with determinacy)"
    )
    ap.add_argument("--list", action="store_true", help="also print T### IDs per cell")
    args = ap.parse_args(argv)

    config = load_config(args.config)
    runs, derived = out_path(config, "runs"), out_path(config, "derived")
    run_path = args.run or latest_run(runs)
    run = json.loads(run_path.read_text())
    if (
        DETERMINACY_KEY not in run
        or run.get(OPTIMAL_KEY, {}).get("status") != "optimal"
    ):
        raise SystemExit(
            f"{run_path.name}: no proven optimum + determinacy; use an --optimize run"
        )

    placements = derived / "placements.csv"
    ran_at = datetime.fromisoformat(run["when"])
    if datetime.fromtimestamp(placements.stat().st_mtime) > ran_at:
        print(
            f"WARNING: placements.csv changed after this run ({run['when']}). Re-run the model.\n"
        )

    office = load_office(placements, run["cycle"])
    s = score(run[OPTIMAL_KEY]["assignment"], run[DETERMINACY_KEY], office)
    c = s["cells"]

    print(
        f"run: {run_path.name}  cycle {run['cycle']}  excluded rules: {run['excluded'] or 'none'}"
    )
    print(
        f"teachers: {s['teachers']}   placed by office: {s['office_placed']}   by model: {s['model_placed']}"
    )
    print(
        f"courses run by office: {s['office_courses_run']}   by model: {s['model_courses_run']}"
    )
    if s["office_not_in_run"]:
        print(
            f"WARNING: {len(s['office_not_in_run'])} office-placed teacher(s) not in the run (not scored)"
        )
    print()
    print(f"{'':12}{'match':>8}{'mismatch':>10}{'total':>8}")
    for d in ("determined", "contested"):
        m, x = len(c[f"{d}_match"]), len(c[f"{d}_mismatch"])
        print(f"{d:12}{m:>8}{x:>10}{m + x:>8}")
    print()
    print(
        f"DETERMINED AND MATCH: {s['determined_match']} / {s['teachers']} "
        f"({s['share_of_all']:.1%} of all; {s['share_of_determined']:.1%} of determined)"
    )
    print(
        f"  of which placed in the same course: {s['determined_match_placed']}, "
        f"both unplaced: {s['determined_match_unplaced']}"
    )
    for d, kinds in s["mismatch_kinds"].items():
        if kinds:
            print(
                f"{d} mismatches: "
                + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))
            )
    print(
        "\ncontested match/mismatch reflects one arbitrary optimal solution: not evidence."
    )

    if args.list:
        for cell, ids in c.items():
            print(f"\n{cell} ({len(ids)}): {' '.join(ids)}")
        if s["office_not_in_run"]:
            print(f"\noffice_not_in_run: {' '.join(s['office_not_in_run'])}")

    out = run_path.with_name(
        run_path.stem.removesuffix(RUN_SUFFIX) + "_reproduction.json"
    )
    out.write_text(json.dumps({"run": run_path.name, **s}, indent=2))
    print(f"\nwrote {out.name}")


if __name__ == "__main__":
    main()
