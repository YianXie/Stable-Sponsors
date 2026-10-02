"""Read one cycle's raw spreadsheets into plain records.

Both stages call load_cycle(), so they cannot disagree about what the raw data
says. Warnings produced here name files, columns, spreadsheet rows and trip
codes only, never a person, so console output is safe to share.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from stable_sponsors.idmap import (
    canon_header,
    is_null_pref,
    is_placeholder_sponsor,
    norm_course,
    norm_email,
    raw_path,
    read_sheet,
    resolve_col,
    sha256_file,
)

ROUNDS = {"intl_r1": "intl", "intl_r2": "intl", "sg": "sg"}
MULTI_NAME_RE = re.compile(r"\s(?:&|and|\+)\s|\s/\s|;|\n", re.I)


@dataclass
class Offering:
    name: str
    city: str
    country: str
    row: int
    code: str = ""  # trip code; only courses that ran have one (when configured)


@dataclass
class Response:
    round: str
    channel: str
    email: str  # normalised
    name: str  # raw, '' when the form has no name column
    ranks: list  # [(rank, raw string)], rank = column position 1..k
    freetext: dict  # {column: text}
    row: int


@dataclass
class Slot:
    code: str
    course_name: str
    slot: int
    sponsor: str  # raw, '' unless status == 'named'
    status: str  # named | blank_in_source | placeholder_in_source
    row: int


@dataclass
class Repeat:
    email: str
    prior_raw: str
    row: int


@dataclass
class Cycle:
    key: str
    offerings: list = field(default_factory=list)
    responses: list = field(default_factory=list)
    slots: list = field(default_factory=list)
    repeaters: list | None = None  # None: this cycle has no repeat file
    rounds: list = field(default_factory=list)
    extra_columns: list = field(default_factory=list)  # (round, column, values)
    warnings: list = field(default_factory=list)
    inputs: dict = field(default_factory=dict)  # relative path -> sha256
    expected_sg_courses: int | None = None
    expected_sg_codes: list | None = (
        None  # Singapore trip codes that should all be in placements
    )
    not_run_codes: list = field(
        default_factory=list
    )  # office-confirmed: listed but did not run
    offerings_have_codes: bool = False
    n_continuation_rows: int = 0


def _blank_row(r, cols) -> bool:
    return not any(r[c] for c in cols)


def _dedupe(rows, label, policy, warnings):
    by_email: dict[str, list] = {}
    for x in rows:
        by_email.setdefault(x.email, []).append(x)
    out = []
    for e, xs in by_email.items():
        if len(xs) == 1:
            out.append(xs[0])
            continue
        if policy == "error":
            raise SystemExit(
                f"{label}: {len(xs)} submissions from one address "
                f"(rows {[x.row for x in xs]}); duplicate_submissions=error"
            )
        keep = xs[-1] if policy == "last" else xs[0]
        warnings.append(
            f"{label}: {len(xs)} submissions from one address "
            f"(rows {', '.join(str(x.row) for x in xs)}); kept row {keep.row} ({policy})"
        )
        out.append(keep)
    return out


def load_cycle(cfg: dict, key: str) -> Cycle:
    spec = cfg["cycles"][key]
    cy = Cycle(
        key=key,
        expected_sg_courses=spec.get("expected_sg_courses"),
        expected_sg_codes=[str(c).strip() for c in spec["expected_sg_codes"]]
        if spec.get("expected_sg_codes")
        else None,
        not_run_codes=[str(c).strip() for c in spec.get("not_run_codes") or []],
    )
    policy = cfg["duplicate_submissions"]

    def read(sub):
        p = raw_path(cfg, sub["path"])
        df = read_sheet(p, sub.get("sheet"))
        cy.inputs[sub["path"]] = sha256_file(p)
        return df

    # ---- offerings (international list, including courses that did not run)
    o = spec.get("offerings")
    if o:
        df = read(o)
        lab = f"{key} offerings"
        cn = resolve_col(df, o["name_col"], lab)
        cc = resolve_col(df, o.get("city_col"), lab)
        ctry = resolve_col(df, o.get("country_col"), lab)
        kc = resolve_col(df, o.get("code_col"), lab)
        cy.offerings_have_codes = kc is not None
        seen, seen_code = {}, {}
        for i, r in df.iterrows():
            nm = r[cn]
            if is_null_pref(nm):
                if not _blank_row(r, df.columns):
                    cy.warnings.append(
                        f"{lab}: row {i + 2} has no course name; skipped"
                    )
                continue
            k = norm_course(nm)
            if k in seen:
                cy.warnings.append(
                    f"{lab}: row {i + 2} repeats the course on row {seen[k]}; skipped"
                )
                continue
            seen[k] = i + 2
            code = r[kc] if kc and not is_null_pref(r[kc]) else ""
            if code and code in seen_code:
                cy.warnings.append(
                    f"{lab}: row {i + 2} repeats trip code {code} from row "
                    f"{seen_code[code]}"
                )
            if code:
                seen_code.setdefault(code, i + 2)
            cy.offerings.append(
                Offering(nm, r[cc] if cc else "", r[ctry] if ctry else "", i + 2, code)
            )

    # ---- preference forms
    for p in spec.get("preferences") or []:
        rnd = p["round"]
        if rnd not in ROUNDS:
            raise SystemExit(
                f"{key}: unknown round {rnd!r}; use one of {sorted(ROUNDS)}"
            )
        if rnd in cy.rounds:
            raise SystemExit(f"{key}: round {rnd} configured twice")
        cy.rounds.append(rnd)
        df = read(p)
        lab = f"{key} {rnd}"
        ec = resolve_col(df, p["email_col"], lab)
        nc = resolve_col(df, p.get("name_col"), lab)
        rcs = [resolve_col(df, c, lab) for c in p["rank_cols"]]
        fcs = [resolve_col(df, c, lab) for c in p.get("freetext_cols") or []]
        # ignore_cols may name columns that have since been deleted from the file
        ign = {
            c
            for c in df.columns
            if canon_header(c) in {canon_header(x) for x in p.get("ignore_cols") or []}
        }
        used = {ec, nc, *rcs, *fcs} | ign
        for c in df.columns:
            if c not in used:
                vals = [v for v in df[c] if v]
                if vals:
                    cy.extra_columns.append((rnd, c, vals))

        rows, nulls = [], 0
        for i, r in df.iterrows():
            if _blank_row(r, df.columns):
                continue
            email = norm_email(r[ec])
            if not email:
                cy.warnings.append(
                    f"{lab}: row {i + 2} has no usable email address; skipped"
                )
                continue
            ranks = []
            for k, c in enumerate(rcs, 1):
                v = r[c]
                if is_null_pref(v):
                    nulls += bool(v)
                    continue
                ranks.append((k, v))
            ft = {c: r[c] for c in fcs if r[c]}
            rows.append(
                Response(rnd, ROUNDS[rnd], email, r[nc] if nc else "", ranks, ft, i + 2)
            )
        if nulls:
            cy.warnings.append(
                f"{lab}: {nulls} preference cells hold a placeholder "
                "such as N/A; treated as blank"
            )
        cy.responses.extend(_dedupe(rows, lab, policy, cy.warnings))

    # ---- repeat declarations
    rp = spec.get("repeaters")
    if rp:
        df = read(rp)
        lab = f"{key} repeaters"
        ec = resolve_col(df, rp["email_col"], lab)
        pc = resolve_col(df, rp.get("prior_course_col"), lab)
        rows = []
        for i, r in df.iterrows():
            if _blank_row(r, df.columns):
                continue
            e = norm_email(r[ec])
            if not e:
                cy.warnings.append(
                    f"{lab}: row {i + 2} has no usable email address; skipped"
                )
                continue
            prior = r[pc] if pc else ""
            if pc and is_null_pref(prior):
                cy.warnings.append(f"{lab}: row {i + 2} has no prior course")
                prior = ""
            rows.append(Repeat(e, prior, i + 2))
        cy.repeaters = _dedupe(rows, lab, policy, cy.warnings)

    # ---- final placements (one row per course; extra rows = extra sponsors)
    pl = spec["placements"]
    df = read(pl)
    lab = f"{key} placements"
    cc = resolve_col(df, pl["code_col"], lab)
    nc = resolve_col(df, pl["name_col"], lab)
    scs = [resolve_col(df, c, lab) for c in pl["sponsor_cols"]]
    next_slot: dict[str, int] = {}
    first_name: dict[str, str] = {}
    last_code = None
    for i, r in df.iterrows():
        code, cname = r[cc], r[nc]
        sponsors = [r[c] for c in scs]
        extra_row = False
        same_as_above = (
            last_code is not None
            and cname
            and norm_course(cname) == norm_course(first_name[last_code])
        )
        if not code and (not cname or same_as_above):
            if not any(sponsors):
                continue
            if last_code is None:
                cy.warnings.append(
                    f"{lab}: row {i + 2} has sponsors but no course above it; skipped"
                )
                continue
            code, extra_row = last_code, True  # merged Trip Code cell
            cy.n_continuation_rows += 1
        elif not code:
            # id from the name, not the row position, so re-sorting the sheet keeps it
            code = "NOCODE-" + hashlib.sha1(norm_course(cname).encode()).hexdigest()[:6]
            cy.warnings.append(
                f"{lab}: row {i + 2} has a course name but no trip code; "
                f"assigned {code}"
            )
        elif code in first_name:
            extra_row = True
            if cname and norm_course(cname) != norm_course(first_name[code]):
                cy.warnings.append(
                    f"{lab}: row {i + 2} reuses trip code {code} with a "
                    "different course name; treated as the same course"
                )
        first_name.setdefault(code, cname)
        last_code = code
        for s in sponsors:
            if extra_row and not s:
                continue  # padding on a continuation row, not a missing sponsor
            slot = next_slot.get(code, 0) + 1
            next_slot[code] = slot
            if not s:
                status = "blank_in_source"
            elif is_placeholder_sponsor(s):
                status = "placeholder_in_source"
            else:
                status = "named"
                if MULTI_NAME_RE.search(s):
                    cy.warnings.append(
                        f"{lab}: row {i + 2} ({code}) slot {slot} may hold "
                        "more than one person"
                    )
            cy.slots.append(
                Slot(
                    code,
                    first_name[code],
                    slot,
                    s if status == "named" else "",
                    status,
                    i + 2,
                )
            )
    if cy.n_continuation_rows:
        cy.warnings.append(
            f"{lab}: {cy.n_continuation_rows} rows had sponsors but no trip "
            "code; attached to the course above (merged cells?)"
        )
    return cy


def load_all(cfg: dict) -> list[Cycle]:
    return [load_cycle(cfg, k) for k in sorted(cfg["cycles"])]
