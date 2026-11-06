import json
import re

import pytest

from stable_sponsors import rq2
from stable_sponsors.model import load_rules, solve_optimal
from stable_sponsors.objectives import OBJECTIVES, StagedResult
from stable_sponsors.rq2 import main
from tests.conftest import RULES_PATH, make_private_root


def _run(tmp_path, *extra):
    cfg = make_private_root(tmp_path)
    main(
        [
            "--config",
            str(cfg),
            "--rules",
            str(RULES_PATH),
            "--orders",
            "2",
            "--time-limit",
            "10",
            *extra,
        ]
    )
    return json.loads(
        next((tmp_path / "private" / "runs").glob("*_rq2_run.json")).read_text()
    )


def test_run_has_every_objective_and_rsd(tmp_path, toy_cycle):
    rep = _run(tmp_path)
    assert set(rep["objectives"]) == set(OBJECTIVES) and rep["rsd"]["orders"] == 2
    assert rep["office"]["metrics"]["placed"] == 5
    assert (
        rep["objectives"]["utilitarian"]["result"]["score"]
        == solve_optimal(toy_cycle, load_rules(RULES_PATH)).primary_value
    )


def test_run_records_provenance(tmp_path):
    p = _run(tmp_path)["provenance"]
    assert len(p["inputs_sha256"]) == 64 and "commit" in p and "dirty" in p


def test_determinacy_flag_adds_review(tmp_path):
    u = _run(tmp_path, "--determinacy")["objectives"]["utilitarian"]
    assert "determined_match" in u["review"] and len(u["determinacy"]) == 5


def test_review_ignores_office_unplaced_teachers(tmp_path):
    # Drop the office's SING-1 row, so T1002 is unplaced by the office.
    cfg = make_private_root(tmp_path)
    placements = tmp_path / "private" / "derived" / "2027" / "placements.csv"
    lines = placements.read_text().splitlines(keepends=True)
    placements.write_text("".join(ln for ln in lines if "SING-1" not in ln))
    main(
        ["--config", str(cfg), "--rules", str(RULES_PATH), "--orders", "1"]
        + ["--time-limit", "10", "--determinacy"]
    )
    rep = json.loads(
        next((tmp_path / "private" / "runs").glob("*_rq2_run.json")).read_text()
    )
    office = rep["office"]["metrics"]
    assert office["placed"] == 4 and office["courses_run"] == 2
    for entry in rep["objectives"].values():
        assert entry["review"]["office_courses_run"] == office["courses_run"]
        assert entry["review"]["office_placed"] == 4


def test_console_has_no_teacher_ids(tmp_path, capsys):
    _run(tmp_path, "--determinacy")
    assert not re.search(r"\bT\d{3,4}\b", capsys.readouterr().out)


def test_excluding_a_score_rule_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        _run(tmp_path, "--exclude", "6")


def test_objective_not_proven_optimal_is_no_verdict(tmp_path, monkeypatch, capsys):
    real = rq2.solve_objective

    def timed_out(cycle, rules, name, *args):
        r = real(cycle, rules, name, *args)
        if name != "coverage":
            return r
        return StagedResult(name, "not_proven", (), None, r.wall_time, None)

    monkeypatch.setattr(rq2, "solve_objective", timed_out)
    cov = _run(tmp_path, "--determinacy")["objectives"]["coverage"]
    assert cov["metrics"] is None and "determinacy" not in cov
    # Every body row of both tables shows the status in the coverage column, not a number.
    rows = [
        r.split(" | ") for r in capsys.readouterr().out.splitlines() if r[:2] == "| "
    ]
    col = rows[0].index("coverage")
    body = [r[col] for r in rows if r[0] not in ("| metric", "| rank_hist")]
    assert body and set(body) == {"not_proven"}
