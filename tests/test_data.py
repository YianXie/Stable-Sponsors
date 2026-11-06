import shutil
from pathlib import Path

import pytest

from stable_sponsors.compare import violations
from stable_sponsors.data import ObservedPlacement, load_cycle, load_observed_placements
from stable_sponsors.rules.context import Ctx, build_ctx
from stable_sponsors.rules.hard import incumbency_preassignment
from tests.conftest import TOY_DIR

HEADER = "prior_cycle,prior_course_id,cycle,course_id,basis,status,note\n"


def test_load_cycle(toy_cycle) -> None:
    assert len(toy_cycle.teachers) == 5
    assert len(toy_cycle.courses) == 4

    placements = load_observed_placements(TOY_DIR / "placements.csv", toy_cycle)
    assert len(placements) == 5


# --- cross-year course identity -------------------------------------------


def _toy_with_lineage(tmp_path: Path, rows: str) -> Path:
    for f in TOY_DIR.glob("*.csv"):
        shutil.copy(f, tmp_path)
    (tmp_path / "course_lineage.csv").write_text(HEADER + rows)
    return tmp_path


def _pinned(ctx: Ctx) -> set[str]:
    """Names of the variables the model's constraints were added on."""
    return {
        ctx.model.proto.variables[c.linear.vars[0]].name
        for c in ctx.model.proto.constraints
    }


def test_prior_code_is_translated_not_reused(tmp_path):
    """The trap: last year's INTL-1 is this year's INTL-2, and this year's
    INTL-1 is a different trip. The repeater must land in INTL-2."""
    base = _toy_with_lineage(
        tmp_path,
        "2026,INTL-1,2027,INTL-2,toy,confirmed,\n2026,INTL-2,2027,INTL-2,toy,confirmed,\n",
    )
    cyc = load_cycle(base)
    t1000 = next(t for t in cyc.teachers if t.teacher_id == "T1000")
    assert t1000.prior_course_id == "INTL-1"
    assert t1000.incumbent_course_id == "INTL-2"

    ctx = build_ctx(cyc)
    incumbency_preassignment(ctx, {})
    pinned = _pinned(ctx)
    assert "x_T1000_INTL-2" in pinned
    assert "x_T1000_INTL-1" not in pinned


def test_missing_lineage_row_raises(tmp_path):
    base = _toy_with_lineage(tmp_path, "2026,INTL-2,2027,INTL-2,toy,confirmed,\n")
    with pytest.raises(ValueError, match="no lineage row for prior course INTL-1"):
        load_cycle(base)


def test_lineage_target_must_exist_this_year(tmp_path):
    base = _toy_with_lineage(
        tmp_path,
        "2026,INTL-1,2027,INTL-9,toy,confirmed,\n2026,INTL-2,2027,INTL-2,toy,confirmed,\n",
    )
    with pytest.raises(ValueError, match="not in this cycle"):
        load_cycle(base)


def test_duplicate_lineage_rows_raise(tmp_path):
    base = _toy_with_lineage(
        tmp_path,
        "2026,INTL-1,2027,INTL-1,toy,confirmed,\n2026,INTL-1,2027,INTL-2,toy,confirmed,\n"
        "2026,INTL-2,2027,INTL-2,toy,confirmed,\n",
    )
    with pytest.raises(ValueError, match="more than one row"):
        load_cycle(base)


def test_discontinued_course_means_no_incumbency(tmp_path):
    base = _toy_with_lineage(
        tmp_path,
        "2026,INTL-1,2027,,discontinued,assumed,\n2026,INTL-2,2027,INTL-2,toy,confirmed,\n",
    )
    cyc = load_cycle(base)
    t1000 = next(t for t in cyc.teachers if t.teacher_id == "T1000")
    assert t1000.incumbent_course_id is None  # blank cell -> None, not NaN

    ctx = build_ctx(cyc)
    incumbency_preassignment(ctx, {})
    assert not any(n.startswith("x_T1000_") for n in _pinned(ctx))

    # ...and placing them anywhere is not an incumbency violation
    obs = (
        ObservedPlacement(
            cycle=2027, course_id="INTL-2", sponsor_slot=1, teacher_id="T1000"
        ),
    )
    assert "T1000" not in violations(cyc, obs)["0 incumbency"]


def test_lineage_off_reuses_prior_code(tmp_path):
    """use_lineage=False is the pre-fix behaviour: the lineage table is ignored
    and the prior-year code is matched by code against this year's catalogue."""
    base = _toy_with_lineage(
        tmp_path,
        "2026,INTL-1,2027,INTL-2,toy,confirmed,\n2026,INTL-2,2027,INTL-2,toy,confirmed,\n",
    )
    cyc = load_cycle(base, use_lineage=False)
    t1000 = next(t for t in cyc.teachers if t.teacher_id == "T1000")
    assert t1000.incumbent_course_id == "INTL-1"


