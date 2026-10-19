from pathlib import Path

import pandas as pd
import pytest

from stable_sponsors.data import load_cycle
from stable_sponsors.params import (
    _read,
    draft_course_params,
    draft_teacher_params,
    merge_keep_existing,
)

TOY = Path(__file__).resolve().parent / "fixtures" / "toy_cycle"
CAP = {"intl": (2, 2), "sg": (2, 2)}


@pytest.fixture
def toy():
    return {n: _read(TOY / f"{n}.csv") for n in ("courses", "teachers", "preferences")}


def test_one_row_per_course_and_teacher(toy):
    c = draft_course_params(toy["courses"], toy["preferences"], "2027", CAP)
    t = draft_teacher_params(toy["teachers"], "2027")
    assert sorted(c["course_id"]) == sorted(toy["courses"]["course_id"])
    assert sorted(t["teacher_id"]) == sorted(toy["teachers"]["teacher_id"])
    assert set(c["status"]) == set(t["status"]) == {"assumed"}


def test_gender_slots_come_from_form_suffix(toy):
    c = draft_course_params(toy["courses"], toy["preferences"], "2027", CAP)
    c = c.set_index("course_id")
    # toy: T1001 ranked INTL-1 (male); T1003 ranked INTL-2 (female)
    assert (c.loc["INTL-1", "male_slots"], c.loc["INTL-1", "female_slots"]) == (1, 0)
    assert (c.loc["INTL-2", "male_slots"], c.loc["INTL-2", "female_slots"]) == (0, 1)


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


def test_output_loads_with_data_py(toy, tmp_path):
    """The drafted files must be readable by load_cycle without edits."""
    for name in ("courses", "teachers", "preferences", "course_lineage"):
        (tmp_path / f"{name}.csv").write_text((TOY / f"{name}.csv").read_text())
    draft_course_params(toy["courses"], toy["preferences"], "2027", CAP).to_csv(
        tmp_path / "course_params.csv", index=False
    )
    draft_teacher_params(toy["teachers"], "2027").to_csv(
        tmp_path / "teacher_params.csv", index=False
    )
    cycle = load_cycle(tmp_path)
    assert all(c.max_sponsors == 2 for c in cycle.courses)
    assert all(t.gender is None for t in cycle.teachers)


def test_repo_guard_points_at_repo_root():
    """The outside-the-repo guard is only as good as REPO_ROOT. It broke once
    when idmap.py moved into the package; this pins it."""
    from stable_sponsors.pseudonymize.idmap import REPO_ROOT, _guard

    assert (REPO_ROOT / "pyproject.toml").is_file()
    with pytest.raises(SystemExit, match="REFUSING"):
        _guard(REPO_ROOT / "derived", "test path")
