"""Small inline cycles for tests: one teacher, course or cycle per call, with plain defaults."""

from stable_sponsors.data import (
    Course,
    CourseType,
    Cycle,
    Preference,
    SlotGender,
    Teacher,
)

CYCLE_YEAR = 2027


def teacher(
    tid: str,
    *,
    repeater: bool = False,
    incumbent: str | None = None,
    gender: SlotGender = None,
) -> Teacher:
    """A teacher who submitted in international round 1 only.

    A repeater's incumbent course is both their prior and their incumbent course (rules 0 and 4
    read incumbent_course_id). A non-repeater has neither.
    """
    if incumbent is not None and not repeater:
        raise ValueError("only a repeater has an incumbent course")
    return Teacher(
        cycle=CYCLE_YEAR,
        teacher_id=tid,
        is_repeater=repeater,
        prior_course_id=incumbent,
        incumbent_course_id=incumbent,
        submitted_intl_r1=True,
        submitted_intl_r2=False,
        submitted_sg=False,
        slot_genders_ranked=None,
        gender=gender,
    )


def course(cid: str, lo: int = 2, hi: int = 2, kind: CourseType = "intl") -> Course:
    """An offered course that ran, with lo..hi sponsors, no requirements and no gender slots."""
    return Course(
        cycle=CYCLE_YEAR,
        course_id=cid,
        course_type=kind,
        in_offerings=True,
        ran=True,
        country=None,
        requires=(),
        min_sponsors=lo,
        max_sponsors=hi,
        male_slots=0,
        female_slots=0,
    )


def cycle(
    prefs: list[tuple], courses: list[Course], extra: tuple[Teacher, ...] = ()
) -> Cycle:
    """A cycle from (teacher, course, rank) prefs, each optionally followed by a round.

    The round defaults to intl_r1. Teachers are everyone in prefs plus extra, sorted by ID; a
    teacher in both keeps the extra record (e.g. a repeater who also ranked).
    """
    by_id = {p[0]: teacher(p[0]) for p in prefs}
    by_id.update({t.teacher_id: t for t in extra})
    return Cycle(
        tuple(by_id[tid] for tid in sorted(by_id)),
        tuple(courses),
        tuple(
            Preference(
                CYCLE_YEAR, p[0], p[3] if len(p) > 3 else "intl_r1", p[2], p[1], None
            )
            for p in prefs
        ),
    )
