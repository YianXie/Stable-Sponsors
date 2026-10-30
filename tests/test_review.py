import json
from dataclasses import replace

import pytest

from stable_sponsors import model, review
from stable_sponsors.data import Preference, Teacher
from stable_sponsors.review import (
    MISMATCH_CATEGORIES,
    claim_scores,
    classify_mismatches,
    load_office,
    pinned_repeaters,
    score,
)
from tests.conftest import RULES_PATH, make_private_root


def test_score_cross_tab():
    model = {"T1": "A", "T2": "A", "T3": "B", "T4": None, "T5": None, "T6": "B"}
    det = {"T1": True, "T2": True, "T3": False, "T4": True, "T5": True, "T6": False}
    office = {"T1": "A", "T2": "B", "T3": "B", "T5": "A"}  # T4, T6 unplaced by office
    s = score(model, det, office, {"T6"})
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
    assert s["office_unplaced_by_model"] == {
        "unplaced": 1,  # T4
        "placed, determined": 0,
        "placed, contested submitter": 1,  # T6
        "placed, contested non-submitter": 0,
    }
    assert s["model_courses_run"] == 2  # A, B
    assert s["office_courses_run"] == 2  # A, B
    assert s["office_only_courses"] == 0
    assert s["model_only_courses"] == 0
    assert s["share_of_all"] == pytest.approx(2 / 6)
    assert s["share_of_determined"] == pytest.approx(2 / 4)


def test_office_teacher_missing_from_run_is_reported_not_scored():
    s = score({"T1": "A"}, {"T1": True}, {"T1": "A", "T9": "A"}, set())
    assert s["office_not_in_run"] == ["T9"]
    assert s["teachers"] == 1


def test_courses_run_counts_distinct_staffed_courses():
    s = score(
        {"T1": "A", "T2": "A", "T3": None},
        {"T1": True, "T2": True, "T3": True},
        {"T1": "A", "T2": "B", "T9": "C"},  # T9 not in run, but C still ran
        set(),
    )
    assert s["model_courses_run"] == 1
    assert s["office_courses_run"] == 3
    assert s["office_only_courses"] == 2  # B, C
    assert s["model_only_courses"] == 0


def test_courses_run_by_only_one_side():
    s = score(
        {"T1": "A", "T2": "D", "T3": "E"},
        {"T1": True, "T2": True, "T3": False},
        {"T1": "A", "T2": "B"},
        set(),
    )
    assert s["office_only_courses"] == 1  # B
    assert s["model_only_courses"] == 2  # D, E


def test_office_unplaced_split_by_model_outcome():
    s = score(
        {"T1": None, "T2": "A", "T3": "A", "T4": "B", "T5": "B"},
        {"T1": False, "T2": True, "T3": False, "T4": False, "T5": True},
        {"T5": "B"},  # only T5 placed by office, so it is left out
        {"T1", "T3"},
    )
    assert s["office_unplaced_by_model"] == {
        "unplaced": 1,  # T1, even though a contested submitter
        "placed, determined": 1,  # T2
        "placed, contested submitter": 1,  # T3
        "placed, contested non-submitter": 1,  # T4
    }


def test_pinned_repeaters(toy_cycle):
    assert pinned_repeaters(toy_cycle.teachers, []) == {
        "T1000": "INTL-1",
        "T1004": "INTL-2",
    }
    assert pinned_repeaters(toy_cycle.teachers, [0]) == {}  # incumbency rule excluded


def test_repeater_with_discontinued_course_is_not_pinned(toy_cycle):
    teachers = tuple(
        replace(t, incumbent_course_id=None) if t.teacher_id == "T1000" else t
        for t in toy_cycle.teachers
    )
    assert pinned_repeaters(teachers, []) == {"T1004": "INTL-2"}


