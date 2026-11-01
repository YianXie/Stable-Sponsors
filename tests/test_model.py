import json
from dataclasses import replace

from ortools.sat.python import cp_model

from stable_sponsors import model
from stable_sponsors.data import Course, Cycle, Preference, Teacher
from stable_sponsors.model import (
    active_rules,
    check_feasibility,
    determinacy,
    diagnose,
    load_hard_rules,
    load_rules,
    min_fallbacks,
    objective_expr,
    placement_costs,
    solve_optimal,
)
from stable_sponsors.rules.context import build_ctx
from tests.conftest import RULES_PATH, make_private_root

# Hard rules only: feasibility is a property of the constraints, not the objective.
RULES = load_hard_rules(RULES_PATH)


def test_contradicted_rules_inactive():
    rules = [{"id": 10, "class": "hard", "status": "contradicted", "params": {}}]
    assert active_rules(rules) == []


def test_toy_is_feasible(toy_cycle):
    assert check_feasibility(toy_cycle, RULES).status == "feasible"


def test_exclude_skips_rule(toy_cycle):
    assert (
        5
        not in check_feasibility(toy_cycle, RULES, exclude=frozenset({5})).rules_applied
    )


def test_assignment_respects_incumbency(toy_cycle):
    assignment = check_feasibility(toy_cycle, RULES).assignment
    assert assignment is not None
    assert assignment["T1000"] == "INTL-1"


def test_diagnose_finds_planted_conflict(toy_cycle):
    # Cap INTL-1 at 0 sponsors. That conflicts with T1000's incumbency.
    # Without rule 5, whose upper bound would hold the cap even with rule 9 dropped.
    bad = replace(
        toy_cycle,
        courses=tuple(
            replace(c, min_sponsors=0, max_sponsors=0, male_slots=0, female_slots=0)
            if c.course_id == "INTL-1"
            else c
            for c in toy_cycle.courses
        ),
    )
    d = diagnose(bad, [r for r in RULES if r["id"] != 5])
    assert d["leave_one_out"][0] == "feasible"  # drop incumbency → fixed
    assert d["leave_one_out"][9] == "feasible"  # drop capacity → fixed


def _run_report(tmp_path, *args: str) -> dict:
    model.main(
        [
            "--config",
            str(tmp_path / "pseudonymize.yaml"),
            "--rules",
            str(RULES_PATH),
            *args,
        ]
    )
    (path,) = (tmp_path / "private" / "runs").glob(f"*{model.RUN_SUFFIX}.json")
    return json.loads(path.read_text())


def test_cli_records_lineage_on_by_default(tmp_path):
    make_private_root(tmp_path)
    assert _run_report(tmp_path)["lineage"] is True


def test_cli_no_lineage_needs_no_lineage_file(tmp_path):
    make_private_root(tmp_path, lineage=False)
    report = _run_report(tmp_path, "--no-lineage")
    assert report["lineage"] is False
    assert report["feasibility_result"]["assignment"]["T1000"] == "INTL-1"


def test_cli_time_limit_reaches_determinacy(tmp_path, monkeypatch):
    make_private_root(tmp_path)
    seen = {}
    real = model.determinacy

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(model, "determinacy", spy)
    _run_report(tmp_path, "--optimize", "--time-limit", "42")
    assert seen["time_limit"] == 42.0


# ---- fallback placements (rule 11): small inline cycles ----


def _teacher(tid: str) -> Teacher:
    return Teacher(2027, tid, False, None, None, True, False, False, None)


def _course(cid: str, lo: int = 2, hi: int = 2) -> Course:
    return Course(2027, cid, "intl", True, True, None, (), lo, hi, 0, 0)


def _cycle(prefs: list[tuple], courses: list[Course]) -> Cycle:
    """Each pref is (teacher, course, rank), optionally followed by a round (default intl_r1)."""
    tids = sorted({p[0] for p in prefs})
    return Cycle(
        tuple(_teacher(t) for t in tids),
        tuple(courses),
        tuple(
            Preference(2027, p[0], p[3] if len(p) > 3 else "intl_r1", p[2], p[1], None)
            for p in prefs
        ),
    )


def _rules(*without: int) -> list[dict]:
    return [r for r in load_rules(RULES_PATH) if r["id"] not in without]


def _short_course_cycle() -> Cycle:
    # T1 wants A; T2's only choice B has no other rankers, so T2 can only help by filling A.
    # T2 ranks B second, so A is the higher-scoring course to run.
    return _cycle([("T1", "A", 1), ("T2", "B", 2)], [_course("A"), _course("B")])


def test_fallback_lets_short_course_run():
    r = solve_optimal(_short_course_cycle(), _rules(), exclude=frozenset({4}))
    assert r.assignment == {"T1": "A", "T2": "A"}


def test_short_course_does_not_run_with_rule_4_on():
    r = solve_optimal(_short_course_cycle(), _rules())
    assert r.assignment == {"T1": None, "T2": None}


def test_fallback_never_used_when_it_gains_nothing():
    # T3 and T4 could staff C, which nobody ranked, at no cost to anyone's preference score.
    cycle = _cycle(
        [("T1", "A", 1), ("T2", "A", 1), ("T3", "D", 1), ("T4", "D", 1)],
        [_course("A"), _course("C"), _course("D", 3, 3)],
    )
    r = solve_optimal(cycle, _rules(), exclude=frozenset({4}))
    assert r.assignment == {"T1": "A", "T2": "A", "T3": None, "T4": None}


def test_fallback_not_used_when_a_ranked_seat_is_available():
    # T2 could fill A unranked, but T3 ranked A: the ranked sponsor takes the seat.
    cycle = _cycle(
        [("T1", "A", 1), ("T2", "D", 1), ("T3", "A", 7)],
        [_course("A"), _course("D", 3, 3)],
    )
    r = solve_optimal(cycle, _rules(), exclude=frozenset({4}))
    assert r.assignment == {"T1": "A", "T2": None, "T3": "A"}


