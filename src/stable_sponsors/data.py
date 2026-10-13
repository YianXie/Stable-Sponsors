from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

CourseType = Literal["intl", "sg"]
SlotGender = Literal["male", "female"] | None


@dataclass(frozen=True)
class Teacher:
    """A class representing a teacher in the Stable Sponsors system.

    Attributes:
        cycle (int): The school year the teacher is selecting for.
        id (str): The unique identifier for the teacher.
        is_repeater (bool): Indicates if the teacher is a repeater.
        prior_course_id (str | None): The ID of the prior course, if any.
        submitted_intl_r1 (bool): Indicates if the teacher submitted his/her preferences in the first international round.
        submitted_intl_r2 (bool): Indicates if the teacher submitted his/her preferences in the second international round.
        submitted_sg (bool): Indicates if the teacher submitted his/her preferences in the Singapore round.
        slot_genders_ranked (SlotGender | None): The genders of the slots ranked by the teacher, if any.
    """

    cycle: int
    teacher_id: str
    is_repeater: bool
    prior_course_id: str | None
    submitted_intl_r1: bool
    submitted_intl_r2: bool
    submitted_sg: bool
    slot_genders_ranked: SlotGender | None


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
    """

    cycle: int
    course_id: str
    course_type: CourseType
    in_offerings: bool
    ran: bool
    country: str | None


@dataclass(frozen=True)
class Preference:
    """A class representing a teacher's preference for a course."""

    cycle: int
    teacher_id: str
    round_id: str
    rank: int
    course_id: str
    slot_gender: SlotGender


@dataclass(frozen=True)
class Cycle:
    """A class representing a cycle of teacher-course preferences."""

    teachers: tuple[Teacher, ...]
    courses: tuple[Course, ...]
    preferences: tuple[Preference, ...]


@dataclass(frozen=True)
class ObservedPlacement:
    """A class representing an observed placement of a teacher in a course."""

    cycle: int
    course_id: str
    sponsor_slot: int
    teacher_id: str


def _bool(v) -> bool:
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    s = str(v).strip().lower()
    if s in {"true", "1"}:
        return True
    if s in {"false", "0"}:
        return False
    raise ValueError(f"not a boolean: {v!r}")


def load_teachers(
    path: Path,
) -> tuple[Teacher, ...]:
    """Reads teacher data from a CSV file and returns a list of Teacher objects.

    Args:
        path (Path): The path to the CSV file containing teacher data.

    Returns:
        tuple[Teacher, ...]: A tuple of Teacher objects representing the teachers in the CSV file.
    """

    teachers_df = pd.read_csv(path)

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

    df = pd.read_csv(path)
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

    df = pd.read_csv(path)
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


def load_observed_placements(path: Path, cycle: Cycle) -> tuple[ObservedPlacement, ...]:
    """Reads observed placement data from a CSV file and returns a list of ObservedPlacement objects.

    Args:
        path (Path): The path to the CSV file containing observed placement data.
        cycle (Cycle): The Cycle object to which the observed placements belong.

    Returns:
        tuple[ObservedPlacement, ...]: A tuple of ObservedPlacement objects representing the observed placements in the CSV file.
    """

    df = pd.read_csv(path)
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


def load_cycle(base: Path) -> Cycle:
    """Loads a cycle of teacher-course preferences from CSV files in the specified directory.

    Args:
        base (Path): The base path to the directory containing the CSV files.

    Returns:
        Cycle: An instance of the Cycle class containing teachers, courses, and preferences.
    """

    teachers = load_teachers(base / "teachers.csv")
    courses = load_courses(base / "courses.csv")
    preferences = load_preferences(base / "preferences.csv")
    cycle = Cycle(teachers=teachers, courses=courses, preferences=preferences)

    validate_cycle(cycle)

    return cycle
