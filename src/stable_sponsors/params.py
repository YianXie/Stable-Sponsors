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

To apply a drafting change to rows that already exist, name the columns:

    uv run python -m stable_sponsors.params --cycle 2027 --refresh-cols gender male_slots female_slots

Only those columns change, plus the `gender:` note in `source`. Refreshing `gender` overwrites a
gender entered by hand, so don't refresh it once the office's data is in.
"""

import argparse
from pathlib import Path

import pandas as pd

from stable_sponsors.data import read_csv
from stable_sponsors.pseudonymize.idmap import DEFAULT_CONFIG, load_config, out_path

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
    Gendered slots: 1 male + 1 female on every course (M-009, D-004). A form
    suffix on one gender only is flagged with CHECK. That's expected where a
    repeater holds the other slot, so it's information, not an error.
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
        male, female = 1, 1

        notes = [
            f"capacity: default {lo}-{hi} for {ctype}",
            "gender: 1M/1F per M-009 (reported)",
        ]
        if len(genders) == 1:
            notes.append(f"CHECK: form shows only {next(iter(genders))} slot")
        if cid not in ranked:
            notes.append("nobody ranked this course")
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


def infer_gender_from_form(slot_genders_ranked: str | None) -> tuple[str | None, str]:
    """(gender, note) from the (MALE)/(FEMALE) slot labels a teacher ranked.

    Both labels on one form are a conflict: gender stays blank and is flagged, never resolved by
    picking one. No label means unknown, not "no".
    """
    if slot_genders_ranked is None or pd.isna(slot_genders_ranked):
        return None, "gender: not yet received"
    labels = set(slot_genders_ranked.split("|"))
    if len(labels) > 1:
        return None, "CHECK: form has both slot labels; gender: not yet received"
    return next(iter(labels)), "gender: form slot label"


def draft_teacher_params(teachers: pd.DataFrame, cycle: str) -> pd.DataFrame:
    """One row per teacher in `cycle`, with qualifications blank and gender from the form.

    Qualifications come from hand-coding the free text. Gender comes from the form's slot label
    when there is exactly one (status `inferred`), else stays blank until the office supplies it.
    """
    teachers = _for_cycle(teachers, cycle)
    inferred = [infer_gender_from_form(v) for v in teachers["slot_genders_ranked"]]
    return pd.DataFrame(
        {
            "cycle": cycle,
            "teacher_id": teachers["teacher_id"].to_numpy(),
            "qualifications": "",
            "gender": [g or "" for g, _ in inferred],
            "source": [
                f"qualifications: not yet coded from freetext; {note}"
                for _, note in inferred
            ],
            "status": ["inferred" if g else "assumed" for g, _ in inferred],
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


def refresh_columns(
    existing: pd.DataFrame,
    draft: pd.DataFrame,
    id_col: str,
    cycle: str,
    cols: list[str],
) -> pd.DataFrame:
    """Overwrite `cols` with the draft's values for this cycle's rows; keep every other cell.

    A column the file doesn't have yet is added, blank for rows the draft doesn't cover.
    """
    out = existing.copy()
    rows = out["cycle"] == cycle
    for col in cols:
        if col not in out.columns:
            out[col] = ""
        values = draft.set_index(id_col)[col].astype(str)
        known = rows & out[id_col].isin(values.index)
        out.loc[known, col] = out.loc[known, id_col].map(values)
    return out


def _with_gender_note(source: str, draft_source: str) -> str:
    """`source` with its `gender:` note (and any CHECK flag) replaced by the draft's."""

    def is_gender(note: str) -> bool:
        return note.startswith(("gender:", "CHECK:"))

    kept = [n for n in source.split("; ") if not is_gender(n)]
    return "; ".join(kept + [n for n in draft_source.split("; ") if is_gender(n)])


