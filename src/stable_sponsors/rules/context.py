from dataclasses import dataclass

from ortools.sat.python import cp_model

from stable_sponsors.data import Cycle


@dataclass
class Ctx:
    model: cp_model.CpModel
    cycle: Cycle
    x: dict[tuple[str, str], cp_model.IntVar]


def build_ctx(cycle: Cycle) -> Ctx:
    model = cp_model.CpModel()
    x = {
        (t.teacher_id, c.course_id): model.new_bool_var(
            f"x_{t.teacher_id}_{c.course_id}"
        )
        for t in cycle.teachers
        for c in cycle.courses
    }
    return Ctx(model=model, cycle=cycle, x=x)
