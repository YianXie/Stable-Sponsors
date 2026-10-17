from dataclasses import replace

import pytest
import yaml
from ortools.sat.python import cp_model

from stable_sponsors.data import Cycle, load_observed_placements
from stable_sponsors.rules.context import Ctx, build_ctx
from stable_sponsors.rules.hard import (
    course_capacity,
    incumbency_preassignment,
    one_course_per_teacher,
    only_ranked_courses,
    qualification_required,
    slot_gender,
)
from stable_sponsors.rules.registry import ENCODERS
from tests.conftest import REPO_ROOT, TOY_DIR

FEASIBLE = {cp_model.OPTIMAL, cp_model.FEASIBLE}


def solve(ctx: Ctx) -> cp_model.CpSolverStatus:
    """Solve a cp model

    Args:
        ctx (Ctx): the context

    Returns:
        cp_model.CpSolverStatus: the status of the solver
    """

    return cp_model.CpSolver().solve(ctx.model)


def force(ctx: Ctx, teacher_ids: tuple[str, ...], course_id: str) -> None:
    """Force a teacher to be assigned to a course.

    Args:
        ctx (Ctx): the context
        teacher_ids (str): the IDs of the teachers to force
        course_id (str): the ID of the course to which to force the teachers

    Raises:
        ValueError: If the course ID is not found in the context.
    """

    if course_id not in ctx.y:
        raise ValueError(f"Course ID {course_id} not found in context")

    for tid in teacher_ids:
        ctx.model.add(ctx.x[(tid, course_id)] == 1)


### Incumbency preassignment tests


def test_repeater_cannot_be_moved_out(ctx: Ctx) -> None:
    """Test that a repeater cannot be moved out of the course they taught last year.

    Args:
        ctx (Ctx): the context for the toy cycle.
    """

    incumbency_preassignment(ctx, {})
    ctx.model.add(ctx.x[("T1000", "INTL-1")] == 0)
    status = solve(ctx)
    assert status == cp_model.INFEASIBLE


def test_non_repeater_can_take_open_slot(ctx: Ctx) -> None:
    """Test that non-repeaters can be assigned to other courses.

    Args:
        ctx (Ctx): the context for the toy cycle.
    """

    incumbency_preassignment(ctx, {})
    force(ctx, ("T1001",), "INTL-1")
    status = solve(ctx)
    assert status in FEASIBLE


def test_non_repeater_is_not_forced_anywhere(ctx: Ctx) -> None:
    """Test that a non-repeater is not forced to be assigned to any course.

    Args:
        ctx (Ctx): the context for the toy cycle.
    """
    incumbency_preassignment(ctx, {})
    for c in ctx.cycle.courses:
        ctx.model.add(ctx.x[("T1001", c.course_id)] == 0)
    assert solve(ctx) in FEASIBLE


def test_no_repeaters_adds_no_constraints(toy_cycle: Cycle) -> None:
    """Test that no constraints is added when there are no repeaters.

    Args:
        toy_cycle (Cycle): the toy cycle.
    """
    no_rep = replace(
        toy_cycle,
        teachers=tuple(
            replace(t, is_repeater=False, prior_course_id=None)
            for t in toy_cycle.teachers
        ),
    )
    ctx = build_ctx(no_rep)
    incumbency_preassignment(ctx, {})
    assert len(ctx.model.proto.constraints) == 0


### Qualification required tests


def test_non_qualified_teacher_cannot_be_assigned(ctx: Ctx) -> None:
    """Test that a non-qualified teacher cannot be assigned to a course with a qualification requirement.

    Args:
        ctx (Ctx): the context for the toy cycle.
    """

    qualification_required(ctx, {})
    force(ctx, ("T1001",), "INTL-1")
    status = solve(ctx)
    assert status == cp_model.INFEASIBLE


