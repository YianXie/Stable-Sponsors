import json
import shutil

import pytest
import yaml

from stable_sponsors import model, reproduction
from stable_sponsors.reproduction import load_office, score
from tests.conftest import RULES_PATH, TOY_DIR


def test_score_cross_tab():
    model = {"T1": "A", "T2": "A", "T3": "B", "T4": None, "T5": None, "T6": "B"}
    det = {"T1": True, "T2": True, "T3": False, "T4": True, "T5": True, "T6": False}
    office = {"T1": "A", "T2": "B", "T3": "B", "T5": "A"}  # T4, T6 unplaced by office
    s = score(model, det, office)
    assert s["cells"]["determined_match"] == ["T1", "T4"]  # T4: both unplaced
    assert s["cells"]["determined_mismatch"] == ["T2", "T5"]
    assert s["cells"]["contested_match"] == ["T3"]
    assert s["cells"]["contested_mismatch"] == ["T6"]
    assert s["determined_match"] == 2
    assert s["determined_match_placed"] == 1
    assert s["determined_match_unplaced"] == 1
    assert s["mismatch_kinds"]["determined"] == {
        "different course": 1,
        "model unplaced, office placed": 1,
    }
    assert s["mismatch_kinds"]["contested"] == {"model placed, office unplaced": 1}
    assert s["share_of_all"] == pytest.approx(2 / 6)
    assert s["share_of_determined"] == pytest.approx(2 / 4)


def test_office_teacher_missing_from_run_is_reported_not_scored():
    s = score({"T1": "A"}, {"T1": True}, {"T1": "A", "T9": "A"})
    assert s["office_not_in_run"] == ["T9"]
    assert s["teachers"] == 1


def test_mismatched_inputs_raise():
    with pytest.raises(ValueError):
        score({"T1": "A"}, {"T2": True}, {})


def test_load_office_filters_cycle_and_status(tmp_path):
    p = tmp_path / "placements.csv"
    p.write_text(
        "cycle, course_id, sponsor_slot, teacher_id, status\n"
        "2027, A, 1, T1, assigned\n"
        "2027, A, 2, , blank_in_source\n"
        "2026, B, 1, T2, assigned\n"
    )
    assert load_office(p, 2027) == {"T1": "A"}


def test_load_office_rejects_double_placement(tmp_path):
    p = tmp_path / "placements.csv"
    p.write_text(
        "cycle,course_id,sponsor_slot,teacher_id,status\n"
        "2027,A,1,T1,assigned\n2027,B,1,T1,assigned\n"
    )
    with pytest.raises(SystemExit):
        load_office(p, 2027)


def test_reproduction_reads_the_run_model_writes(tmp_path):
    """model --optimize and reproduction must agree on the run file name and keys.

    They drifted once: model renamed its report and reproduction kept looking
    for the old one. This runs both CLIs on the toy cycle in a throwaway
    private_root laid out like the real one.
    """
    root = tmp_path / "private"
    for sub, names in {
        "derived": ("teachers", "courses", "preferences", "placements"),
        "params": ("teacher_params", "course_params"),
        "key": ("course_lineage",),
    }.items():
        (root / sub).mkdir(parents=True)
        for name in names:
            shutil.copy(TOY_DIR / f"{name}.csv", root / sub)
    (root / "raw").mkdir()
    cfg = tmp_path / "pseudonymize.yaml"
    cfg.write_text(yaml.safe_dump({"private_root": str(root), "cycles": {2027: {}}}))

    model.main(["--config", str(cfg), "--rules", str(RULES_PATH), "--optimize"])
    reproduction.main(["--config", str(cfg)])

    (out,) = (root / "runs").glob("*_reproduction.json")
    s = json.loads(out.read_text())
    assert s["teachers"] == 5
    # repeaters are determined, and the model places them where the office did
    assert {"T1000", "T1004"} <= set(s["cells"]["determined_match"])
