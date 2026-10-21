from collections import Counter
from pathlib import Path

from stable_sponsors.data import (
    ObservedPlacement,
    load_observed_placements,
    read_csv,
    read_lineage,
)
from stable_sponsors.model import (
    SOLVED,
    _solve,
    build_model,
    load_cycle_from_config,
    load_rules,
)
from stable_sponsors.pseudonymize.idmap import DEFAULT_CONFIG, load_config, out_path
from stable_sponsors.rules.context import Ctx

CYCLE = 2027


def _placed(observed) -> dict[str, str]:
    """teacher_id -> course_id for each observed placement."""
    return {p.teacher_id: p.course_id for p in observed}


def force_observed(ctx: Ctx, observed: tuple[ObservedPlacement, ...]):
    obs = _placed(observed)
    for (tid, cid), var in ctx.x.items():
        ctx.model.add(var == int(obs.get(tid) == cid))


def violations(cycle, observed) -> dict[str, list]:
    """Check the observed allocation against each hard rule directly."""
    obs = _placed(observed)
    courses = {c.course_id: c for c in cycle.courses}
    ranked = {(p.teacher_id, p.course_id) for p in cycle.preferences}
    submitters = {p.teacher_id for p in cycle.preferences}
    load = Counter(obs.values())

    v = {
        k: []
        for k in (
            "0 incumbency",
            "3 qualification",
            "4 only_ranked",
            "9 capacity",
            "10 course_set",
        )
    }
    for t in cycle.teachers:
        cid = obs.get(t.teacher_id)
        incumbent = t.incumbent_course_id if t.is_repeater else None
        if incumbent is not None and cid != incumbent:
            v["0 incumbency"].append(t.teacher_id)
        if cid is None:
            continue
        c = courses[cid]
        if not set(c.requires) <= set(t.qualifications):
            v["3 qualification"].append(t.teacher_id)
        # a repeater placed in their incumbent course needn't have ranked it
        if (
            t.teacher_id in submitters
            and (t.teacher_id, cid) not in ranked
            and cid != incumbent
        ):
            v["4 only_ranked"].append(t.teacher_id)
    for c in cycle.courses:
        n = load.get(c.course_id, 0)
        if c.ran and not (c.min_sponsors <= n <= c.max_sponsors):
            v["9 capacity"].append((c.course_id, n))
        if not c.ran and n:
            v["10 course_set"].append((c.course_id, n))
    return v


def explain(cycle, observed, v):
    obs = _placed(observed)
    teachers = {t.teacher_id: t for t in cycle.teachers}
    running = {c.course_id for c in cycle.courses if c.ran}
    kind = {c.course_id: c.course_type for c in cycle.courses}
    ranked: dict[str, set[str]] = {}
    for p in cycle.preferences:
        ranked.setdefault(p.teacher_id, set()).add(p.course_id)

    print("\nincumbency violations:")
    for tid in v["0 incumbency"]:
        got, mine = obs.get(tid), ranked.get(tid, set())
        where = (
            "unplaced"
            if got is None
            else "a course they ranked"
            if got in mine
            else "a course they did NOT rank"
        )
        print(f"  submitted={bool(mine)!s:<5}  placed in {where}")

    print("\nonly-ranked violations:")
    for tid in v["4 only_ranked"]:
        mine, got = ranked[tid], obs[tid]
        n_running = len(mine & running)
        same_pool = any(kind[c] == kind[got] for c in mine)

        print(
            f"  ranked={len(mine)}  of which ran={n_running}  "
            f"same pool as placement={same_pool}  repeater={teachers[tid].is_repeater}"
        )


def claim_scores(cycle, rules) -> dict[tuple[str, str], int]:
    """Same scoring as the objective: round bonus + rank weight, best over rounds."""
    p1 = next(r["params"] for r in rules if r["id"] == 1)["weights"]
    p6 = next(r["params"] for r in rules if r["id"] == 6)["bonus"]
    s: dict[tuple[str, str], int] = {}
    for p in cycle.preferences:
        k = (p.teacher_id, p.course_id)
        s[k] = max(s.get(k, 0), p6[p.round_id] + p1[p.rank - 1])
    return s