def test_qualified_teacher_can_choose_other_courses(ctx: Ctx) -> None:
    """Test that a qualified teacher can be assigned to other courses.

    Args:
        ctx (Ctx): the context for the toy cycle.
    """

    qualification_required(ctx, {})
    force(ctx, ("T1000",), "INTL-2")
    status = solve(ctx)
    assert status in FEASIBLE


def test_qualified_teacher_can_take_restricted_course(ctx: Ctx):
    """Test that a qualified teacher can be assigned to a course with a qualification requirement.

    Args:
        ctx (Ctx): The context for the toy cycle.
    """

    qualification_required(ctx, {})
    force(ctx, ("T1000",), "INTL-1")  # T1000 has scuba
    assert solve(ctx) in FEASIBLE


def test_all_requirements_needed_not_any(toy_cycle: Cycle):
    """Test that a teacher must have all requirements for a course, not just any one of them.

    Args:
        toy_cycle (Cycle): The toy cycle.
    """

    courses = tuple(
        replace(c, requires=("scuba", "first_aid")) if c.course_id == "INTL-1" else c
        for c in toy_cycle.courses
    )
    ctx = build_ctx(replace(toy_cycle, courses=courses))
    qualification_required(ctx, {})
    force(ctx, ("T1002",), "INTL-1")  # has first_aid, not scuba
    assert solve(ctx) == cp_model.INFEASIBLE


def test_unrestricted_course_open_to_unqualified(ctx: Ctx):
    """Test that an unrestricted course can be assigned to unqualified teachers.

    Args:
        ctx (Ctx): The context for the toy cycle.
    """

    qualification_required(ctx, {})
    force(ctx, ("T1001",), "INTL-2")  # T1001 has no qualifications
    assert solve(ctx) in FEASIBLE


def test_exactly_one_block_per_unqualified_pair(ctx: Ctx):
    """Test that each unqualified teacher-course pair is blocked by exactly one constraint.

    Args:
        ctx (Ctx): The context for the toy cycle.
    """

    qualification_required(ctx, {})
    # INTL-1 needs scuba; T1001–T1003 lack it → 3 constraints, nothing else
    assert len(ctx.model.proto.constraints) == 3


### Only ranked courses tests


def test_unranked_course_is_infeasible(ctx: Ctx) -> None:
    """Test that a teacher cannot be assigned to a course they have not ranked.

    Args:
        ctx (Ctx): the context for the toy cycle.
    """

    only_ranked_courses(ctx, {})
    force(ctx, ("T1002",), "SING-1")  # T1002 has not ranked SING-1
    status = solve(ctx)
    assert status == cp_model.INFEASIBLE


def test_ranked_course_is_feasible(ctx: Ctx) -> None:
    """Test that a teacher can be assigned to a course they have ranked.

    Args:
        ctx (Ctx): the context for the toy cycle.
    """

    only_ranked_courses(ctx, {})
    force(ctx, ("T1001",), "INTL-2")  # T1001 has ranked INTL-2
    status = solve(ctx)
    assert status in FEASIBLE


### Slot gender tests


def test_female_slot_mismatch_is_infeasible(ctx: Ctx) -> None:
    """Test that a teacher cannot be assigned to a course that does not match their gender.

    Args:
        ctx (Ctx): the context for the toy cycle.
    """

    course_capacity(ctx, {})
    slot_gender(ctx, {})
    force(
        ctx, ("T1000", "T1002"), "INTL-2"
    )  # T1000 and T1002 are male; INTL-2 needs 1 female
    status = solve(ctx)
    assert status == cp_model.INFEASIBLE


def test_female_slot_match_is_feasible(ctx: Ctx) -> None:
    """Test that a teacher can be assigned to a course that matches their gender.

    Args:
        ctx (Ctx): the context for the toy cycle.
    """

    slot_gender(ctx, {})
    force(ctx, ("T1003",), "INTL-2")  # T1003 is female; INTL-2 needs 1 female
    status = solve(ctx)
    assert status in FEASIBLE


