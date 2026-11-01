"""Evidence checks for the 2026-10-28 interview: do the data agree with what the office said?

Three counts that gate later model changes (thresholds in docs/encoding-decisions.md):

    (a) why the office's rule-4 violators may have ended up in an unranked course
    (b) repeaters by what happened to their incumbent course, and whether they submitted
    (c) residuals on language immersion courses
    (d) how many teachers ranked the courses that did not run
    (e) whether teachers who preferred those courses could have staffed them, course by course
    (f) the fewest fallback placements the office's course set needs, and what they depend on

Reads inputs and observed placements only. Console output is counts and trip codes; gender and
language are never printed per teacher.

    uv run python -m stable_sponsors.interview_checks
"""

import argparse
from collections import Counter
from dataclasses import replace
from pathlib import Path

from stable_sponsors.compare import ORIGINS, claim_scores, fallback_origin, violations
from stable_sponsors.data import Cycle, load_observed_placements
from stable_sponsors.model import load_cycle_from_config, load_rules, min_fallbacks
from stable_sponsors.pseudonymize.idmap import DEFAULT_CONFIG, load_config, out_path

# The 2027 catalogue's language immersion courses. A country doesn't identify them: China has 8 courses.
LANGUAGE_COURSES = "CHIN-1,FRAN-1,SPAI-1"


def staffable(
    rankers: list[tuple[str, str | None]],
    male_slots: int,
    female_slots: int,
    min_sponsors: int,
) -> bool:
    """Can these rankers staff a course: enough distinct teachers, and the slots covered?

    Each ranker is (teacher_id, gender). A teacher with no known gender, or with both on record, can
    fill either slot: unknown is not "no".
    """
    labels: dict[str, set[str]] = {}
    for tid, gender in rankers:
        labels.setdefault(tid, set()).update({gender} if gender else set())
    known = Counter(next(iter(g)) if len(g) == 1 else None for g in labels.values())
    short = max(male_slots - known["male"], 0) + max(female_slots - known["female"], 0)
    return len(labels) >= min_sponsors and short <= known[None]


def ranking_genders(cycle: Cycle) -> list[tuple[str, str, str | None]]:
    """(teacher_id, course_id, gender) for each ranking, using the teacher's gender.

    A slot label only appears on courses the form showed as gendered, so it can't be read per
    course: no unrun course has one. The teacher's gender (inferred in params) is what rule 5 uses.
    """
    gender = {t.teacher_id: t.gender for t in cycle.teachers}
    return [
        (p.teacher_id, p.course_id, gender[p.teacher_id]) for p in cycle.preferences
    ]


def rankers_at_placement(
    ids: list[str], placed: dict[str, str], prefs: list[tuple[str, str]]
) -> list[int]:
    """Sorted: how many teachers ranked the course each of these teachers was placed in."""
    rankers = Counter(cid for _, cid in set(prefs))
    return sorted(rankers[placed[tid]] for tid in ids)


def without_pins(cycle: Cycle, teacher_ids: set[str]) -> Cycle:
    """The cycle with these repeaters' incumbent courses removed, so rule 0 doesn't pin them."""
    return replace(
        cycle,
        teachers=tuple(
            replace(t, incumbent_course_id=None) if t.teacher_id in teacher_ids else t
            for t in cycle.teachers
        ),
    )


def repeater_status(cycle: Cycle) -> Counter[tuple[str, bool]]:
    """Repeaters by ("incumbent_ran" | "incumbent_unrun" | "discontinued", submitted a form)."""
    ran = {c.course_id for c in cycle.courses if c.ran}
    submitters = {p.teacher_id for p in cycle.preferences}
    out: Counter[tuple[str, bool]] = Counter()
    for t in cycle.teachers:
        if not t.is_repeater:
            continue
        if t.incumbent_course_id is None:
            status = "discontinued"
        elif t.incumbent_course_id in ran:
            status = "incumbent_ran"
        else:
            status = "incumbent_unrun"
        out[(status, t.teacher_id in submitters)] += 1
    return out


