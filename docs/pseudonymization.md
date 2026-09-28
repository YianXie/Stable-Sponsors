# Interim sponsor allocation: pseudonymisation pipeline

Turns the office's spreadsheets (2026 and 2027 cycles) into a pseudonymous
dataset keyed by `T###` teacher IDs and trip codes. Two stages with a human
review in between, because the identity join is a judgment call and a wrong
link becomes a false RQ1 residual.

```
pip install pandas openpyxl pyyaml pytest

cp config/pseudonymize.example.yaml config/pseudonymize.yaml    # gitignored; set private_root

python tools/make_synthetic.py --out ~/interim-synthetic          # optional dry run on fake data
pytest -q                                                          # includes an end-to-end run on fake data

python src/build_crosswalk.py                  # stage 1: writes three drafts under key/
#   review key/identity_draft.csv, course_alias_draft.csv, course_catalogue_draft.csv
#   fix what is wrong, set confirmed=y on every row
python src/build_crosswalk.py --accept         # promotes drafts to key/*.csv
python src/apply_pseudonymization.py           # stage 2: writes derived/
pytest -q                                      # leakage tests now run against your derived/
```

Console output from every script contains only counts, spreadsheet row numbers,
trip codes and `T###` IDs, so it is safe to paste into a chat. The CSVs under
`key/` and `freetext/` are not.

## Layout

```
repo (public)              code, config/*.example.yaml, tests. No data.
~/interim-private/
    raw/2026/ raw/2027/    files as received from the office
    key/                   identity.csv, course_alias.csv, course_catalogue.csv (+ drafts, backups)
    derived/               teachers, preferences, placements, courses, checks, manifest.json
    freetext/<cycle>/      one file per teacher per free-text answer + coding_sheet.csv
```

`private_root` and `raw_dir` are refused if they resolve inside the repo.

## Reviewing the drafts

Edit the `*_draft.csv` files, never `identity.csv` and friends: the drafts are
what every rerun reads, and stage 2 warns if they hold edits you have not accepted.

**identity_draft.csv**: one row per email address or distinct name. Rows sharing a
`teacher_id` are one person across both cycles. Sorted worst first.
To split a wrong merge, set `teacher_id` to `NEW` (or `NEW1`, `NEW2`… for several
different new people); a fresh unused ID is assigned. To merge, copy the other
person's ID. Any row whose `teacher_id` differs from `proposed_id` needs a note
saying why, or `--accept` refuses; that is what stops a typo from silently
merging two teachers. People you have separated are never re-merged by a rerun.
Flags that need a decision:

| flag                 | meaning                                                                                                                                                                                                       |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LOW_MARGIN           | another person scored almost as well (e.g. `dkim@` vs `dkim2@`)                                                                                                                                               |
| WEAK_LINK            | the link rests on a weak or fuzzy email match                                                                                                                                                                 |
| MULTI_NAME           | several spellings merged (Marty / Martin, with or without a middle initial)                                                                                                                                   |
| NEAR_MISS            | left alone, but a candidate was refused; check it is really a separate person                                                                                                                                 |
| PLACED_NO_EMAIL      | placed in 2027 but no 2027 form links to them                                                                                                                                                                 |
| NO_NAME              | submitted a form but never linked to a placement                                                                                                                                                              |
| CROSS_CYCLE_LINK     | email seen only in one cycle, name only in the other                                                                                                                                                          |
| TWO_SLOTS_SAME_CYCLE | one name fills two sponsor slots in one cycle                                                                                                                                                                 |
| PLACED_OFF_LIST      | placed on a course that is on none of their own lists: check the link first (an unplaced `qzhou@` linked to a different, unresponsive Q. Zhou looks exactly like this); if it is right, it is a residual case |

`NO_EMAIL` alone is expected: 2026 had no repeat file, so 2026 repeaters appear
only on the placement sheet.

**course_alias_draft.csv**: every course string -> `course_id`. `course_id` is the
trip code for courses that ran and `NR-xxxxxx` for offered courses that did not
run. Upper-case methods need a decision.

