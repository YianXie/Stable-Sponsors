from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

CourseType = Literal["intl", "sg"]
SlotGender = Literal["male", "female"] | None


@dataclass(frozen=True)
class Teacher:
    """A class representing a teacher in the Stable Sponsors system.

    Attributes:
        cycle (int): The school year the teacher is selecting for.
        teacher_id (str): The unique identifier for the teacher.
        is_repeater (bool): Indicates if the teacher is a repeater.
        prior_course_id (str | None): The ID of the prior course, if any.
        incumbent_course_id (str | None): The ID of the incumbent course, if any.
        submitted_intl_r1 (bool): Indicates if the teacher submitted his/her preferences in the first international round.
        submitted_intl_r2 (bool): Indicates if the teacher submitted his/her preferences in the second international round.
        submitted_sg (bool): Indicates if the teacher submitted his/her preferences in the Singapore round.
        slot_genders_ranked (SlotGender | None): The genders of the slots ranked by the teacher, if any.
        qualifications (tuple[str, ...]): The qualifications of the teacher, if any.
        gender (SlotGender | None): The gender of the teacher, if any.
    """

    # From teachers.csv
    cycle: int
    teacher_id: str
    is_repeater: bool
    prior_course_id: str | None
    incumbent_course_id: str | None
    submitted_intl_r1: bool
    submitted_intl_r2: bool
    submitted_sg: bool
    slot_genders_ranked: SlotGender | None

    # From teacher_params.csv
    qualifications: tuple[str, ...] = ()
    gender: SlotGender | None = None


@dataclass(frozen=True)
class Course:
    """A class representing a course in the Stable Sponsor system

    Attributes:
        cycle (int): The school year the course is offered in.
        course_id (str): The unique identifier for the course.
        course_type (CourseType): The type of the course ("intl" or "sg").
        in_offerings (bool): Indicates if the course is in the offering list.
        ran (bool): Indicates if the course will be run.
        country (str): The host country where the course is offered, or none if the course is domestic in Singapore.
        requires (tuple[str, ...]): The qualifications required for the course.
        min_sponsors (int | None): The minimum number of sponsors required for the course, or none if unspecified.
        max_sponsors (int | None): The maximum number of sponsors allowed for the course, or none if unspecified.
        male_slots (int | None): The number of male slots needed for the course, or none if unspecified.
        female_slots (int | None): The number of female slots needed for the course, or none if unspecified.
    """

    # From courses.csv
    cycle: int
    course_id: str
    course_type: CourseType
    in_offerings: bool
    ran: bool
    country: str | None

    # From course_params.csv
    requires: tuple[str, ...] = ()
    min_sponsors: int | None = None
    max_sponsors: int | None = None
    male_slots: int | None = None
    female_slots: int | None = None


@dataclass(frozen=True)
class Preference:
    """A class representing a teacher's preference for a course.

    Attributes:
        cycle (int): The school year the preference is for.
        teacher_id (str): The unique identifier for the teacher.
        round_id (str): The round of the preference (e.g., "intl_r1", "intl_r2", "sg").
        rank (int): The rank of the course in the teacher's preference list.
        course_id (str): The unique identifier for the course.
        slot_gender (SlotGender | None): The gender of the course slot, or none if
    """

    cycle: int
    teacher_id: str
    round_id: str
    rank: int
    course_id: str
    slot_gender: SlotGender


@dataclass(frozen=True)
class Cycle:
    """A class representing a cycle of teacher-course preferences.

    Attributes:
        teachers (tuple[Teacher, ...]): A tuple of Teacher objects representing the teachers in the cycle.
        courses (tuple[Course, ...]): A tuple of Course objects representing the courses in the cycle.
        preferences (tuple[Preference, ...]): A tuple of Preference objects representing the preferences
    """

    teachers: tuple[Teacher, ...]
    courses: tuple[Course, ...]
    preferences: tuple[Preference, ...]


@dataclass(frozen=True)
class ObservedPlacement:
    """A class representing an observed placement of a teacher in a course.

    Attributes:
        cycle (int): The school year the placement is for.
        course_id (str): The unique identifier for the course.
        sponsor_slot (int): The sponsor slot number for the placement.
        teacher_id (str): The unique identifier for the teacher.
    """

    cycle: int
    course_id: str
    sponsor_slot: int
    teacher_id: str