def test_lineage_off_unknown_code_means_no_incumbency(tmp_path):
    """Without lineage, a prior code missing from this year's catalogue pins
    nothing. The lineage file is not needed at all."""
    for f in TOY_DIR.glob("*.csv"):
        shutil.copy(f, tmp_path)
    (tmp_path / "course_lineage.csv").unlink()
    teachers = tmp_path / "teachers.csv"
    teachers.write_text(teachers.read_text().replace("INTL-1 ", "INTL-9 ", 1))

    cyc = load_cycle(tmp_path, use_lineage=False)
    t1000 = next(t for t in cyc.teachers if t.teacher_id == "T1000")
    assert t1000.prior_course_id == "INTL-9"
    assert t1000.incumbent_course_id is None


# --- observed placements ---------------------------------------------------


def test_observed_placements_keep_assigned_rows_of_this_cycle(tmp_path, toy_cycle):
    """placements.csv also holds empty sponsor slots (no teacher), and a file may
    hold other cycles' rows. Those are not placements in this cycle."""
    p = tmp_path / "placements.csv"
    p.write_text(
        (TOY_DIR / "placements.csv").read_text().rstrip("\n")
        + "\n2027, INTL-1, 3, , blank_in_source"
        + "\n2027, INTL-2, 3, , blank_in_source"
        + "\n2026, INTL-1, 1, T1001, assigned\n"
    )
    placements = load_observed_placements(p, toy_cycle)
    assert placements == load_observed_placements(TOY_DIR / "placements.csv", toy_cycle)


# --- unknown is not "no" (2026: no repeat file, no round 2) ------------------


def _toy_with_unknowns(tmp_path: Path) -> Path:
    """The toy cycle with is_repeater, prior_course_id and submitted_intl_r2 blank
    for everyone (as in 2026) and INTL-3's `ran` blank."""
    for f in TOY_DIR.glob("*.csv"):
        shutil.copy(f, tmp_path)
    lines = (tmp_path / "teachers.csv").read_text().splitlines()
    out = [lines[0]]
    for line in lines[1:]:
        cells = line.split(",")
        cells[2] = cells[3] = cells[5] = " "
        out.append(",".join(cells))
    (tmp_path / "teachers.csv").write_text("\n".join(out) + "\n")
    courses = (tmp_path / "courses.csv").read_text()
    (tmp_path / "courses.csv").write_text(
        courses.replace(
            "INTL-3   , intl       , True        , False,",
            "INTL-3   , intl       , True        ,      ,",
        )
    )
    return tmp_path


def test_blank_flags_load_as_unknown(tmp_path):
    cyc = load_cycle(_toy_with_unknowns(tmp_path))
    assert {t.is_repeater for t in cyc.teachers} == {None}
    assert {t.submitted_intl_r2 for t in cyc.teachers} == {None}
    assert all(t.incumbent_course_id is None for t in cyc.teachers)
    assert {c.course_id: c.ran for c in cyc.courses}["INTL-3"] is None
    # known flags are still read as before
    assert {t.teacher_id: t.submitted_intl_r1 for t in cyc.teachers}["T1001"] is True


def test_unknown_repeater_pins_nothing(tmp_path):
    ctx = build_ctx(load_cycle(_toy_with_unknowns(tmp_path)))
    incumbency_preassignment(ctx, {})
    assert not any(n.startswith("x_") for n in _pinned(ctx))


def test_unknown_round_flag_contradicted_by_rankings_is_still_checked(tmp_path):
    """Unknown skips the submitted/rankings check only for that flag; a known
    flag that disagrees with the rankings still raises."""
    base = _toy_with_unknowns(tmp_path)
    lines = (base / "teachers.csv").read_text().splitlines()
    for i, line in enumerate(lines):
        cells = line.split(",")
        if cells[1].strip() == "T1001":
            cells[4] = " False"  # T1001 ranked intl_r1
            lines[i] = ",".join(cells)
    (base / "teachers.csv").write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="submitted_intl_r1"):
        load_cycle(base)


def test_no_known_repeaters_needs_no_lineage_file(tmp_path):
    """2026 has no repeat file, so no lineage file either: nothing to translate."""
    base = _toy_with_unknowns(tmp_path)
    (base / "course_lineage.csv").unlink()
    cyc = load_cycle(base)
    assert all(t.incumbent_course_id is None for t in cyc.teachers)