def test_missing_teacher_gender_raises(ctx: Ctx) -> None:
    """Test that a ValueError is raised if a teacher has no gender specified.

    Args:
        ctx (Ctx): the context for the toy cycle.
    """

    # Remove gender from T1000
    ctx.cycle = replace(
        ctx.cycle,
        teachers=tuple(
            replace(t, gender=None) if t.teacher_id == "T1000" else t
            for t in ctx.cycle.teachers
        ),
    )
    with pytest.raises(ValueError, match="has no gender specified"):
        slot_gender(ctx, {})


def test_missing_female_slots_raises(ctx: Ctx) -> None:
    """Test that a ValueError is raised if a course has no female slots specified.

    Args:
        ctx (Ctx): the context for the toy cycle.
    """

    # Remove female_slots from INTL-2
    ctx.cycle = replace(
        ctx.cycle,
        courses=tuple(
            replace(c, female_slots=None) if c.course_id == "INTL-2" else c
            for c in ctx.cycle.courses
        ),
    )
    with pytest.raises(ValueError, match="must have both male and female slots"):
        slot_gender(ctx, {})


### One course per teacher tests


def test_two_courses_for_one_teacher_is_infeasible(ctx: Ctx) -> None:
    """Test that a teacher cannot be assigned to more than one course.

    Args:
        ctx (Ctx): the context for the toy cycle.
    """

    one_course_per_teacher(ctx, {})
    force(ctx, ("T1000",), "INTL-1")
    force(ctx, ("T1000",), "INTL-2")
    status = solve(ctx)
    assert status == cp_model.INFEASIBLE


def test_one_course_per_teacher_is_feasible(ctx: Ctx) -> None:
    """Test that a teacher can be assigned to one course.

    Args:
        ctx (Ctx): the context for the toy cycle.
    """

    one_course_per_teacher(ctx, {})
    force(ctx, ("T1000",), "INTL-1")
    status = solve(ctx)
    assert status in FEASIBLE


### Course capacity tests


def test_over_max_is_infeasible(ctx):
    course_capacity(ctx, {})
    force(ctx, ("T1000", "T1001", "T1002"), "INTL-1")  # 3 > max 2
    assert solve(ctx) == cp_model.INFEASIBLE


def test_within_bounds_is_feasible(ctx):
    course_capacity(ctx, {})
    force(ctx, ("T1000", "T1001"), "INTL-1")  # 2 <= max 2
    assert solve(ctx) in FEASIBLE


def test_running_course_below_min_is_infeasible(ctx):
    course_capacity(ctx, {})
    ctx.model.add(ctx.y["INTL-2"] == 1)
    for t in ctx.cycle.teachers:
        ctx.model.add(ctx.x[(t.teacher_id, "INTL-2")] == 0)
    assert solve(ctx) == cp_model.INFEASIBLE


def test_missing_bounds_raises(ctx):
    ctx.cycle = replace(
        ctx.cycle,
        courses=tuple(
            c
            if c.course_id != "INTL-1"
            else replace(c, min_sponsors=None, max_sponsors=None)
            for c in ctx.cycle.courses
        ),
    )
    with pytest.raises(
        ValueError, match="must have both min and max capacity specified"
    ):
        course_capacity(ctx, {})


### Observed placement tests


RULES = yaml.safe_load((REPO_ROOT / "config" / "rules-2027.yaml").read_text())["rules"]


def test_observed_toy_placement_satisfies_all_hard_rules(toy_cycle: Cycle) -> None:
    ctx = build_ctx(toy_cycle)
    for r in RULES:
        if r["class"] == "hard" and r["status"] != "deferred":
            ENCODERS[r["id"]](ctx, r["params"])
    for p in load_observed_placements(TOY_DIR / "placements.csv", toy_cycle):
        ctx.model.add(ctx.x[(p.teacher_id, p.course_id)] == 1)
    assert solve(ctx) in FEASIBLE
