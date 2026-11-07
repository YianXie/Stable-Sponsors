"""Did office-unplaced teachers rank courses that did not run?

Evidence for or against "the course set is fixed before sponsor allocation" (rule 10, Finding 3).
If a course did not run while enough willing, unplaced sponsors had ranked it, it was not cancelled
for lack of sponsors. If no unplaced teacher ranked any unrun course, the data cannot tell the two
explanations apart. A course whose unplaced rankers can't cover 1 male + 1 female (M-009) is not
"enough", which is what the gender-staffable column adds.

Reads inputs (preferences, which courses ran) and observed placements only. Console output is counts
and trip codes; ``--list`` adds T### IDs.

    uv run python -m stable_sponsors.course_set_check
"""

import argparse
from collections import defaultdict

from stable_sponsors.interview_checks import ranking_genders, staffable
from stable_sponsors.model import load_cycle_from_config
from stable_sponsors.pseudonymize.idmap import for_cycle, load_config, out_path
from stable_sponsors.review import load_office

DEFAULT_SPONSORS = 2  # M-008


def unrun_demand(
    unplaced: set[str],
    prefs: list[tuple[str, str, int, str]],
    unrun: set[str],
) -> dict[str, list[tuple[str, str, int]]]:
    """Unrun course -> [(teacher_id, round_id, rank)] for unplaced teachers who ranked it."""
    out: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for tid, rnd, rank, cid in prefs:
        if tid in unplaced and cid in unrun:
            out[cid].append((tid, rnd, rank))
    return {c: sorted(v) for c, v in sorted(out.items())}


def gender_staffable(
    unplaced: set[str],
    prefs: list[tuple[str, str, str | None]],
    unrun: set[str],
    need: dict[str, int | None],
) -> dict[str, bool]:
    """Unrun course -> can its unplaced rankers staff it with 1 male + 1 female?

    ``prefs`` holds (teacher_id, course_id, gender). The 1/1 comes from M-009, not from
    course_params.csv, so this doesn't depend on whether the params have been refreshed.
    """
    rankers: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    for tid, cid, gender in prefs:
        if tid in unplaced and cid in unrun:
            rankers[cid].append((tid, gender))
    return {
        cid: staffable(rows, 1, 1, need.get(cid) or DEFAULT_SPONSORS)
        for cid, rows in sorted(rankers.items())
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="config/pseudonymize.yaml")
    ap.add_argument("--cycle", default=2027, type=int)
    ap.add_argument("--list", action="store_true", help="also print T### IDs")
    args = ap.parse_args(argv)

    config = load_config(args.config)
    cycle = load_cycle_from_config(config, args.cycle)
    office = load_office(
        out_path(for_cycle(config, args.cycle), "derived") / "placements.csv",
        args.cycle,
    )

    unplaced = {t.teacher_id for t in cycle.teachers} - set(office)
    unrun = {c.course_id for c in cycle.courses if not c.ran}
    need = {c.course_id: c.min_sponsors for c in cycle.courses}
    prefs = [(p.teacher_id, p.round_id, p.rank, p.course_id) for p in cycle.preferences]
    demand = unrun_demand(unplaced, prefs, unrun)
    gender_ok = gender_staffable(
        unplaced,
        ranking_genders(cycle),
        unrun,
        need,
    )

    rankers = {tid for rows in demand.values() for tid, _, _ in rows}
    print(
        f"cycle {args.cycle}: {len(unplaced)} office-unplaced teachers, {len(unrun)} courses did not run"
    )
    print(
        f"unplaced teachers who ranked >= 1 unrun course: {len(rankers)} / {len(unplaced)}"
    )
    print(
        f"unrun courses ranked by >= 1 unplaced teacher: {len(demand)} / {len(unrun)}\n"
    )
    for cid, rows in demand.items():
        n = len({tid for tid, _, _ in rows})
        m = need.get(cid)
        flag = "  <- enough unplaced rankers to staff it" if m and n >= m else ""
        ranks = ", ".join(f"{rnd}#{rank}" for _, rnd, rank in rows)
        # never beside IDs: "no" would say that the two listed teachers share a gender
        gender_col = (
            ""
            if args.list
            else f"gender-staffable={'yes' if gender_ok[cid] else 'no'}  "
        )
        print(
            f"  {cid}: {n} unplaced ranker(s), min sponsors {m if m else '?'}  "
            f"{gender_col}[{ranks}]{flag}"
        )
        if args.list:
            print(f"    {' '.join(sorted({tid for tid, _, _ in rows}))}")
    if demand:
        enough = [
            c
            for c, rows in demand.items()
            if len({r[0] for r in rows}) >= (need.get(c) or DEFAULT_SPONSORS)
        ]
        print(f"\nenough unplaced rankers: {len(enough)}", end="")
        if not args.list:
            print(
                f", of which gender-staffable: {sum(gender_ok[c] for c in enough)}",
                end="",
            )
        print()
    if not demand:
        print(
            "  none: the data cannot separate 'course set fixed first' from 'cancelled for lack of sponsors'"
        )


if __name__ == "__main__":
    main()
