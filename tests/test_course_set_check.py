import pandas as pd

from stable_sponsors.course_set_check import gender_staffable, main, unrun_demand
from tests.conftest import make_private_root


def test_only_unplaced_teachers_and_unrun_courses_count():
    prefs = [
        ("T1", "intl_r1", 1, "X"),  # unplaced, unrun -> counts
        ("T1", "intl_r1", 2, "A"),  # unplaced, course ran -> ignored
        ("T2", "sg", 3, "X"),  # unplaced, unrun -> counts
        ("T3", "intl_r1", 1, "X"),  # placed -> ignored
        ("T2", "intl_r2", 1, "Y"),  # unplaced, unrun -> counts
    ]
    out = unrun_demand({"T1", "T2"}, prefs, {"X", "Y"})
    assert out == {
        "X": [("T1", "intl_r1", 1), ("T2", "sg", 3)],
        "Y": [("T2", "intl_r2", 1)],
    }


def test_no_demand_returns_empty():
    assert unrun_demand({"T1"}, [("T1", "intl_r1", 1, "A")], {"X"}) == {}


def test_gender_staffable_needs_one_of_each_label():
    prefs = [
        ("T1", "X", "male"),  # X: two male labels
        ("T2", "X", "male"),
        ("T1", "Y", "male"),  # Y: one of each
        ("T3", "Y", "female"),
        ("T4", "Z", "female"),  # placed teacher, doesn't count
        ("T1", "Z", "male"),
        ("T2", "Z", "male"),
    ]
    out = gender_staffable(
        {"T1", "T2", "T3"}, prefs, {"X", "Y", "Z"}, {"X": 2, "Y": 2, "Z": 2}
    )
    assert out == {"X": False, "Y": True, "Z": False}


def _toy_with_unplaced_rankers(tmp_path):
    """T1001 and T1002 unplaced, both ranking INTL-3, which did not run."""
    cfg = make_private_root(tmp_path)
    derived = tmp_path / "private" / "derived"
    placements = pd.read_csv(derived / "placements.csv", skipinitialspace=True)
    placements.columns = placements.columns.str.strip()
    placements = placements[
        ~placements["teacher_id"].str.strip().isin(["T1001", "T1002"])
    ]
    placements.to_csv(derived / "placements.csv", index=False)
    with (derived / "preferences.csv").open("a") as f:
        f.write("\n2027,T1001,intl_r1,2,INTL-3,\n2027,T1002,intl_r1,2,INTL-3,\n")
    return cfg


def test_main_prints_gender_staffable_without_ids(tmp_path, capsys):
    main(["--config", str(_toy_with_unplaced_rankers(tmp_path))])
    out = capsys.readouterr().out
    assert "gender-staffable=yes" in out  # T1001 male, T1002 female
    assert "T1001" not in out


def test_list_never_shows_ids_beside_a_gender_result(tmp_path, capsys):
    main(["--config", str(_toy_with_unplaced_rankers(tmp_path)), "--list"])
    out = capsys.readouterr().out
    assert "T1001" in out
    assert "gender-staffable" not in out
