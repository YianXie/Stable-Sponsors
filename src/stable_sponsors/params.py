"""Draft course_params.csv and teacher_params.csv for one cycle.

    uv run python -m stable_sponsors.params --cycle 2027

Reads only INPUT tables from private_root/derived/ (courses, teachers,
preferences). It never opens placements.csv: a parameter copied from what
actually happened would make reproduction succeed for a meaningless reason.

Writes to private_root/params/ (outside the repo, never inside derived/, so
re-running the pseudonymisation pipeline can't overwrite your hand edits).

Every value it fills in is a placeholder marked status=assumed, with a
`source` saying where it came from. Edit the rows by hand as the office
confirms things, changing status to confirmed or documented.

Re-running is safe: rows that already exist in the output file are kept
exactly as they are (your edits win). Only IDs that are missing get a new
draft row. IDs in the file that no longer exist in derived/ are reported,
never deleted.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from stable_sponsors.pseudonymize.idmap import load_config, out_path

COURSE_COLS = [
    "cycle",
    "course_id",
    "requires",
    "min_sponsors",
    "max_sponsors",
    "male_slots",
    "female_slots",
    "source",
    "status",
]
TEACHER_COLS = ["cycle", "teacher_id", "qualifications", "gender", "source", "status"]


def _read(path: Path) -> pd.DataFrame:
    """Same parsing as data._read_csv: strings, stripped, blanks -> NaN."""
    df = pd.read_csv(path, dtype=str, skipinitialspace=True)
    df.columns = df.columns.str.strip()
    return df.apply(lambda col: col.str.strip()).replace("", np.nan)


def _for_cycle(df: pd.DataFrame, cycle: str) -> pd.DataFrame:
    return df[df["cycle"] == cycle]


# --------------------------------------------------------------------------
# drafting (pure functions: tested on the toy cycle)
# --------------------------------------------------------------------------


def draft_course_params(
    courses: pd.DataFrame,
    preferences: pd.DataFrame,
    cycle: str,
    capacity: dict[str, tuple[int, int]],
) -> pd.DataFrame:
    """One row per course in `cycle`.

    Capacity: per-course-type default from `capacity`, e.g. {"intl": (2, 2)}.
    Gendered slots: 1 if any preference row for the course carries that
    (MALE)/(FEMALE) slot suffix, else 0. The suffix is input data (it was on
    the form teachers filled in), but reading it as a hard requirement is
    an assumption, so status stays `assumed`.
    Requirements: left blank. Nothing in the data says which courses need
    scuba etc.; that must come from the office or the procedure document.
    """
    courses = _for_cycle(courses, cycle)
    prefs = _for_cycle(preferences, cycle)

    gendered = (
        prefs.dropna(subset=["slot_gender"])
        .groupby("course_id")["slot_gender"]
        .agg(lambda s: set(s.str.lower()))
        .to_dict()
    )
    ranked = set(prefs["course_id"])

    rows = []
    for _, c in courses.iterrows():
        cid, ctype = c["course_id"], c["course_type"]
        if ctype not in capacity:
            raise ValueError(f"no default capacity for course_type {ctype!r} ({cid})")
        lo, hi = capacity[ctype]
        genders = gendered.get(cid, set())
        male, female = int("male" in genders), int("female" in genders)

        notes = [f"capacity: default {lo}-{hi} for {ctype}"]
        if genders:
            notes.append(f"gender: slot suffix on form ({', '.join(sorted(genders))})")
        elif cid not in ranked:
            notes.append("gender: nobody ranked this course, no suffix evidence")
        else:
            notes.append("gender: no slot suffix seen")
        if male + female > hi:
            notes.append(f"CHECK: {male + female} gendered slots > max {hi}")
        notes.append("requires: not yet known")

        rows.append(
            {
                "cycle": cycle,
                "course_id": cid,
                "requires": "",
                "min_sponsors": lo,
                "max_sponsors": hi,
                "male_slots": male,
                "female_slots": female,
                "source": "; ".join(notes),
                "status": "assumed",
            }
        )
    return pd.DataFrame(rows, columns=COURSE_COLS)


def draft_teacher_params(teachers: pd.DataFrame, cycle: str) -> pd.DataFrame:
    """One row per teacher in `cycle`, with qualifications and gender blank.

    Blank on purpose: qualifications come from hand-coding the free text, and
    gender from the office. Guessing either here would put an invented fact
    into the model with nothing marking it as invented.
    """
    teachers = _for_cycle(teachers, cycle)
    return pd.DataFrame(
        {
            "cycle": cycle,
            "teacher_id": teachers["teacher_id"].to_numpy(),
            "qualifications": "",
            "gender": "",
            "source": "qualifications: not yet coded from freetext; gender: not yet received",
            "status": "assumed",
        },
        columns=TEACHER_COLS,
    )


def merge_keep_existing(
    draft: pd.DataFrame, existing: pd.DataFrame | None, id_col: str, cycle: str
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Keep every existing row untouched; append drafts only for missing IDs.

    Returns (merged, added_ids, orphan_ids). Orphans are IDs present in the
    existing file for this cycle but absent from the draft; they're kept and
    reported, because deleting a hand-edited row silently loses work.
    """
    if existing is None or existing.empty:
        return draft, list(draft[id_col]), []

    missing_cols = set(draft.columns) - set(existing.columns)
    if missing_cols:
        raise SystemExit(
            f"existing file lacks columns {sorted(missing_cols)}; "
            "add them by hand or move the file aside and regenerate"
        )
    existing = existing[draft.columns].fillna("")
    have = set(existing.loc[existing["cycle"] == cycle, id_col])
    new = draft[~draft[id_col].isin(have)]
    orphans = sorted(have - set(draft[id_col]))
    return pd.concat([existing, new], ignore_index=True), list(new[id_col]), orphans


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _write(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(path)  # atomic: a crash never leaves a half-written file


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--config", default="config/pseudonymize.yaml")
    ap.add_argument("--cycle", required=True)
    ap.add_argument("--intl", default="2,2", help="min,max sponsors for intl courses")
    ap.add_argument("--sg", default="2,2", help="min,max sponsors for sg courses")
    args = ap.parse_args(argv)

    def pair(s: str) -> tuple[int, int]:
        lo, hi = (int(v) for v in s.split(","))
        if not 0 <= lo <= hi:
            raise SystemExit(f"bad capacity {s!r}: need 0 <= min <= max")
        return lo, hi

    capacity = {"intl": pair(args.intl), "sg": pair(args.sg)}

    cfg = load_config(args.config)
    derived = out_path(cfg, "derived")
    params_dir = out_path(cfg, "params")
    params_dir.mkdir(parents=True, exist_ok=True)

    courses = _read(derived / "courses.csv")
    teachers = _read(derived / "teachers.csv")
    preferences = _read(derived / "preferences.csv")
    if args.cycle not in set(courses["cycle"]):
        raise SystemExit(f"cycle {args.cycle} not found in {derived / 'courses.csv'}")

    jobs = [
        (
            "course_params.csv",
            "course_id",
            draft_course_params(courses, preferences, args.cycle, capacity),
        ),
        (
            "teacher_params.csv",
            "teacher_id",
            draft_teacher_params(teachers, args.cycle),
        ),
    ]
    for name, id_col, draft in jobs:
        path = params_dir / name
        existing = _read(path) if path.exists() else None
        merged, added, orphans = merge_keep_existing(
            draft, existing, id_col, args.cycle
        )
        _write(merged, path)
        print(f"{path}: {len(added)} new rows, {len(draft) - len(added)} kept as-is")
        if orphans:
            print(
                f"  WARNING: {len(orphans)} {id_col}s in file but not in derived/: {orphans}"
            )

    c = jobs[0][2]
    print("\ncourse summary (new drafts only matter; kept rows are yours):")
    print(f"  courses with a male slot:   {int(c['male_slots'].sum())}")
    print(f"  courses with a female slot: {int(c['female_slots'].sum())}")
    print(
        f"  courses nobody ranked:      {c['source'].str.contains('nobody ranked').sum()}"
    )
    flagged = c.loc[c["source"].str.contains("CHECK"), "course_id"].tolist()
    if flagged:
        print(f"  CHECK (gendered slots exceed max): {flagged}")
    print(
        "\nNext: edit the files, then ask the office about every row still `assumed`."
    )


if __name__ == "__main__":
    main()
