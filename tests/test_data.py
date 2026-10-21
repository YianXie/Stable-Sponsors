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


# --- observed placements ---------------------------------------------------


def test_observed_placements_keep_assigned_rows_of_this_cycle(tmp_path, toy_cycle):
    """derived/placements.csv also holds empty sponsor slots (no teacher) and
    other cycles' rows. Those are not placements in this cycle."""
    p = tmp_path / "placements.csv"
    p.write_text(
        (TOY_DIR / "placements.csv").read_text().rstrip("\n")
        + "\n2027, INTL-1, 3, , blank_in_source"
        + "\n2027, INTL-2, 3, , blank_in_source"
        + "\n2026, INTL-1, 1, T1001, assigned\n"
    )
    placements = load_observed_placements(p, toy_cycle)
    assert placements == load_observed_placements(TOY_DIR / "placements.csv", toy_cycle)
