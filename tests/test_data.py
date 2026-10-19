from pathlib import Path

from stable_sponsors.data import load_cycle, load_observed_placements


def test_load_cycle() -> None:
    base = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "toy_cycle"

    cycle = load_cycle(base)
    assert len(cycle.teachers) == 5
    assert len(cycle.courses) == 4

    placements = load_observed_placements(base / "placements.csv", cycle)
    assert len(placements) == 5


# --- cross-year course identity -------------------------------------------

import shutil

import pytest

from stable_sponsors.compare import violations
from stable_sponsors.data import ObservedPlacement
from stable_sponsors.rules.context import build_ctx
from stable_sponsors.rules.hard import incumbency_preassignment

TOY = Path(__file__).resolve().parent / "fixtures" / "toy_cycle"
HEADER = "prior_cycle,prior_course_id,cycle,course_id,basis,status,note\n"


def _toy_with_lineage(tmp_path: Path, rows: str) -> Path:
    for f in TOY.glob("*.csv"):
        shutil.copy(f, tmp_path)
    (tmp_path / "course_lineage.csv").write_text(HEADER + rows)
    return tmp_path


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
    pinned = {ctx.model.proto.variables[c.linear.vars[0]].name for c in ctx.model.proto.constraints}
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
    names = {ctx.model.proto.variables[c.linear.vars[0]].name for c in ctx.model.proto.constraints}
    assert not any(n.startswith("x_T1000_") for n in names)

    # ...and placing them anywhere is not an incumbency violation
    obs = (ObservedPlacement(cycle=2027, course_id="INTL-2", sponsor_slot=1, teacher_id="T1000"),)
    assert "T1000" not in violations(cyc, obs)["0 incumbency"]
