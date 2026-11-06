"""Metrics of one allocation, and how far two allocations agree (RQ2).

Everything works on assignments passed in (teacher_id -> course_id, None = unplaced); this module
never reads the office's placements itself. A course counts as running iff the assignment puts at
least one sponsor in it, never from the model's y.
"""

from collections import Counter, defaultdict
from statistics import fmean

from stable_sponsors.data import ROUNDS, Cycle, Preference
from stable_sponsors.review import Assignment
from stable_sponsors.serial import submitters

ROUND_1 = ("intl_r1", "sg")  # placed from one of these rounds = no wait for Round 2

__all__ = ["Assignment", "agreement", "allocation_metrics", "summarise"]


def _courses_run(assignment: Assignment) -> set[str]:
    """Courses with at least one sponsor in `assignment`."""
    return {cid for cid in assignment.values() if cid is not None}


def _label(rows: list[Preference]) -> str:
    """rank_hist label of a placed, ranked pair, from its best preference row.

    The best row is the one with the highest bonus + weight. Rows are compared by round (order of
    ROUNDS) and then rank, which picks that row whenever each round's bonus beats the next round's
    by more than the weight range, as in rules-2027 and v3.1 (20/10/0 against weights 7..1).
    """
    best = min(rows, key=lambda p: (ROUNDS.index(p.round_id), p.rank))
    return f"{best.round_id}:{best.rank}"


def allocation_metrics(
    cycle: Cycle,
    assignment: Assignment,
    scores: dict[tuple[str, str], int],
    population: list[str],
) -> dict:
    """Score, coverage, worst-off and rank metrics of `assignment`.

    `scores` is objectives.preference_scores and `population` objectives.leximin_population.
    A teacher missing from `assignment` counts as unplaced; unplaced or unranked scores 0.
    """
    rows: dict[tuple[str, str], list[Preference]] = defaultdict(list)
    for p in cycle.preferences:
        rows[(p.teacher_id, p.course_id)].append(p)
    incumbent = {t.teacher_id: t.incumbent_course_id for t in cycle.teachers}
    kind = {c.course_id: c.course_type for c in cycle.courses}
    placed = {tid: cid for tid, cid in assignment.items() if cid is not None}
    running = _courses_run(placed)

    # Unplaced teachers look up (tid, None), which is never a key, so they score 0.
    def score(tid: str) -> int:
        return scores.get((tid, placed.get(tid)), 0)

    hist: Counter[str] = Counter()
    unranked = round1 = 0
    for tid in submitters(cycle):
        cid = placed.get(tid)
        if cid is None:
            hist["unplaced"] += 1
        elif (tid, cid) in rows:
            hist[_label(rows[(tid, cid)])] += 1
            round1 += any(p.round_id in ROUND_1 for p in rows[(tid, cid)])
        else:
            hist["unranked"] += 1
            # A repeater kept on their own incumbent course didn't need to rank it.
            unranked += cid != incumbent.get(tid)

    worst = [score(tid) for tid in population]
    worst_score = min(worst, default=None)
    return {
        "score": sum(score(tid) for tid in placed),
        "placed": len(placed),
        "submitters_unplaced": hist["unplaced"],
        "courses_run": len(running),
        "courses_run_intl": sum(kind[cid] == "intl" for cid in running),
        "courses_run_sg": sum(kind[cid] == "sg" for cid in running),
        "unranked_placements": unranked,
        "worst_score": worst_score,
        "at_worst": worst.count(worst_score),
        "round1_placed": round1,
        "rank_hist": dict(sorted(hist.items())),
    }


def agreement(a: Assignment, b: Assignment) -> dict:
    """How many teachers two assignments place alike, and which courses run in each.

    Over the union of teachers; one missing from an assignment counts as unplaced there, so
    unplaced in both is the same placement.
    """
    run_a, run_b = _courses_run(a), _courses_run(b)
    return {
        "same_placement": sum(a.get(tid) == b.get(tid) for tid in a.keys() | b.keys()),
        "courses_both": len(run_a & run_b),
        "courses_only_a": len(run_a - run_b),
        "courses_only_b": len(run_b - run_a),
    }


def _is_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _stats(values: list[float]) -> dict:
    return {"mean": fmean(values), "min": min(values), "max": max(values)}


def summarise(rows: list[dict]) -> dict:
    """Mean, min and max of each numeric key over `rows` (e.g. one row per serial order).

    A key is summarised only if it is a number in every row (worst_score is None with an empty
    population). rank_hist is summarised per label, a label missing from a row counting as 0.
    """
    out: dict = {}
    for key in dict.fromkeys(k for r in rows for k in r):
        values = [r.get(key) for r in rows]
        if key != "rank_hist" and all(_is_number(v) for v in values):
            out[key] = _stats(values)
    if any("rank_hist" in r for r in rows):
        hists = [r.get("rank_hist", {}) for r in rows]
        labels = sorted({label for h in hists for label in h})
        out["rank_hist"] = {
            label: _stats([h.get(label, 0) for h in hists]) for label in labels
        }
    return out