def refresh_gender_source(
    existing: pd.DataFrame, draft: pd.DataFrame, id_col: str, cycle: str
) -> pd.DataFrame:
    """Keep provenance true after a refresh: update the `gender:` note in `source`.

    `status` moves only to `inferred`, the one status that describes the gender cell itself; a
    course row's status also covers its capacity, so it stays.
    """
    out = existing.copy()
    by_id = draft.set_index(id_col)
    for i, row in out[out["cycle"] == cycle].iterrows():
        if row[id_col] not in by_id.index:
            continue
        new = by_id.loc[row[id_col]]
        out.loc[i, "source"] = _with_gender_note(str(row["source"]), new["source"])
        if new["status"] == "inferred":
            out.loc[i, "status"] = "inferred"
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _write(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(path)  # atomic: a crash never leaves a half-written file


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--cycle", required=True)
    ap.add_argument("--intl", default="2,2", help="min,max sponsors for intl courses")
    ap.add_argument("--sg", default="2,2", help="min,max sponsors for sg courses")
    ap.add_argument(
        "--refresh-cols",
        nargs="*",
        default=[],
        metavar="COL",
        help="overwrite these columns on existing rows with the new draft; other cells are kept",
    )
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

    courses = read_csv(derived / "courses.csv")
    teachers = read_csv(derived / "teachers.csv")
    preferences = read_csv(derived / "preferences.csv")
    if args.cycle not in set(courses["cycle"]):
        raise SystemExit(f"cycle {args.cycle} not found in {derived / 'courses.csv'}")

    course_draft = draft_course_params(courses, preferences, args.cycle, capacity)
    teacher_draft = draft_teacher_params(teachers, args.cycle)
    jobs = [
        ("course_params.csv", "course_id", course_draft),
        ("teacher_params.csv", "teacher_id", teacher_draft),
    ]
    all_cols = set(course_draft.columns) | set(teacher_draft.columns)
    if set(args.refresh_cols) - all_cols:
        raise SystemExit(
            f"--refresh-cols: no such column {sorted(set(args.refresh_cols) - all_cols)}"
        )
    for name, id_col, draft in jobs:
        path = params_dir / name
        existing = read_csv(path) if path.exists() else None
        merged, added, orphans = merge_keep_existing(
            draft, existing, id_col, args.cycle
        )
        cols = [c for c in args.refresh_cols if c in draft.columns]
        if cols:
            merged = refresh_columns(merged, draft, id_col, args.cycle, cols)
            merged = refresh_gender_source(merged, draft, id_col, args.cycle)
            print(f"{path}: refreshed {cols}")
        _write(merged, path)
        print(f"{path}: {len(added)} new rows, {len(draft) - len(added)} kept as-is")
        if orphans:
            print(
                f"  WARNING: {len(orphans)} {id_col}s in file but not in derived/: {orphans}"
            )

    print("\ncourse summary (new drafts only matter; kept rows are yours):")
    print(
        f"  courses nobody ranked:      {course_draft['source'].str.contains('nobody ranked').sum()}"
    )
    one_sided = course_draft["source"].str.contains("form shows only")
    print(f"  form shows one slot only:   {one_sided.sum()}")
    flagged = course_draft.loc[
        course_draft["source"].str.contains("gendered slots"), "course_id"
    ].tolist()
    if flagged:
        print(f"  CHECK (gendered slots exceed max): {flagged}")

    # Counts only: never print a teacher's gender per ID.
    submitters = set(_for_cycle(preferences, args.cycle)["teacher_id"])
    blank = teacher_draft["gender"] == ""
    is_sub = teacher_draft["teacher_id"].isin(submitters)
    print("\nteacher gender from form labels:")
    print(f"  inferred male:              {(teacher_draft['gender'] == 'male').sum()}")
    print(
        f"  inferred female:            {(teacher_draft['gender'] == 'female').sum()}"
    )
    print(
        f"  conflicts (left blank):     {teacher_draft['source'].str.contains('both slot labels').sum()}"
    )
    print(f"  unknown, submitted a form:  {(blank & is_sub).sum()}")
    print(f"  unknown, no form:           {(blank & ~is_sub).sum()}")
    print(
        "\nNext: edit the files, then ask the office about every row still `assumed`."
    )


if __name__ == "__main__":
    main()
