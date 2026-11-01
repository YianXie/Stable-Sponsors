import pandas as pd
import pytest

from stable_sponsors.data import load_cycle, read_csv
from stable_sponsors.params import (
    draft_course_params,
    draft_teacher_params,
    infer_gender_from_form,
    merge_keep_existing,
    refresh_columns,
    refresh_gender_source,
)
from tests.conftest import TOY_DIR

CAP = {"intl": (2, 2), "sg": (2, 2)}


@pytest.fixture
def toy():
    return {
        n: read_csv(TOY_DIR / f"{n}.csv")
        for n in ("courses", "teachers", "preferences")
    }


def test_one_row_per_course_and_teacher(toy):
    c = draft_course_params(toy["courses"], toy["preferences"], "2027", CAP)
    t = draft_teacher_params(toy["teachers"], "2027")
    assert sorted(c["course_id"]) == sorted(toy["courses"]["course_id"])
    assert sorted(t["teacher_id"]) == sorted(toy["teachers"]["teacher_id"])
    assert set(c["status"]) == {"assumed"}
    assert set(t["status"]) == {"assumed", "inferred"}  # toy: 2 repeaters have no label


def test_course_draft_is_one_one(toy):
    d = draft_course_params(toy["courses"], toy["preferences"], "2027", CAP)
    assert (d["male_slots"] == 1).all() and (d["female_slots"] == 1).all()
    assert d["source"].str.contains(r"1M/1F per M-009 \(reported\)").all()


def test_course_draft_flags_one_sided_form_evidence(toy):
    d = draft_course_params(toy["courses"], toy["preferences"], "2027", CAP)
    d = d.set_index("course_id")
    # toy: T1001 ranked INTL-1 (male); T1002 and T1003 ranked INTL-2 (female)
    assert "CHECK: form shows only male slot" in d.loc["INTL-1", "source"]
    assert "CHECK: form shows only female slot" in d.loc["INTL-2", "source"]
    assert "CHECK: form shows only" not in d.loc["SING-1", "source"]


def test_single_label():
    assert infer_gender_from_form("female")[0] == "female"


def test_both_labels_blank():
    g, note = infer_gender_from_form("female|male")
    assert g is None and note.startswith("CHECK")


def test_no_label_blank():
    assert infer_gender_from_form(None)[0] is None


def test_teacher_draft_marks_inferred_gender(toy):
    teachers = toy["teachers"].copy()
    teachers.loc[teachers["teacher_id"] == "T1002", "slot_genders_ranked"] = (
        "female|male"
    )
    t = draft_teacher_params(teachers, "2027").set_index("teacher_id")
    assert (t.loc["T1001", "gender"], t.loc["T1001", "status"]) == ("male", "inferred")
    assert "gender: form slot label" in t.loc["T1001", "source"]
    # both labels on the form: blank and flagged, never resolved by picking one
    assert (t.loc["T1002", "gender"], t.loc["T1002", "status"]) == ("", "assumed")
    assert "CHECK" in t.loc["T1002", "source"]
    # no form: unknown stays unknown
    assert (t.loc["T1000", "gender"], t.loc["T1000", "status"]) == ("", "assumed")


def test_other_cycles_ignored(toy):
    other = toy["courses"].assign(cycle="2026", course_id="OLD-1")
    courses = pd.concat([toy["courses"], other])
    c = draft_course_params(courses, toy["preferences"], "2027", CAP)
    assert "OLD-1" not in set(c["course_id"])


def test_unknown_course_type_raises(toy):
    with pytest.raises(ValueError, match="no default capacity"):
        draft_course_params(
            toy["courses"], toy["preferences"], "2027", {"intl": (2, 2)}
        )


def test_merge_keeps_hand_edits_and_reports_orphans(toy):
    draft = draft_teacher_params(toy["teachers"], "2027")
    existing = draft.iloc[:2].copy()
    existing.loc[existing.index[0], ["gender", "status"]] = ["female", "confirmed"]
    existing = pd.concat(
        [existing, draft.iloc[:1].assign(teacher_id="T9999")], ignore_index=True
    )
    merged, added, orphans = merge_keep_existing(draft, existing, "teacher_id", "2027")
    row = merged.set_index("teacher_id").loc[draft["teacher_id"].iloc[0]]
    assert (row["gender"], row["status"]) == ("female", "confirmed")
    assert sorted(added) == sorted(draft["teacher_id"].iloc[2:])
    assert orphans == ["T9999"]


