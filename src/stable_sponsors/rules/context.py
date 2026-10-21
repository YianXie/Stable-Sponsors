from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from stable_sponsors.data import Cycle


@dataclass
class Ctx:
    """Model context that the rule encoders add constraints and objective terms to.

    Attributes:
        model (cp_model.CpModel): The CP model for the optimization problem.
        cycle (Cycle): The cycle being allocated.
        x (dict[tuple[str, str], cp_model.IntVar]): A dictionary mapping teacher-course pairs to boolean variables (teacher assigned to course).
        y (dict[str, cp_model.IntVar]): A dictionary mapping courses to boolean variables (course runs).
        objective (list): A list of terms to be added to the objective function.
    """

    model: cp_model.CpModel
    cycle: Cycle
    x: dict[tuple[str, str], cp_model.IntVar]
    y: dict[str, cp_model.IntVar]
    objective: list = field(default_factory=list)


def build_ctx(cycle: Cycle) -> Ctx:
    """Build the model context for a cycle

    Args:
        cycle (Cycle): the cycle being allocated

    Returns:
        Ctx: the model context
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