def _costly_fallback_cycle() -> Cycle:
    # T1's rank 7 in the Singapore round scores 1 point, and needs two fallback placements to run.
    # Only K makes 1 point of preference score worth 2 fallbacks. D can't run with 3 teachers.
    return _cycle(
        [("T1", "A", 7, "sg"), ("T2", "D", 1), ("T3", "D", 1)],
        [_course("A", 3, 3), _course("D", 4, 4)],
    )


def test_secondary_never_outweighs_primary():
    cycle = _costly_fallback_cycle()
    on = solve_optimal(cycle, _rules(), exclude=frozenset({4}))
    off = solve_optimal(cycle, _rules(11), exclude=frozenset({4}))
    assert on.primary_value == off.value
    assert on.assignment == {"T1": "A", "T2": "A", "T3": "A"}


def test_value_is_the_plain_score_without_secondary_terms():
    r = solve_optimal(_short_course_cycle(), _rules(11), exclude=frozenset({4}))
    assert r.value == r.primary_value


def test_objective_expr_is_k_times_primary_plus_secondary():
    ctx = build_ctx(_costly_fallback_cycle())  # 3 teachers, so K = 4
    ctx.objective.append(5 * ctx.x[("T1", "A")])
    ctx.secondary.append(-ctx.x[("T2", "A")])
    ctx.model.add(ctx.x[("T1", "A")] == 1)
    ctx.model.add(ctx.x[("T2", "A")] == 1)
    ctx.model.maximize(objective_expr(ctx))
    solver = cp_model.CpSolver()
    solver.solve(ctx.model)
    assert solver.objective_value == 4 * 5 - 1


def test_objective_expr_is_plain_without_secondary_terms():
    ctx = build_ctx(_costly_fallback_cycle())
    ctx.objective.append(5 * ctx.x[("T1", "A")])
    ctx.model.add(ctx.x[("T1", "A")] == 1)
    ctx.model.maximize(objective_expr(ctx))
    solver = cp_model.CpSolver()
    solver.solve(ctx.model)
    assert solver.objective_value == 5


def test_determinacy_with_secondary_runs():
    det = determinacy(_short_course_cycle(), _rules(), exclude=frozenset({4}))
    assert det == {"T1": True, "T2": True}


def test_determinacy_with_secondary_sees_a_tie_between_fallbacks():
    # T2 and T3 tie for the one fallback seat on A: neither placement is determined.
    cycle = _cycle(
        [("T1", "A", 1), ("T2", "D", 1), ("T3", "D", 1)],
        [_course("A"), _course("D", 4, 4)],
    )
    det = determinacy(cycle, _rules(), exclude=frozenset({4}))
    assert det["T1"] is True
    assert det["T2"] is False
    assert det["T3"] is False


def test_exclude_applies_to_priority_rules(tmp_path):
    make_private_root(tmp_path)
    report = _run_report(tmp_path, "--optimize", "--exclude", "11")
    assert 11 in report["excluded"]


def test_excluding_a_priority_rule_changes_the_objective(tmp_path, toy_cycle):
    make_private_root(tmp_path)
    report = _run_report(tmp_path, "--optimize", "--exclude", "6")  # no round bonuses
    with_bonuses = solve_optimal(toy_cycle, load_rules(RULES_PATH))
    assert report["optimal_result"]["primary_value"] < with_bonuses.primary_value


def test_excluding_a_deferred_rule_is_reported_as_off(tmp_path, capsys):
    make_private_root(tmp_path)
    report = _run_report(tmp_path, "--exclude", "2")
    assert report["excluded"] == []
    assert "already off" in capsys.readouterr().out


def test_placement_costs_measure_lost_preference_score():
    # A and B each run with their two rankers, 2 x 27 points each. C has no rankers.
    cycle = _cycle(
        [("T1", "A", 1), ("T2", "A", 1), ("T3", "B", 1), ("T4", "B", 1)],
        [_course("A"), _course("B"), _course("C")],
    )
    out = placement_costs(
        cycle, _rules(), [("T1", "A"), ("T1", "C")], exclude=frozenset({4})
    )
    assert out[("T1", "A")] == 0
    # T1 on C stops A running, and C needs a second sponsor from A (T2): both lose 27
    assert out[("T1", "C")] == 54


def test_placement_cost_ignores_the_fallback_penalty():
    # T2 on A is a fallback: it costs nothing in preference score, though secondary falls by 1.
    cycle = _short_course_cycle()
    assert placement_costs(cycle, _rules(), [("T2", "A")], exclude=frozenset({4})) == {
        ("T2", "A"): 0
    }


def test_placement_cost_is_none_when_hard_rules_forbid_it():
    # rule 4 on: an unranked course is out of reach in every solution
    cycle = _short_course_cycle()
    assert placement_costs(cycle, _rules(), [("T2", "A")]) == {("T2", "A"): None}


def test_min_fallbacks_counts_what_the_hard_rules_force():
    assert min_fallbacks(_short_course_cycle(), _rules(), frozenset({4})) == 0
    # With the course set fixed to A running, 3 seats and 1 ranker force 2 fallbacks.
    cycle = _cycle(
        [("T1", "A", 7, "sg"), ("T2", "D", 1), ("T3", "D", 1)],
        [_course("A", 3, 3), replace(_course("D", 4, 4), ran=False)],
    )
    rule_10 = {"id": 10, "class": "hard", "status": "assumed", "params": {}}
    assert min_fallbacks(cycle, _rules() + [rule_10], frozenset({4})) == 2
