from dataclasses import dataclass

from ortools.sat.python import cp_model

from stable_sponsors.data import Cycle


@dataclass
class Ctx:
    """Course context for the optimization problem

    Attributes:
        model (cp_model.CpModel): The CP model for the optimization problem.
        cycle (Cycle): The cycle that the course ran.
        course_params (dict[str, CourseParams]): The parameters for each course.
        x (dict[tuple[str, str], cp_model.IntVar]): A dictionary mapping teacher-course pairs to boolean variables.
        y (dict[str, cp_model.IntVar]): A dictionary mapping courses to boolean variables.
    """

    model: cp_model.CpModel
    cycle: Cycle
    x: dict[tuple[str, str], cp_model.IntVar]
    y: dict[str, cp_model.IntVar]


def build_ctx(cycle: Cycle) -> Ctx:
    """Build course context

    Args:
        cycle (Cycle): the cycle that the course ran

    Returns:
        Ctx: the course context
    """

    model = cp_model.CpModel()
    x = {
        (t.teacher_id, c.course_id): model.new_bool_var(
            f"x_{t.teacher_id}_{c.course_id}"
        )
        for t in cycle.teachers
        for c in cycle.courses
    }
    y = {c.course_id: model.new_bool_var(f"y_{c.course_id}") for c in cycle.courses}
    return Ctx(model=model, cycle=cycle, x=x, y=y)