def envy(cycle, rules, observed, v):
    obs = _placed(observed)
    teachers = {t.teacher_id: t for t in cycle.teachers}
    running = {c.course_id for c in cycle.courses if c.ran}
    submitters = {p.teacher_id for p in cycle.preferences}
    holders: dict[str, list[str]] = {}
    for tid, cid in obs.items():
        holders.setdefault(cid, []).append(tid)
    score = claim_scores(cycle, rules)
    INCUMBENT = 10**6  # an incumbent's claim beats any ranking

    def claim(tid, cid):
        t = teachers[tid]
        if t.is_repeater and t.incumbent_course_id == cid:
            return INCUMBENT
        return score.get((tid, cid), 0)  # 0 = didn't rank it

    cases = set(v["4 only_ranked"]) | set(v["0 incumbency"])

    def holder_kind(h):
        if h in cases:
            return "one of the 17"
        if h not in submitters:
            return "non-submitter"
        return "ranked it lower"

    print("\nonly-ranked violations (wanted = ranked & running):")
    kinds = Counter()
    for tid in v["4 only_ranked"]:
        wanted = [c for (t, c) in score if t == tid and c in running]
        # per wanted course: the holders whose claim to it is weaker than tid's
        weaker = {
            c: [h for h in holders.get(c, []) if claim(h, c) < claim(tid, c)]
            for c in wanted
        }
        envious = [c for c in wanted if weaker[c]]
        print(
            f"  wanted={len(wanted)}  held by someone with a WEAKER claim={len(envious)}"
        )
        kinds.update(holder_kind(h) for hs in weaker.values() for h in hs)

    print("\nincumbency violations (wanted = prior course):")
    for tid in v["0 incumbency"]:
        c = teachers[tid].incumbent_course_id
        hs = holders.get(c, [])
        kinds_of_holders = sorted(
            "incumbent"
            if claim(h, c) == INCUMBENT
            else "ranked it"
            if claim(h, c) > 0
            else "did NOT rank it"
            for h in hs
        )
        print(f"  prior course now held by: {kinds_of_holders}")

    print("\nweaker-claim holders by kind:", dict(kinds))

    swaps = sum(
        1
        for i in v["4 only_ranked"]
        for j in v["4 only_ranked"]
        if i < j and score.get((j, obs[i]), 0) > 0 and score.get((i, obs[j]), 0) > 0
    )
    print("swap pairs among the 12 (each holds a course the other ranked):", swaps)


def score_observed(cycle, rules, observed, exclude=frozenset(), time_limit=30.0):
    ctx = build_model(cycle, rules, exclude)
    force_observed(ctx, observed)
    solver, code = _solve(ctx.model, time_limit)
    if code in SOLVED:
        return "feasible", round(solver.objective_value)
    # Which hard rule does the real allocation break?
    hard_ids = [
        r["id"] for r in rules if r["class"] == "hard" and r["id"] not in exclude
    ]
    broken = []
    for i in hard_ids:
        c2 = build_model(cycle, rules, exclude | {i})
        force_observed(c2, observed)
        if _solve(c2.model, time_limit)[1] in SOLVED:
            broken.append(i)
    return "infeasible", broken


def main() -> None:
    config = load_config(DEFAULT_CONFIG)
    rules = load_rules(Path("config/rules-2027.yaml"))
    derived = out_path(config, "derived")
    cycle = load_cycle_from_config(config, CYCLE)
    observed = load_observed_placements(derived / "placements.csv", cycle)

    # Repeaters' self-reported prior course vs the 2026 placement records.
    pl = read_csv(derived / "placements.csv")
    pl_2026 = pl[pl["cycle"] == "2026"]
    placed_2026 = dict(zip(pl_2026["teacher_id"], pl_2026["course_id"]))
    lineage = read_lineage(out_path(config, "key") / "course_lineage.csv", {CYCLE})
    obs = _placed(observed)

    tally = Counter()
    for t in cycle.teachers:
        if not t.is_repeater:
            continue
        rec = placed_2026.get(t.teacher_id)
        if rec is None:
            tally["no 2026 placement on record"] += 1
        elif rec == t.prior_course_id:
            tally["self-report agrees with records"] += 1
        else:
            followed = obs.get(t.teacher_id) == lineage.get(rec)
            tally[f"DISAGREE; 2027 placement follows records={followed}"] += 1
    print(dict(tally))

    print(score_observed(cycle, rules, observed, exclude=frozenset(), time_limit=30.0))

    print(
        "observed teachers matched to cycle:",
        len(set(obs) & {t.teacher_id for t in cycle.teachers}),
        "of",
        len(observed),
    )
    v = violations(cycle, observed)
    for rule, items in v.items():
        print(f"{rule:<16} {len(items)}")
    if v["9 capacity"]:
        print(
            "  sponsors per violating course:", Counter(n for _, n in v["9 capacity"])
        )
    explain(cycle, observed, v)
    envy(cycle, rules, observed, v)


if __name__ == "__main__":
    main()
