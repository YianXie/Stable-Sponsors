from stable_sponsors.rules.context import Ctx

from .registry import register


@register(0)
def incumbency_preassignment(ctx: Ctx, params: dict) -> None:
    """Pre-assign repeaters to the same course they taught last year.

    Args:
        ctx (Ctx): the context
        params (dict): the parameters for the course, from the yaml config file
    """

    for teacher in ctx.cycle.teachers:
        if teacher.is_repeater:
            course_id = teacher.prior_course_id
            assert course_id is not None, "Repeater teacher must have a prior course ID"
            ctx.model.add(ctx.x[(teacher.teacher_id, course_id)] == 1)


@register(3)
def qualification_required(ctx: Ctx, params: dict) -> None:
    """Ensure that only qualified teachers can be assigned to certain courses.

    Args:
        ctx (Ctx): The context
        params (dict): The parameters for the course, from the yaml config file
    """

    for teacher in ctx.cycle.teachers:
        for course in ctx.cycle.courses:
            if not all(
                requirements in teacher.qualifications
                for requirements in course.requires
            ):
                ctx.model.add(ctx.x[(teacher.teacher_id, course.course_id)] == 0)


@register(4)
def only_ranked_courses(ctx: Ctx, params: dict) -> None:
    """Ensure that teachers are only assigned to courses they have ranked.

    Args:
        ctx (Ctx): The context
        params (dict): The parameters for the course, from the yaml config file
    """

    ranked = {(p.teacher_id, p.course_id) for p in ctx.cycle.preferences}
    submitters = {p.teacher_id for p in ctx.cycle.preferences}
    for t in ctx.cycle.teachers:
        if t.teacher_id not in submitters:
            continue
        for c in ctx.cycle.courses:
            if (t.teacher_id, c.course_id) not in ranked:
                ctx.model.add(ctx.x[(t.teacher_id, c.course_id)] == 0)


@register(5)
def slot_gender(ctx: Ctx, params: dict) -> None:
    """Ensure that teachers are only assigned to courses that match their gender.

    Args:
        ctx (Ctx): The context
        params (dict): The parameters for the course, from the yaml config file

    Raises:
        ValueError: If a teacher has no gender specified or a course has no female slots specified.
    """

    for teacher in ctx.cycle.teachers:
        if teacher.gender is None:
            raise ValueError(f"Teacher {teacher.teacher_id} has no gender specified")

    # Ensure that each course has exactly `female_slots` female sponsors.
    for course in ctx.cycle.courses:
        if course.male_slots is None or course.female_slots is None:
            raise ValueError(
                f"Course {course.course_id} must have both male and female slots specified."
            )
        cid = course.course_id
        women = sum(
            ctx.x[(t.teacher_id, cid)]
            for t in ctx.cycle.teachers
            if t.gender == "female"
        )
        men = sum(
            ctx.x[(t.teacher_id, cid)] for t in ctx.cycle.teachers if t.gender == "male"
        )
        ctx.model.add(women >= course.female_slots * ctx.y[cid])
        ctx.model.add(men >= course.male_slots * ctx.y[cid])


@register(8)
def one_course_per_teacher(ctx, params):
    """Ensure that each teacher is assigned to at most one course.

    Args:
        ctx (Ctx): The context
        params (dict): The parameters for the course, from the yaml config file
    """

    for teacher in ctx.cycle.teachers:
        ctx.model.add(
            sum(
                ctx.x[(teacher.teacher_id, course.course_id)]
                for course in ctx.cycle.courses
            )
            <= 1
        )


@register(9)
def course_capacity(ctx: Ctx, params: dict) -> None:
    """Ensure that the number of sponsors for each course is within the specified bounds.

    Args:
        ctx (Ctx): The context
        params (dict): The parameters for the course, from the yaml config file

    Raises:
        ValueError: If no capacity bounds are specified for a course.
    """

    for course in ctx.cycle.courses:
        min_capacity = course.min_sponsors
        max_capacity = course.max_sponsors

        if min_capacity is None or max_capacity is None:
            raise ValueError(
                f"Course {course.course_id} must have both min and max capacity specified."
            )

        # Ensure that the number of sponsors for each course is within the specified bounds.
        ctx.model.add(
            sum(ctx.x[(t.teacher_id, course.course_id)] for t in ctx.cycle.teachers)
            >= min_capacity * ctx.y[course.course_id]
        )
        ctx.model.add(
            sum(ctx.x[(t.teacher_id, course.course_id)] for t in ctx.cycle.teachers)
            <= max_capacity * ctx.y[course.course_id]
        )