def preferring_rankers(
    prefs: list[tuple[str, str, str | None]],
    placed: dict[str, str],
    scores: dict[tuple[str, str], int],
    incumbent: dict[str, str],
    unrun: set[str],
) -> dict[str, list[tuple[str, str | None]]]:
    """Unrun course -> (teacher_id, slot_gender) of rankers who score more on it than where placed.

    ``prefs`` holds (teacher_id, course_id, slot_gender). Unplaced scores 0, and a repeater on
    their incumbent course isn't a candidate. Depends on the assumed weights in ``scores``.
    """
    out: dict[str, list[tuple[str, str | None]]] = {}
    for tid, cid, gender in prefs:
        if cid not in unrun or placed.get(tid) == incumbent.get(tid, ""):
            continue
        if scores[(tid, cid)] > scores.get((tid, placed.get(tid, "")), 0):
            out.setdefault(cid, []).append((tid, gender))
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--cycle", default=2027, type=int)
    ap.add_argument("--rules", default="config/rules-2027.yaml")
    ap.add_argument(
        "--fixed-set-rules",
        default="config/rules-2027-v3.1-fixed-set.yaml",
        help="rules with rule 10 on and rule 11 active, for check (f)",
    )
    ap.add_argument(
        "--language-courses",
        default=LANGUAGE_COURSES,
        help="comma-separated language immersion course IDs",
    )
    args = ap.parse_args(argv)

    config = load_config(args.config)
    cycle = load_cycle_from_config(config, args.cycle)
    observed = load_observed_placements(
        out_path(config, "derived") / "placements.csv", cycle
    )
    placed = {p.teacher_id: p.course_id for p in observed}
    v = violations(cycle, observed)

    ran = {c.course_id for c in cycle.courses if c.ran}
    ranked: dict[str, set[str]] = {}
    for p in cycle.preferences:
        ranked.setdefault(p.teacher_id, set()).add(p.course_id)

    # (a) with a comparison group: a teacher who ranked 7 courses often has one that didn't run,
    # so a share among the violators means little on its own.
    violators = set(v["4 only_ranked"])
    others = {
        tid for tid in ranked if tid not in violators and placed.get(tid) in ranked[tid]
    }
    print(f"(a) origin of rule-4 violators, cycle {args.cycle}")
    print(f"    {'':<14}{'violators':>10}{'placed in ranked':>18}")
    for origin in ORIGINS:
        a = sum(fallback_origin(ranked[t], ran) == origin for t in violators)
        b = sum(fallback_origin(ranked[t], ran) == origin for t in others)
        print(f"    {origin:<14}{a:>10}{b:>18}")
    print(f"    {'total':<14}{len(violators):>10}{len(others):>18}")
    kinds = {c.course_id: c.course_type for c in cycle.courses}
    pools = Counter(kinds[placed[t]] for t in violators)
    print(f"    placed by the office in: {dict(sorted(pools.items()))}")
    landed = rankers_at_placement(
        sorted(violators),
        placed,
        [(p.teacher_id, p.course_id) for p in cycle.preferences],
    )
    print(f"    rankers of the course each was placed in: {landed}")

    print("\n(b) repeaters: (status, submitted a form)")
    status = repeater_status(cycle)
    for key in sorted(status):
        print(f"    {key[0]:<16} submitted={key[1]!s:<6}{status[key]:>4}")
    print(f"    {'total':<33}{sum(status.values()):>4}")

    language = {c.strip() for c in args.language_courses.split(",")}
    residuals = {
        "rule 4": set(v["4 only_ranked"]),
        "rule 0": set(v["0 incumbency"]),
    }
    print(f"\n(c) residuals whose office course is one of {sorted(language)}")
    hits = set()
    for name, ids in residuals.items():
        here = {t for t in ids if placed.get(t) in language}
        hits |= here
        print(f"    {name}: {len(here)} / {len(ids)}")
    print(f"    either: {len(hits)}")

    # M-011 says a course with no sign-ups drops. How many rankers did the unrun courses have?
    rankers: dict[str, set[str]] = {}
    for p in cycle.preferences:
        rankers.setdefault(p.course_id, set()).add(p.teacher_id)
    unrun = [c.course_id for c in cycle.courses if not c.ran]
    print("\n(d) courses that did not run, by number of distinct rankers")
    for n, k in sorted(Counter(len(rankers.get(c, ())) for c in unrun).items()):
        print(f"    {n} ranker(s): {k}")
    ranks = Counter(p.rank for p in cycle.preferences if p.course_id in set(unrun))
    print(f"    their rankings by rank: {dict(sorted(ranks.items()))}")

    # Rule ids 1 and 6 are the same in both rule files; the weights are assumed.
    scores = claim_scores(cycle, load_rules(Path(args.rules)))
    incumbent = {
        t.teacher_id: t.incumbent_course_id
        for t in cycle.teachers
        if t.is_repeater and t.incumbent_course_id is not None
    }
    wanting = preferring_rankers(
        ranking_genders(cycle), placed, scores, incumbent, set(unrun)
    )
    enough = [c for c, rows in wanting.items() if staffable(rows, 1, 1, 2)]
    teachers = {t for rows in wanting.values() for t, _ in rows}
    known = {t for rows in wanting.values() for t, g in rows if g is not None}
    print("\n(e) unrun courses, teachers who score more on them than where placed")
    print(f"    can cover 1M/1F and 2 sponsors: {len(enough)} / {len(unrun)}")
    print(f"    teachers with a known gender: {len(known)} / {len(teachers)}")
    print(
        "    per course, not jointly: a placed teacher who moved would leave their course short"
    )

    # Rule 4 off, rule 11 counting: can the office's courses run from ranked courses alone?
    fixed = load_rules(Path(args.fixed_set_rules))
    no_rule_4 = frozenset({4})
    print("\n(f) fewest fallback placements on the office's course set")
    print(
        f"    all rules:                       {min_fallbacks(cycle, fixed, no_rule_4)}"
    )
    print(
        f"    without rule 5:                  {min_fallbacks(cycle, fixed, no_rule_4 | {5})}"
    )
    suspect = without_pins(cycle, set(v["0 incumbency"]))
    print(
        f"    without the rule-0 residuals' pins: {min_fallbacks(suspect, fixed, no_rule_4)}"
    )


if __name__ == "__main__":
    main()