def test_mismatched_inputs_raise():
    with pytest.raises(ValueError):
        score({"T1": "A"}, {"T2": True}, {}, set())


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
    cfg = make_private_root(tmp_path)
    root = tmp_path / "private"

    model.main(["--config", str(cfg), "--rules", str(RULES_PATH), "--optimize"])
    review.main(["--config", str(cfg)])

    (out,) = (root / "runs").glob("*_reproduction.json")
    s = json.loads(out.read_text())
    assert s["teachers"] == 5
    assert s["repeaters"] == 2
    assert s["repeaters_pinned"] == 2
    # repeaters are determined, and the model places them where the office did
    assert {"T1000", "T1004"} <= set(s["cells"]["determined_match"])
    cats = s["determined_mismatch_categories"]
    assert list(cats) == list(MISMATCH_CATEGORIES)
    assert (
        sorted(t for ids in cats.values() for t in ids)
        == s["cells"]["determined_mismatch"]
    )


RULES = [
    {"id": 1, "params": {"weights": [7, 6, 5]}},
    {"id": 6, "params": {"bonus": {"intl_r1": 20, "intl_r2": 10, "sg": 0}}},
]


def pref(tid, round_id, rank, cid):
    return Preference(2027, tid, round_id, rank, cid, None)


def teacher(tid, incumbent=None):
    return Teacher(
        2027, tid, incumbent is not None, incumbent, incumbent,
        False, False, False, None,
    )  # fmt: skip


def test_claim_scores_take_best_rank_and_best_round_separately():
    prefs = (pref("T1", "intl_r1", 3, "A"), pref("T1", "sg", 1, "A"))
    assert claim_scores(prefs, RULES, []) == {("T1", "A"): 7 + 20}
    assert claim_scores(prefs, RULES, [6]) == {("T1", "A"): 7}
    assert claim_scores(prefs, RULES, [1, 6]) == {("T1", "A"): 0}


def test_classify_mismatches_one_teacher_per_category():
    teachers = tuple(map(teacher, ["T2", "T3", "T4", "T5", "T6", "T7"])) + (
        teacher("T1", incumbent="A"),
    )
    prefs = (
        pref("T2", "intl_r1", 1, "B"),  # office puts T2 in unranked C
        pref(
            "T3", "intl_r1", 1, "D"
        ),  # wanted D, the office gave it to non-submitter T4
        pref("T3", "intl_r1", 2, "E"),
        pref("T5", "intl_r1", 1, "F"),
        pref("T6", "intl_r1", 1, "G"),
        pref("T6", "intl_r1", 2, "H"),
    )
    model = {
        "T1": "A",
        "T2": "B",
        "T3": "D",
        "T4": None,
        "T5": None,
        "T6": "G",
        "T7": "C",
    }
    office = {
        "T1": "B",
        "T2": "C",
        "T3": "E",
        "T4": "D",
        "T5": "F",
        "T6": "H",
        "T7": "E",
    }
    out = classify_mismatches(
        sorted(model), model, office, teachers, claim_scores(prefs, RULES, [])
    )
    assert list(out) == list(MISMATCH_CATEGORIES)
    assert out == {
        "repeater not on old course": ["T1"],
        "placed in unranked course": ["T2"],
        "non-submitter ahead of submitter": ["T3", "T4"],  # both sides of the pair
        "unexplained tie": ["T7"],  # non-submitter: C and E both score 0
        "other": [
            "T5",
            "T6",
        ],  # T5: model leaves out a rank-1 placement; T6: rank 2 vs 1
    }


def test_incumbent_repeater_is_not_ahead_of_a_submitter():
    teachers = (teacher("T1", incumbent="A"), teacher("T2"))
    prefs = (pref("T2", "intl_r1", 1, "A"), pref("T2", "intl_r1", 2, "B"))
    out = classify_mismatches(
        ["T2"],
        {"T1": "A", "T2": "A"},
        {"T1": "A", "T2": "B"},
        teachers,
        claim_scores(prefs, RULES, []),
    )
    assert out["other"] == ["T2"]
