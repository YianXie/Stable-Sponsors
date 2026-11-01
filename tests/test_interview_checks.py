from dataclasses import replace

from stable_sponsors.interview_checks import (
    fallback_origin,
    preferring_rankers,
    rankers_at_placement,
    ranking_genders,
    repeater_status,
    staffable,
)


def test_origin_all_unrun():
    assert fallback_origin({"A", "B"}, ran={"C"}) == "all_unrun"


def test_origin_some_unrun():
    assert fallback_origin({"A", "B"}, ran={"A"}) == "some_unrun"


def test_origin_none_unrun():
    assert fallback_origin({"A"}, ran={"A"}) == "none_unrun"


def test_two_male_rankers_cannot_staff_one_one_course():
    assert not staffable([("T1", "male"), ("T2", "male")], 1, 1, 2)


def test_male_and_female_rankers_staff_one_one_course():
    assert staffable([("T1", "male"), ("T2", "female")], 1, 1, 2)


def test_unknown_gender_is_wildcard():
    assert staffable([("T1", "male"), ("T2", None)], 1, 1, 2)


def test_one_ranker_ranking_twice_is_one_teacher():
    assert not staffable([("T1", "male"), ("T1", "female")], 1, 1, 2)


def test_teacher_with_conflicting_labels_fills_either_slot():
    # T2 ranked this course under both labels: their gender is unknown, not "both"
    assert staffable([("T1", "male"), ("T2", "male"), ("T2", "female")], 1, 1, 2)


def test_known_label_beats_a_missing_one():
    # T1 ranked this course in two rounds, one labelled and one not: still a known male
    assert not staffable([("T1", "male"), ("T1", None), ("T2", "male")], 1, 1, 2)


def test_too_few_teachers_is_not_staffable_even_if_slots_are_covered():
    assert not staffable([("T1", "male"), ("T2", "female")], 1, 1, 3)


def test_repeater_status_toy(toy_cycle):
    s = repeater_status(toy_cycle)
    assert s[("incumbent_ran", False)] == 2 and s[("incumbent_unrun", False)] == 0


def test_repeater_status_counts_unrun_and_discontinued(toy_cycle):
    teachers = tuple(
        replace(t, incumbent_course_id="INTL-3")  # INTL-3 did not run
        if t.teacher_id == "T1000"
        else replace(t, incumbent_course_id=None)  # discontinued
        if t.teacher_id == "T1004"
        else t
        for t in toy_cycle.teachers
    )
    s = repeater_status(replace(toy_cycle, teachers=teachers))
    assert s[("incumbent_unrun", False)] == 1
    assert s[("discontinued", False)] == 1
    assert s[("incumbent_ran", False)] == 0


def test_repeater_status_marks_submitters(toy_cycle):
    # T1001 is not a repeater in the toy; make them one who also submitted
    teachers = tuple(
        replace(
            t, is_repeater=True, prior_course_id="INTL-1", incumbent_course_id="INTL-1"
        )
        if t.teacher_id == "T1001"
        else t
        for t in toy_cycle.teachers
    )
    s = repeater_status(replace(toy_cycle, teachers=teachers))
    assert s[("incumbent_ran", True)] == 1


def test_preferring_rankers_keeps_those_who_would_gain():
    prefs = [
        ("T1", "X", "male"),  # unplaced: any ranked course beats that
        ("T2", "X", None),  # scores more on X than on A
        ("T3", "X", "male"),  # scores less on X than on A
        ("T4", "X", None),  # repeater on their incumbent course: not a candidate
        ("T5", "A", None),  # A ran
    ]
    placed = {"T2": "A", "T3": "A", "T4": "B", "T5": "A"}
    scores = {
        ("T1", "X"): 5,
        ("T2", "X"): 5,
        ("T2", "A"): 3,
        ("T3", "X"): 3,
        ("T3", "A"): 5,
        ("T4", "X"): 7,
    }
    out = preferring_rankers(prefs, placed, scores, {"T4": "B"}, unrun={"X"})
    assert out == {"X": [("T1", "male"), ("T2", None)]}


def test_ranking_genders_use_the_teacher_not_the_label_on_that_course(toy_cycle):
    # toy: T1001 is male (params); their SING-1 ranking carries no slot label
    assert ("T1001", "SING-1", "male") in ranking_genders(toy_cycle)


def test_ranking_genders_leave_an_unknown_teacher_unknown(toy_cycle):
    teachers = tuple(
        replace(t, gender=None) if t.teacher_id == "T1001" else t
        for t in toy_cycle.teachers
    )
    rows = ranking_genders(replace(toy_cycle, teachers=teachers))
    # the INTL-1 ranking is labelled male, but gender comes only from the teacher's row
    assert ("T1001", "INTL-1", None) in rows


def test_rankers_at_placement_counts_rankers_of_the_office_course():
    prefs = [("T2", "A"), ("T3", "A"), ("T4", "B")]
    placed = {"T1": "A", "T5": "C"}
    assert rankers_at_placement(["T1", "T5"], placed, prefs) == [0, 2]
