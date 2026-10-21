from stable_sponsors.rules.context import Ctx

from .registry import register


@register(0)
def incumbency_preassignment(ctx: Ctx, params: dict) -> None:
    """Pre-assign repeaters to the same course they taught last year.

    Args:
        ctx (Ctx): the context
        params (dict): the parameters for the course, from the yaml config file

    Raises:
        ValueError: If a repeater's incumbent course is not in the current cycle. Repeaters whose prior course was discontinued (incumbent_course_id is None) are skipped.
    """

    course_ids = {c.course_id for c in ctx.cycle.courses}
    for teacher in ctx.cycle.teachers:
        course_id = teacher.incumbent_course_id
        # course_id is None: prior course discontinued (lineage), nothing to repeat into
        if not teacher.is_repeater or course_id is None:
            continue
        if course_id not in course_ids:
            raise ValueError(
                f"Repeater teacher {teacher.teacher_id} has prior course ID {course_id} which is not in the current cycle's courses."
            )
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
            if not set(course.requires) <= set(teacher.qualifications):
                ctx.model.add(ctx.x[(teacher.teacher_id, course.course_id)] == 0)


@register(4)
def only_ranked_courses(ctx: Ctx, params: dict) -> None:
    """Ensure that teachers are only assigned to courses they have ranked.

    Args:
        ctx (Ctx): The context
        params (dict): The parameters for the course, from the yaml config file
    """

    ranked = {(p.teacher_id, p.course_id) for p in ctx.cycle.preferences}
    ranked |= {
        (t.teacher_id, t.incumbent_course_id)
        for t in ctx.cycle.teachers
        if t.is_repeater and t.incumbent_course_id is not None
    }
    submitters = {p.teacher_id for p in ctx.cycle.preferences}

    for t in ctx.cycle.teachers:
        if t.teacher_id not in submitters:
            continue
        for c in ctx.cycle.courses:
            if (t.teacher_id, c.course_id) not in ranked:
                ctx.model.add(ctx.x[(t.teacher_id, c.course_id)] == 0)


@register(5)
def slot_gender(ctx: Ctx, params: dict) -> None:
    """Ensure that each running course gets at least its male and female slots filled by teachers of that gender.

    Args:
        ctx (Ctx): The context
        params (dict): The parameters for the course, from the yaml config file

    Raises:
        ValueError: If a teacher has no gender specified or a course has no male or female slots specified.
    """

    for teacher in ctx.cycle.teachers:
        if teacher.gender is None:
            raise ValueError(f"Teacher {teacher.teacher_id} has no gender specified")

    # A running course has at least `female_slots` female and `male_slots` male sponsors.
    for course in ctx.cycle.courses:
        if course.male_slots is None or course.female_slots is None:
            raise ValueError(
                f"Course {course.course_id} must have both male and female slots specified."
            )
        cid = course.course_id
        for gender, slots in (
            ("female", course.female_slots),
            ("male", course.male_slots),
        ):
            sponsors = sum(
                ctx.x[(t.teacher_id, cid)]
                for t in ctx.cycle.teachers
                if t.gender == gender
            )
            ctx.model.add(sponsors >= slots * ctx.y[cid])


@register(8)
def one_course_per_teacher(ctx: Ctx, params: dict) -> None:
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
        if course.min_sponsors is None or course.max_sponsors is None:
            raise ValueError(
                f"Course {course.course_id} must have both min and max capacity specified."
            )

        cid = course.course_id
        sponsors = sum(ctx.x[(t.teacher_id, cid)] for t in ctx.cycle.teachers)
        ctx.model.add(sponsors >= course.min_sponsors * ctx.y[cid])
        ctx.model.add(sponsors <= course.max_sponsors * ctx.y[cid])


@register(10)
def courses_run_as_observed(ctx: Ctx, params: dict) -> None:
    """Treat the set of running courses as given (decided before sponsor allocation).

    Args:
        ctx (Ctx): The context
        params (dict): The parameters for the course, from the yaml config file
    """
    for c in ctx.cycle.courses:
        ctx.model.add(ctx.y[c.course_id] == int(c.ran))
