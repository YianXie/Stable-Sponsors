"""List the cases that need manual review and write a review sheet.

    uv run python -m stable_sponsors.review_cases

Prints pseudonymous IDs only. The sheet goes to private_root/review/, outside
the repo. Look up names and course titles there using your crosswalk key.
"""

import csv

from stable_sponsors.compare import violations
from stable_sponsors.data import load_cycle, load_observed_placements
from stable_sponsors.pseudonymize.idmap import load_config, out_path

CYCLE = 2027


def main() -> None:
    cfg = load_config("config/pseudonymize.yaml")
    derived, params = out_path(cfg, "derived"), out_path(cfg, "params")
    cycle = load_cycle(
        derived, params, CYCLE, lineage_path=out_path(cfg, "key") / "course_lineage.csv"
    )
    observed = load_observed_placements(derived / "placements.csv", cycle)
    v = violations(cycle, observed)

    obs = {p.teacher_id: p.course_id for p in observed}
    teachers = {t.teacher_id: t for t in cycle.teachers}
    prefs: dict[str, list[str]] = {}
    for p in sorted(cycle.preferences, key=lambda p: (p.round_id, p.rank)):
        prefs.setdefault(p.teacher_id, []).append(
            f"{p.round_id}#{p.rank}:{p.course_id}"
        )

    cases = [(tid, "0 incumbency") for tid in v["0 incumbency"]]
    cases += [(tid, "4 only_ranked") for tid in v["4 only_ranked"]]

    # Swap partners: another case who holds a course this teacher ranked, and vice versa.
    ranked = {tid: {s.split(":", 1)[1] for s in prefs.get(tid, [])} for tid, _ in cases}

    def partners(tid):
        return [
            j
            for j, _ in cases
            if j != tid and obs.get(j) in ranked[tid] and obs.get(tid) in ranked[j]
        ]

    print(f"{len(cases)} cases for manual review:")
    for i, (tid, rule) in enumerate(cases, 1):
        print(f"  {i:>2}. {tid}  ({rule})")

    out_dir = out_path(cfg, "review")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"review_{CYCLE}.csv"
    if path.exists():
        raise SystemExit(
            f"{path} already exists. Move it aside first so your verdicts aren't overwritten."
        )

    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "case",
                "teacher_id",
                "rule",
                "placed_course",
                "prior_course (last year's code)",
                "incumbent_course (this year's code)",
                "is_repeater",
                "ranked (round#rank:course)",
                "swap_partners",
                "verdict",
                "note",
            ]
        )
        for i, (tid, rule) in enumerate(cases, 1):
            t = teachers[tid]
            w.writerow(
                [
                    i,
                    tid,
                    rule,
                    obs.get(tid) or "",
                    t.prior_course_id or "",
                    t.incumbent_course_id or "",
                    t.is_repeater,
                    " | ".join(prefs.get(tid, [])),
                    " ".join(partners(tid)),
                    "",
                    "",
                ]
            )
    print(f"\nreview sheet: {path}")
    print("verdicts: data:mapping | data:repeater_flag | unencoded_rule | discretion")


if __name__ == "__main__":
    main()