- 2026 offerings carry a trip code for courses that ran (`code_col`), so they join
  placements by code: `code_match`; `CODE_MATCH_NAMES_DIFFER` (same code, different
  names: check the code); `CODE_NOT_IN_PLACEMENTS` (has a code, no placement row);
  `NO_CODE_BUT_IN_PLACEMENTS` (blank code, yet its exact name is on the placement
  sheet). A blank code is never joined by a similar name or by country.
- 2027 offerings have no codes and join by name: `GEO_HINT` means the placement
  name shares only the country or city with the offering name.
- `GUESS_MISSING_SG_COURSE`: the one Singapore-form string that matches no course,
  proposed for the one listed Singapore code with no placement row (SING-9 in 2026).
  Confirm it only if the office agrees it names that course.

- Form options such as `Nepal Trek (MALE)` / `Nepal Trek (FEMALE)` name the course
  plus the open sponsor slot (every course needs at least one male and one female
  sponsor). The tag is ignored for matching, so both variants share one alias row,
  and kept as `slot_gender` in `preferences.csv`. `teachers.csv` gets
  `slot_genders_ranked`; a teacher who picked both kinds of slot is listed in
  `checks.csv`. Only the bracketed full words count, never "- Male".

`LOCK_CONFLICT` means something you confirmed earlier now disagrees with an exact
match in the data (e.g. a "did not run" course now appears in placements) and has
been unconfirmed. Set `course_id` to `NONE` for a
string that is not a course (the preference is dropped and logged).

**course_catalogue_draft.csv**: one row per course per cycle with its type and `ran`
(`y`, `n`, or `unknown`). Where `expected_sg_codes` is set (2026: SING-1 to SING-12),
that list decides which courses are Singapore; a listed code with no placement row
gets `ran = unknown` and `MISSING_FROM_PLACEMENTS`, and a Singapore-looking course
not on the list gets `SG_BUT_NOT_IN_SG_LIST`. Without a list (2027), courses missing
from the offerings are classed as Singapore; if the count differs from
`expected_sg_courses`, an international course probably failed to join its
offering, so look at `ASSUMED_SG` rows.

When the office answers about a course with `ran = unknown`: if it did not run, add
its code to that cycle's `not_run_codes` in the config; if it ran, get the corrected
placement sheet. Either way, rerun stage 1.

## Rules baked in

- **Random IDs, stored only in the key.** IDs come from a system RNG, not a seed,
  so they cannot be regenerated from the public faculty list. Rerunning stage 1
  never renumbers anyone: confirmed rows are locks, unconfirmed rows are hints.
- **Unknown is not "no".** 2026 has no repeat file and no round 2, so those
  columns are empty for 2026, not `False`; likewise `courses.ran` is empty for a
  course whose trip code is known but that has no placement row.
- **Nothing is imputed.** Blank or placeholder sponsor cells stay as
  `blank_in_source` / `placeholder_in_source`. Stage 2 refuses to write
  anything if a single raw email, name or course string is not covered by the key.
- **Extra-sponsor rows.** A placement row with sponsors but no code or name
  (merged cells) belongs to the course above; so does a repeated trip code.
- **Duplicate submissions** keep the last row by default (`duplicate_submissions`).
- **Free text never reaches `derived/`.** Hand-code it in `freetext/coding_sheet.csv`;
  rebuilds merge into that sheet instead of overwriting it.
- **Checks are questions, not fixes.** `derived/checks.csv` lists things such as a
  repeater placed on a different course, or a 2027 prior course that is not the
  teacher's 2026 placement (often a renumbered trip code). Take them to the office.

## Tests

`tests/test_matching.py` covers the matching rules. `tests/test_pipeline_synthetic.py`
generates a fake two-cycle dataset with the real files' exact headers, scores every
proposed identity and course link against ground truth, requires every unflagged
proposal to be correct, then checks the derived tables, rerun stability, and leakage.
`tests/test_leakage.py` runs against your real `derived/` once it exists.
