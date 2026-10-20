import pytest

from stable_sponsors.reproduction import load_office, score


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
