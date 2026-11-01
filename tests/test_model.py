import json
from dataclasses import replace

from stable_sponsors import model
from stable_sponsors.model import (
    active_rules,
    check_feasibility,
    diagnose,
    load_hard_rules,
)
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