def _bool(v: Any) -> bool:
    """Convert a value to a boolean.

    Args:
        v (Any): The value to convert to a boolean.

    Raises:
        ValueError: If the value cannot be converted to a boolean.

    Returns:
        bool: The boolean value.
    """

    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    s = str(v).strip().lower()
    if s in {"true", "1"}:
        return True
    if s in {"false", "0"}:
        return False
    raise ValueError(f"not a boolean: {v!r}")


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV, stripping padding around headers and cells; blank cells become NaN.

    Args:
        path (Path): The path to the CSV file.

    Returns:
        pd.DataFrame: The DataFrame containing the CSV data with stripped headers and cells, and blank cells replaced with NaN.
    """

    df = pd.read_csv(path, dtype=str, skipinitialspace=True)
    df.columns = df.columns.str.strip()
    return df.apply(lambda col: col.str.strip()).replace("", np.nan)


def resolve_incumbency(
    teachers: tuple[Teacher, ...], courses: tuple[Course, ...], path: Path
) -> tuple[Teacher, ...]:
    """Map each repeater's prior course (prior-year code) to this year's code.

    Course codes are per-year: the same trip can change code, and the same code
    can mean a different trip. The lineage file is the only bridge. A repeater
    with no lineage row is an error, never a fallback to "same code", because
    that fallback is exactly how the bug this guards against happened.

    Lineage CSV columns: prior_course_id, course_id (blank = discontinued),
    plus optional cycle (the target year) and prior_cycle, basis, status, note.

    Args:
        teachers (tuple[Teacher, ...]): teachers of a single cycle.
        courses (tuple[Course, ...]): this cycle's courses, to validate targets.
        path (Path): the lineage CSV.

    Raises:
        ValueError: missing columns, duplicate rows, a target not in this cycle,
            or a repeater whose prior course has no lineage row.

    Returns:
        tuple[Teacher, ...]: teachers with incumbent_course_id set for repeaters
            (None when their prior course was discontinued).
    """

    df = _read_csv(path)
    missing = {"prior_course_id", "course_id"} - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} is missing columns {sorted(missing)}")
    if "cycle" in df.columns:
        df = df[df["cycle"].astype(int).isin({t.cycle for t in teachers})]

    dupes = sorted(set(df.loc[df["prior_course_id"].duplicated(), "prior_course_id"]))
    if dupes:
        raise ValueError(f"{path.name} has more than one row for {dupes}")

    lineage: dict[str, str | None] = {
        str(r.prior_course_id): (None if pd.isna(r.course_id) else str(r.course_id))
        for r in df.itertuples()
    }
    course_ids = {c.course_id for c in courses}
    unknown = sorted(
        v for v in lineage.values() if v is not None and v not in course_ids
    )
    if unknown:
        raise ValueError(f"{path.name} maps to courses not in this cycle: {unknown}")

    out = []
    for t in teachers:
        if t.is_repeater:
            if t.prior_course_id not in lineage:
                raise ValueError(
                    f"{t.teacher_id}: no lineage row for prior course {t.prior_course_id}"
                )
            t = replace(t, incumbent_course_id=lineage[t.prior_course_id])
        out.append(t)
    return tuple(out)


def load_teachers(
    path: Path,
) -> tuple[Teacher, ...]:
    """Reads teacher data from a CSV file and returns a list of Teacher objects.

    Args:
        path (Path): The path to the CSV file containing teacher data.

    Returns:
        tuple[Teacher, ...]: A tuple of Teacher objects representing the teachers in the CSV file.
    """

    teachers_df = _read_csv(path)

    teachers_list = []
    for _, row in teachers_df.iterrows():
        teachers_list.append(
            Teacher(
                cycle=int(row["cycle"]),
                teacher_id=str(row["teacher_id"]),
                is_repeater=_bool(row["is_repeater"]),
                prior_course_id=str(row["prior_course_id"])
                if pd.notna(row["prior_course_id"])
                else None,
                incumbent_course_id=None,  # This will be resolved later using resolve_incumbency
                submitted_intl_r1=_bool(row["submitted_intl_r1"]),
                submitted_intl_r2=_bool(row["submitted_intl_r2"]),
                submitted_sg=_bool(row["submitted_sg"]),
                slot_genders_ranked=row["slot_genders_ranked"]
                if pd.notna(row["slot_genders_ranked"])
                else None,
            )
        )

    return tuple(teachers_list)


def load_courses(path: Path) -> tuple[Course, ...]:
    """Reads course data from a CSV file and returns a list of Course objects.

    Args:
        path (Path): The path to the CSV file containing course data.

    Returns:
        tuple[Course, ...]: A tuple of Course objects representing the courses in the CSV file.
    """

    df = _read_csv(path)
    courses_list = []

    for _, row in df.iterrows():
        courses_list.append(
            Course(
                cycle=int(row["cycle"]),
                course_id=str(row["course_id"]),
                course_type=row["course_type"],
                in_offerings=_bool(row["in_offerings"]),
                ran=_bool(row["ran"]),
                country=row["country"] if pd.notna(row["country"]) else None,
            )
        )

    return tuple(courses_list)


def load_preferences(path: Path) -> tuple[Preference, ...]:
    """Reads preference data from a CSV file and returns a list of Preference objects.

    Args:
        path (Path): The path to the CSV file containing preference data.

    Returns:
        tuple[Preference, ...]: A tuple of Preference objects representing the preferences in the CSV file.
    """

    df = _read_csv(path)
    preferences_list = []

    for _, row in df.iterrows():
        preferences_list.append(
            Preference(
                cycle=int(row["cycle"]),
                teacher_id=str(row["teacher_id"]),
                round_id=str(row["round"]),
                rank=int(row["rank"]),
                course_id=str(row["course_id"]),
                slot_gender=row["slot_gender"]
                if pd.notna(row["slot_gender"])
                else None,
            )
        )

    return tuple(preferences_list)


def load_teacher_params(
    path: Path, teachers: tuple[Teacher, ...]
) -> tuple[Teacher, ...]:
    """Reads teacher parameter data from a CSV file and returns a list of Teacher objects with updated qualifications and gender.

    Args:
        path (Path): The path to the CSV file containing teacher parameter data.
        teachers (tuple[Teacher, ...]): A tuple of Teacher objects to be enriched with qualifications and gender from the CSV file.

    Returns:
        tuple[Teacher, ...]: A tuple of Teacher objects with updated qualifications and gender.
    """

    df = _read_csv(path)
    df = df[df["cycle"].astype(int) == teachers[0].cycle]

    enriched_teachers = []
    for teacher in teachers:
        if not teacher.teacher_id in df["teacher_id"].values:
            raise ValueError(
                f"Teacher ID {teacher.teacher_id} not found in teacher_params.csv."
            )
        teacher_qualifications = df.loc[
            df["teacher_id"] == teacher.teacher_id, "qualifications"
        ].item()
        teacher_gender = df.loc[df["teacher_id"] == teacher.teacher_id, "gender"].item()
        if pd.notna(teacher_qualifications):
            qualifications = tuple(
                str(q).strip()
                for q in teacher_qualifications.strip().split(";")
                if pd.notna(q)
            )
            teacher = replace(teacher, qualifications=qualifications)
        if pd.notna(teacher_gender):
            teacher = replace(teacher, gender=teacher_gender.strip())
        enriched_teachers.append(teacher)

    return tuple(enriched_teachers)


def load_course_params(path: Path, courses: tuple[Course, ...]) -> tuple[Course, ...]:
    """Reads course parameter data from a CSV file and returns a list of Course objects with updated requirements, minimum and maximum sponsors, and male and female slots.

    Args:
        path (Path): The path to the CSV file containing course parameter data.
        courses (tuple[Course, ...]): A tuple of Course objects to be enriched with parameter data from the CSV file.

    Raises:
        ValueError: If a course ID is not found in the CSV file.

    Returns:
        tuple[Course, ...]: A tuple of Course objects with updated parameter data.
    """

    df = _read_csv(path)
    df = df[df["cycle"].astype(int) == courses[0].cycle]

    enriched_courses = []
    for course in courses:
        if not course.course_id in df["course_id"].values:
            raise ValueError(
                f"Course ID {course.course_id} not found in course_params.csv."
            )
        course_requires = df.loc[df["course_id"] == course.course_id, "requires"].item()
        if isinstance(course_requires, str):
            course_requires = tuple(
                str(r).strip()
                for r in course_requires.strip().split(";")
                if pd.notna(r)
            )
        else:
            course_requires = ()
        min_sponsors = df.loc[
            df["course_id"] == course.course_id, "min_sponsors"
        ].item()
        max_sponsors = df.loc[
            df["course_id"] == course.course_id, "max_sponsors"
        ].item()
        course_male_slots = df.loc[
            df["course_id"] == course.course_id, "male_slots"
        ].item()
        course_female_slots = df.loc[
            df["course_id"] == course.course_id, "female_slots"
        ].item()
        course = replace(
            course,
            requires=course_requires,
            min_sponsors=int(min_sponsors.strip()) if pd.notna(min_sponsors) else None,
            max_sponsors=int(max_sponsors.strip()) if pd.notna(max_sponsors) else None,
            male_slots=int(course_male_slots.strip())
            if pd.notna(course_male_slots)
            else None,
            female_slots=int(course_female_slots.strip())
            if pd.notna(course_female_slots)
            else None,
        )
        enriched_courses.append(course)

    return tuple(enriched_courses)


def load_observed_placements(path: Path, cycle: Cycle) -> tuple[ObservedPlacement, ...]:
    """Reads observed placement data from a CSV file and returns a list of ObservedPlacement objects.

    Args:
        path (Path): The path to the CSV file containing observed placement data.
        cycle (Cycle): The Cycle object to which the observed placements belong.

    Returns:
        tuple[ObservedPlacement, ...]: A tuple of ObservedPlacement objects representing the observed placements in the CSV file.
    """

    df = _read_csv(path)
    placements_list: list[ObservedPlacement] = []

    for _, row in df.iterrows():
        placements_list.append(
            ObservedPlacement(
                cycle=int(row["cycle"]),
                course_id=str(row["course_id"]),
                sponsor_slot=int(row["sponsor_slot"]),
                teacher_id=str(row["teacher_id"]),
            )
        )

    teachers = cycle.teachers
    courses = cycle.courses
    placements = tuple(placements_list)

    teacher_ids = {teacher.teacher_id for teacher in teachers}
    course_ids = {course.course_id for course in courses}

    # Test at most one placement row per teacher
    placement_teacher_ids = {placement.teacher_id for placement in placements}
    if len(placement_teacher_ids) != len(placements):
        raise ValueError("Duplicate teacher IDs found in placements.")

    # Test no duplicate teacher_id in teachers and no duplicate course ID in courses
    if len(teacher_ids) != len(teachers):
        raise ValueError("Duplicate teacher IDs found in teachers.")
    if len(course_ids) != len(courses):
        raise ValueError("Duplicate course IDs found in courses.")

    # Test every placement’s teacher_id and course_id exists
    for placement in placements:
        if placement.teacher_id not in teacher_ids:
            raise ValueError(
                f"Teacher ID {placement.teacher_id} in placements not found in teachers."
            )
        if placement.course_id not in course_ids:
            raise ValueError(
                f"Course ID {placement.course_id} in placements not found in courses."
            )

    # Test no two placements share the same (course_id, sponsor_slot)
    placement_pairs = {
        (placement.course_id, placement.sponsor_slot) for placement in placements
    }
    if len(placement_pairs) != len(placements):
        raise ValueError(
            "Duplicate (course_id, sponsor_slot) pairs found in placements."
        )

    return placements


def validate_cycle(cycle: Cycle) -> None:
    """Validates the integrity of a Cycle object and its associated observed placements.

    Args:
        cycle (Cycle): The Cycle object to validate.
        observed_placements (tuple[ObservedPlacement]): A tuple of observed placements to validate against the cycle.

    Raises:
        ValueError: If any validation check fails.
    """

    teachers = cycle.teachers
    courses = cycle.courses
    preferences = cycle.preferences

    # Test every teacher id appeared in preferences is in teachers
    teacher_ids = {teacher.teacher_id for teacher in teachers}
    for preference in preferences:
        if preference.teacher_id not in teacher_ids:
            raise ValueError(
                f"Teacher ID {preference.teacher_id} in preferences not found in teachers."
            )

    # Test every course id appeared in preferences is in courses
    course_ids = {course.course_id for course in courses}
    for preference in preferences:
        if preference.course_id not in course_ids:
            raise ValueError(
                f"Course ID {preference.course_id} in preferences not found in courses."
            )

    # Test course_type is in {"intl", "sg"}
    for course in courses:
        if course.course_type not in {"intl", "sg"}:
            raise ValueError(
                f"Course ID {course.course_id} has invalid course_type {course.course_type}."
            )

    # Test slot_gender is in {"male", "female", None}
    for preference in preferences:
        if preference.slot_gender not in {"male", "female", None}:
            raise ValueError(
                f"Preference for teacher ID {preference.teacher_id} and course ID {preference.course_id} has invalid slot_gender {preference.slot_gender}."
            )

    # Test is_repeater implies prior_course_id is not None
    for teacher in teachers:
        if teacher.is_repeater and teacher.prior_course_id is None:
            raise ValueError(
                f"Teacher ID {teacher.teacher_id} is a repeater but has no prior course ID."
            )

    # Test submitted_intl_r1 agrees with whether an intl_r1 ranking exists, and likewise for the other rounds
    for teacher in teachers:
        intl_r1_rankings = [
            pref
            for pref in preferences
            if pref.teacher_id == teacher.teacher_id and pref.round_id == "intl_r1"
        ]
        intl_r2_rankings = [
            pref
            for pref in preferences
            if pref.teacher_id == teacher.teacher_id and pref.round_id == "intl_r2"
        ]
        sg_rankings = [
            pref
            for pref in preferences
            if pref.teacher_id == teacher.teacher_id and pref.round_id == "sg"
        ]

        if teacher.submitted_intl_r1 != (len(intl_r1_rankings) > 0):
            raise ValueError(
                f"Teacher ID {teacher.teacher_id} submitted_intl_r1 does not match the existence of intl_r1 rankings."
            )
        if teacher.submitted_intl_r2 != (len(intl_r2_rankings) > 0):
            raise ValueError(
                f"Teacher ID {teacher.teacher_id} submitted_intl_r2 does not match the existence of intl_r2 rankings."
            )
        if teacher.submitted_sg != (len(sg_rankings) > 0):
            raise ValueError(
                f"Teacher ID {teacher.teacher_id} submitted_sg does not match the existence of sg rankings."
            )

    # The round values are exactly {"intl_r1", "intl_r2", "sg"}
    valid_rounds = {"intl_r1", "intl_r2", "sg"}
    for preference in preferences:
        if preference.round_id not in valid_rounds:
            raise ValueError(
                f"Preference round_id {preference.round_id} is not one of the valid rounds: {valid_rounds}."
            )


def load_cycle(
    base: Path,
    params_dir: Path | None = None,
    cycle: int | None = None,
    lineage_path: Path | None = None,
) -> Cycle:
    """Loads a cycle of teacher-course preferences from CSV files in the specified directory.

    Args:
        base (Path): The base path to the directory containing the CSV files.
        params_dir (Path | None, optional): An optional path to the directory containing parameter CSV files. If not provided, it defaults to the base path.
        cycle (int | None, optional): Keep only rows for this cycle. derived/ holds every cycle in the same files, so pass this for real data. None keeps all rows (fine for single-cycle fixtures).
        lineage_path (Path | None, optional): The prior-year -> this-year course lineage CSV. Defaults to params_dir / "course_lineage.csv".

    Returns:
        Cycle: An instance of the Cycle class containing teachers, courses, and preferences.

    Raises:
        ValueError: If any validation check fails during the loading of the cycle.
    """

    params_dir = params_dir or base

    if not base.exists() or not base.is_dir():
        raise ValueError(
            f"The specified base path '{base}' does not exist or is not a directory."
        )

    teachers = load_teachers(base / "teachers.csv")
    courses = load_courses(base / "courses.csv")
    preferences = load_preferences(base / "preferences.csv")

    if cycle is not None:
        teachers = tuple(t for t in teachers if t.cycle == cycle)
        courses = tuple(c for c in courses if c.cycle == cycle)
        preferences = tuple(p for p in preferences if p.cycle == cycle)

    # Resolve after filtering: lineage maps one prior year into one target year.
    teachers = resolve_incumbency(
        teachers, courses, lineage_path or params_dir / "course_lineage.csv"
    )
    teachers = load_teacher_params(params_dir / "teacher_params.csv", teachers)
    courses = load_course_params(params_dir / "course_params.csv", courses)

    result = Cycle(teachers=teachers, courses=courses, preferences=preferences)
    validate_cycle(result)

    return result
