from stable_sponsors.course_set_check import gender_staffable, unrun_demand


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