def _course_rows():
    existing = pd.DataFrame(
        {
            "cycle": ["2027", "2027", "2026"],
            "course_id": ["PHIL-4", "OTHER", "PHIL-4"],
            "max_sponsors": ["3", "2", "2"],
            "male_slots": ["0", "1", "0"],
            "source": ["capacity: 3-3; gender: no slot suffix seen", "x", "old"],
            "status": ["assumed", "confirmed", "assumed"],
        }
    )
    draft = pd.DataFrame(
        {
            "cycle": ["2027", "2027"],
            "course_id": ["PHIL-4", "OTHER"],
            "max_sponsors": [2, 2],
            "male_slots": [1, 1],
            "female_slots": [1, 1],
            "source": ["capacity: default 2-2; gender: 1M/1F; requires: x"] * 2,
            "status": ["assumed", "assumed"],
        }
    )
    return existing, draft


def test_refresh_keeps_other_edits():
    existing, draft = _course_rows()
    out = refresh_columns(existing, draft, "course_id", "2027", ["male_slots"])
    row = out[(out["cycle"] == "2027") & (out["course_id"] == "PHIL-4")].iloc[0]
    assert row["male_slots"] == "1"
    assert (row["max_sponsors"], row["status"]) == ("3", "assumed")
    assert row["source"] == "capacity: 3-3; gender: no slot suffix seen"


def test_refresh_leaves_other_cycles_alone():
    existing, draft = _course_rows()
    out = refresh_columns(existing, draft, "course_id", "2027", ["male_slots"])
    assert out[out["cycle"] == "2026"].iloc[0]["male_slots"] == "0"


def test_refresh_adds_a_missing_column():
    existing, draft = _course_rows()
    out = refresh_columns(existing, draft, "course_id", "2027", ["female_slots"])
    by_cycle = out.set_index(["cycle", "course_id"])["female_slots"]
    assert by_cycle[("2027", "PHIL-4")] == "1"
    assert by_cycle[("2026", "PHIL-4")] == ""


def test_refresh_gender_source_replaces_only_the_gender_note():
    existing, draft = _course_rows()
    out = refresh_gender_source(existing, draft, "course_id", "2027")
    phil = out[(out["cycle"] == "2027") & (out["course_id"] == "PHIL-4")].iloc[0]
    assert phil["source"] == "capacity: 3-3; gender: 1M/1F"
    assert phil["status"] == "assumed"
    assert out[out["cycle"] == "2026"].iloc[0]["source"] == "old"


def test_refresh_gender_source_marks_inferred_teachers():
    existing = pd.DataFrame(
        {
            "cycle": ["2027", "2027"],
            "teacher_id": ["T1", "T2"],
            "source": ["q: coded; gender: not yet received"] * 2,
            "status": ["assumed", "assumed"],
        }
    )
    draft = existing.assign(
        source=["q: x; gender: form slot label", "q: x; gender: not yet received"],
        status=["inferred", "assumed"],
    )
    out = refresh_gender_source(existing, draft, "teacher_id", "2027")
    assert list(out["status"]) == ["inferred", "assumed"]
    assert out.iloc[0]["source"] == "q: coded; gender: form slot label"


def test_output_loads_with_data_py(toy, tmp_path):
    """The drafted files must be readable by load_cycle without edits."""
    for name in ("courses", "teachers", "preferences", "course_lineage"):
        (tmp_path / f"{name}.csv").write_text((TOY_DIR / f"{name}.csv").read_text())
    draft_course_params(toy["courses"], toy["preferences"], "2027", CAP).to_csv(
        tmp_path / "course_params.csv", index=False
    )
    draft_teacher_params(toy["teachers"], "2027").to_csv(
        tmp_path / "teacher_params.csv", index=False
    )
    cycle = load_cycle(tmp_path)
    assert all(c.max_sponsors == 2 for c in cycle.courses)
    genders = {t.teacher_id: t.gender for t in cycle.teachers}
    assert genders["T1000"] is None and genders["T1001"] == "male"


def test_repo_guard_points_at_repo_root():
    """The outside-the-repo guard is only as good as REPO_ROOT. It broke once
    when idmap.py moved into the package; this pins it."""
    from stable_sponsors.pseudonymize.idmap import REPO_ROOT, _guard

    assert (REPO_ROOT / "pyproject.toml").is_file()
    with pytest.raises(SystemExit, match="REFUSING"):
        _guard(REPO_ROOT / "derived", "test path")
