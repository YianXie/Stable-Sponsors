"""Stage 2 of 2: apply the accepted key and write the analysis dataset.

    python src/apply_pseudonymization.py --config config/pseudonymize.yaml

Reads key/identity.csv, key/course_alias.csv and key/course_catalogue.csv
(produced by build_crosswalk.py --accept) and refuses to write anything if a
single email, name or course string in the raw files is not covered by them.

Writes under private_root/derived/ (every table has a `cycle` column):
    teachers.csv      one row per teacher per cycle they appear in
    preferences.csv   teacher, round, rank, course
    placements.csv    course, sponsor slot, teacher, status
    courses.csv       course, type, in offerings, ran, sponsors assigned, country
    checks.csv        data-consistency findings; each is a question for the office
    manifest.json     code commit, input/key/output hashes, counts

Free text goes to private_root/freetext/<cycle>/ and never to derived/. The
coding sheet there is merged, not overwritten, so hand-coded columns survive a
rebuild. Empty string in a boolean column means "unknown" (for example
is_repeater in a cycle with no repeat file), never "no".
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import pandas as pd

from stable_sponsors.build_crosswalk import (
    ALIAS_DRAFT,
    ALIAS_FINAL,
    CAT_DRAFT,
    CAT_FINAL,
    ID_DRAFT,
    ID_FINAL,
    is_yes,
    node_key,
)
from stable_sponsors.idmap import (
    NONE_COURSE,
    REPO_ROOT,
    course_key,
    load_config,
    out_path,
    sha256_file,
    split_slot_tag,
)
from stable_sponsors.sources import load_all

CODE_COLUMNS = [
    "req_certification",
    "co_sponsor_request",
    "medical_or_access_constraint",
    "date_constraint",
    "other_code",
]


def _need(path, what):
    if not path.exists():
        raise SystemExit(
            f"{path} not found. Review the drafts and run "
            f"build_crosswalk.py --accept first ({what})."
        )
    df = pd.read_csv(path, dtype=str).fillna("")
    bad = df[~df["confirmed"].map(is_yes)]
    if len(bad):
        raise SystemExit(f"{path.name}: {len(bad)} rows are not confirmed")
    return df


def load_identity(cfg):
    df = _need(out_path(cfg, ID_FINAL), "identity key")
    ident = {}
    for r in df.itertuples():
        k = node_key(r.identifier)
        if k is None:
            raise SystemExit(
                f"identity.csv: empty identifier on CSV line {r.Index + 2}"
            )
        if k in ident and ident[k] != r.teacher_id:
            raise SystemExit(
                f"identity.csv: one identifier is assigned to two teacher_ids "
                f"(line {r.Index + 2})"
            )
        ident[k] = r.teacher_id
    if not df["teacher_id"].str.fullmatch(r"T\d{3}").all():
        raise SystemExit("identity.csv: every teacher_id must look like T123")
    return ident


def load_course_key(cfg):
    al = _need(out_path(cfg, ALIAS_FINAL), "course aliases")
    ca = _need(out_path(cfg, CAT_FINAL), "course catalogue")
    amap = {}
    for r in al.itertuples():
        cid = r.course_id.strip()
        if not cid:
            raise SystemExit(
                f"course_alias.csv: no course_id on CSV line {r.Index + 2}"
            )
        k = (str(r.cycle), r.source, course_key(r.raw_string))
        if k in amap and amap[k] != cid:
            raise SystemExit(
                f"course_alias.csv: line {r.Index + 2} maps a string already "
                "mapped to a different course"
            )
        amap[k] = cid
    cat = {}
    for r in ca.itertuples():
        if r.course_type not in ("intl", "sg"):
            raise SystemExit(
                f"course_catalogue.csv: line {r.Index + 2} course_type must be intl or sg"
            )
        cat[(str(r.cycle), r.course_id)] = dict(
            course_type=r.course_type,
            country=r.country,
            ran=getattr(r, "ran", ""),
            trip_code=getattr(r, "trip_code", ""),
        )
    return amap, cat


def unaccepted_edits(cfg):
    out = []
    for d, f in (
        (ID_DRAFT, ID_FINAL),
        (ALIAS_DRAFT, ALIAS_FINAL),
        (CAT_DRAFT, CAT_FINAL),
    ):
        pd_, pf = out_path(cfg, d), out_path(cfg, f)
        if pd_.exists() and pf.exists() and sha256_file(pd_) != sha256_file(pf):
            out.append(d)
    return out


def git_state():
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=REPO_ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
        return commit, dirty
    except Exception:
        return "unknown", True


def run(cfg, quiet=False):
    ident = load_identity(cfg)
    amap, cat = load_course_key(cfg)
    pending = unaccepted_edits(cfg)
    if pending and not quiet:
        print(
            f"  ! {', '.join(pending)} differ from the accepted key. Edits there are not used "
            "until you run build_crosswalk.py --accept."
        )
    cycles = load_all(cfg)

    missing = defaultdict(list)  # what -> row references (no personal data)
    teachers, prefs, places, courses, checks = [], [], [], [], []
    freetext = []  # (cycle, tid, round, column, text)
    placed_by_cycle = {}

    def check(cy, kind, tid="", cid="", detail=""):
        checks.append(
            dict(cycle=cy, check=kind, teacher_id=tid, course_id=cid, detail=detail)
        )

    for cy in cycles:
        k = cy.key

        def tid_email(email, where):
            t = ident.get(("E", email))
            if not t:
                missing["email not in identity key"].append(where)
            return t

        # ---- repeaters
        rep = {}
        for rp in cy.repeaters or []:
            t = tid_email(rp.email, f"{k} repeaters row {rp.row}")
            if not t:
                continue
            prior = ""
            if rp.prior_raw:
                prior = amap.get((k, "prior", course_key(rp.prior_raw)), "")
                if not prior:
                    missing["prior course not in alias file"].append(
                        f"{k} repeaters row {rp.row}"
                    )
            if t in rep:
                check(k, "repeater_listed_twice", t)
            rep[t] = prior

        # ---- preference forms (one response per teacher per round, after identity mapping)
        submitted = defaultdict(set)
        ranked = defaultdict(set)
        slot_genders = defaultdict(set)
        chosen = {}
        for r in cy.responses:
            t = tid_email(r.email, f"{k} {r.round} row {r.row}")
            if not t:
                continue
            key = (r.round, t)
            if key in chosen:
                prev = chosen[key][1]
                policy = cfg["duplicate_submissions"]
                if policy == "error":
                    missing["same teacher submitted twice under two addresses"].append(
                        f"{k} {r.round} rows {prev.row} and {r.row}"
                    )
                    continue
                # same form file, so a higher spreadsheet row is a later submission
                later, earlier = (r, prev) if r.row > prev.row else (prev, r)
                keep = later if policy == "last" else earlier
                check(
                    k,
                    "two_addresses_same_teacher_same_form",
                    t,
                    "",
                    f"{r.round} rows {earlier.row} and {later.row}; kept row {keep.row} "
                    f"({policy}); the other row's free text is not used",
                )
                chosen[key] = (t, keep)
                continue
            chosen[key] = (t, r)
        for t, r in chosen.values():
            submitted[r.round].add(t)
            if r.name:
                nk = node_key(r.name)
                tn = ident.get(nk) if nk else None
                if tn and tn != t:
                    check(
                        k,
                        "form_name_belongs_to_other_teacher",
                        t,
                        "",
                        f"{r.round} row {r.row}",
                    )
            positions = [rank for rank, _ in r.ranks]
            if positions and max(positions) != len(positions):
                check(
                    k, "gap_in_ranking", t, "", f"{r.round}: filled ranks {positions}"
                )
            seen = set()
            for rank, raw in r.ranks:
                cid = amap.get((k, r.channel, course_key(raw)))
                if not cid:
                    missing["preference string not in alias file"].append(
                        f"{k} {r.round} row {r.row} rank {rank}"
                    )
                    continue
                if cid == NONE_COURSE:
                    check(
                        k, "preference_mapped_to_none", t, "", f"{r.round} rank {rank}"
                    )
                    continue
                ranked[t].add(cid)
                if cid in seen:
                    check(
                        k, "same_course_ranked_twice", t, cid, f"{r.round} rank {rank}"
                    )
                    continue
                seen.add(cid)
                ctype = cat.get((k, cid), {}).get("course_type")
                if ctype and ctype != r.channel:
                    check(
                        k,
                        "course_type_differs_from_form",
                        t,
                        cid,
                        f"{r.round} rank {rank}",
                    )
                slot = split_slot_tag(raw)[1]
                if slot:
                    slot_genders[t].add(slot)
                prefs.append(
                    dict(
                        cycle=k,
                        teacher_id=t,
                        round=r.round,
                        rank=rank,
                        course_id=cid,
                        slot_gender=slot,
                    )
                )
            for col, txt in r.freetext.items():
                freetext.append((k, t, r.round, col, txt))

        # ---- placements
        placed = defaultdict(list)
        for s in cy.slots:
            if s.status != "named":
                places.append(
                    dict(
                        cycle=k,
                        course_id=s.code,
                        sponsor_slot=s.slot,
                        teacher_id="",
                        status=s.status,
                    )
                )
                continue
            nk = node_key(s.sponsor)
            t = ident.get(nk) if nk else None
            if not t:
                missing["sponsor not in identity key"].append(
                    f"{k} placements row {s.row} ({s.code} slot {s.slot})"
                )
                continue
            placed[t].append(s.code)
            places.append(
                dict(
                    cycle=k,
                    course_id=s.code,
                    sponsor_slot=s.slot,
                    teacher_id=t,
                    status="assigned",
                )
            )
        placed = dict(placed)  # plain dict: lookups below must not insert
        placed_by_cycle[k] = placed

        # ---- teachers in this cycle
        present = set(rep) | set(placed)
        for ts in submitted.values():
            present |= ts
        for t in sorted(present):
            any_form = any(t in submitted[rd] for rd in cy.rounds)
            mine = placed.get(t, [])
            teachers.append(
                dict(
                    cycle=k,
                    teacher_id=t,
                    is_repeater=(t in rep) if cy.repeaters is not None else "",
                    prior_course_id=rep.get(t, ""),
                    submitted_intl_r1=(t in submitted["intl_r1"])
                    if "intl_r1" in cy.rounds
                    else "",
                    submitted_intl_r2=(t in submitted["intl_r2"])
                    if "intl_r2" in cy.rounds
                    else "",
                    submitted_sg=(t in submitted["sg"]) if "sg" in cy.rounds else "",
                    is_placed=bool(mine),
                    # unknown for a cycle without a repeat file: they may be repeaters
                    slot_genders_ranked="|".join(sorted(slot_genders.get(t, ()))),
                    placed_without_submission=(
                        ""
                        if (cy.repeaters is None and mine and not any_form)
                        else bool(mine) and not any_form and t not in rep
                    ),
                )
            )
            if len(mine) > 1:
                check(k, "placed_on_more_than_one_course", t, "|".join(mine))
            if len(slot_genders.get(t, ())) > 1:
                check(
                    k,
                    "ranked_both_male_and_female_slots",
                    t,
                    "",
                    "picked slots tagged for both genders; check the form data",
                )
            if t in rep:
                if t in submitted["intl_r1"]:
                    check(k, "repeater_also_submitted_round1", t)
                if not mine:
                    check(k, "repeater_not_placed", t, rep[t])
                elif rep[t] and rep[t] not in mine:
                    check(
                        k,
                        "repeater_placed_on_other_course",
                        t,
                        rep[t],
                        f"placed on {'|'.join(mine)}",
                    )
            if t in submitted["intl_r2"] and t not in submitted["intl_r1"]:
                check(k, "round2_without_round1", t)
            if any_form and not mine:
                check(k, "submitted_but_not_placed", t)
            if cy.repeaters is not None and mine and not any_form and t not in rep:
                check(k, "placed_without_any_response", t, "|".join(mine))
            if mine and ranked.get(t) and not (set(mine) & ranked[t]):
                check(
                    k,
                    "placed_on_course_not_in_any_list",
                    t,
                    "|".join(mine),
                    "verify the identity link first; if it is right, this is a residual case",
                )

        # ---- courses in this cycle
        offered = {
            cid for (c, src, _), cid in amap.items() if c == k and src == "offerings"
        }
        cids = {s.code for s in cy.slots} | {
            cid for (c, _, _), cid in amap.items() if c == k
        }
        # every real course (it has a trip code) is kept even if nobody ranked it, e.g. a
        # listed Singapore course missing from the sheet; only unused NR- ids are dropped
        cids |= {cid for (c, cid), m in cat.items() if c == k and m["trip_code"]}
        cids.discard(NONE_COURSE)
        assigned = Counter(
            p["course_id"]
            for p in places
            if p["cycle"] == k and p["status"] == "assigned"
        )
        for cid in sorted(cids):
            meta = cat.get((k, cid))
            if not meta:
                missing["course not in catalogue"].append(f"{k} {cid}")
                continue
            unknown = assigned[cid] == 0 and meta["ran"] == "unknown"
            if unknown:
                check(
                    k,
                    "course_missing_from_placements",
                    "",
                    cid,
                    "has a trip code but no placement row; ask the office whether it ran",
                )
            courses.append(
                dict(
                    cycle=k,
                    course_id=cid,
                    course_type=meta["course_type"],
                    in_offerings=cid in offered,
                    ran="" if unknown else assigned[cid] > 0,
                    n_sponsors_assigned=assigned[cid],
                    country=meta["country"],
                )
            )
        orphans = {cid for (c, cid) in cat if c == k} - cids
        for cid in sorted(orphans):
            check(
                k,
                "catalogue_course_not_referenced",
                "",
                cid,
                "listed in course_catalogue.csv but no alias or placement points to it; ignored",
            )

    # ---- cross-cycle: a repeater's prior course should be last cycle's placement
    keys = [cy.key for cy in cycles]
    for prev, cur in zip(keys, keys[1:]):
        cur_rep = {
            t["teacher_id"]: t["prior_course_id"]
            for t in teachers
            if t["cycle"] == cur and t["is_repeater"] is True
        }
        for t, prior in sorted(cur_rep.items()):
            last = placed_by_cycle[prev].get(t, [])
            if not last:
                check(
                    cur,
                    "repeater_not_placed_previous_cycle",
                    t,
                    prior,
                    f"no {prev} placement",
                )
            elif prior and prior not in last:
                check(
                    cur,
                    "prior_course_differs_from_previous_placement",
                    t,
                    prior,
                    f"{prev} placement {'|'.join(last)}",
                )

    if missing:
        print("NOTHING WRITTEN. The key does not cover these raw values:")
        for what, refs in missing.items():
            print(f"  {what}: {len(refs)}")
            for ref in refs[:10]:
                print(f"      {ref}")
            if len(refs) > 10:
                print(f"      ... {len(refs) - 10} more")
        print("Rerun build_crosswalk.py, review the new rows, and --accept again.")
        sys.exit(1)

    # ---- write
    derived = out_path(cfg, "derived")
    derived.mkdir(parents=True, exist_ok=True)
    tables = {
        "teachers": pd.DataFrame(
            teachers,
            columns=[
                "cycle",
                "teacher_id",
                "is_repeater",
                "prior_course_id",
                "submitted_intl_r1",
                "submitted_intl_r2",
                "submitted_sg",
                "is_placed",
                "slot_genders_ranked",
                "placed_without_submission",
            ],
        ),
        "preferences": pd.DataFrame(
            prefs,
            columns=[
                "cycle",
                "teacher_id",
                "round",
                "rank",
                "course_id",
                "slot_gender",
            ],
        ),
        "placements": pd.DataFrame(
            places,
            columns=["cycle", "course_id", "sponsor_slot", "teacher_id", "status"],
        ),
        "courses": pd.DataFrame(
            courses,
            columns=[
                "cycle",
                "course_id",
                "course_type",
                "in_offerings",
                "ran",
                "n_sponsors_assigned",
                "country",
            ],
        ),
        "checks": pd.DataFrame(
            checks, columns=["cycle", "check", "teacher_id", "course_id", "detail"]
        ),
    }
    for name, df in tables.items():
        df.to_csv(derived / f"{name}.csv", index=False)

    n_ft = write_freetext(cfg, freetext)

    commit, dirty = git_state()
    counts = {}
    for cy in cycles:
        t = tables["teachers"][tables["teachers"]["cycle"] == cy.key]
        c = tables["courses"][tables["courses"]["cycle"] == cy.key]
        counts[cy.key] = dict(
            teachers=len(t),
            placed=int(t["is_placed"].sum()),
            repeaters=int((t["is_repeater"] == True).sum())
            if cy.repeaters is not None
            else None,  # noqa: E712
            courses=len(c),
            courses_ran=int((c["ran"] == True).sum()),  # noqa: E712
            courses_ran_unknown=int((c["ran"] == "").sum()),
            intl_offered=int(((c["course_type"] == "intl") & c["in_offerings"]).sum()),
            sg=int((c["course_type"] == "sg").sum()),
            preference_rows=int((tables["preferences"]["cycle"] == cy.key).sum()),
            rounds=cy.rounds,
        )
    manifest = {
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": commit,
        "working_tree_dirty": dirty,
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "config_sha256": cfg["_config_sha256"],
        "inputs_sha256": {cy.key: cy.inputs for cy in cycles},
        "key_sha256": {
            rel: sha256_file(out_path(cfg, rel))
            for rel in (ID_FINAL, ALIAS_FINAL, CAT_FINAL)
        },
        "outputs_sha256": {
            f"{n}.csv": sha256_file(derived / f"{n}.csv") for n in tables
        },
        "counts": counts,
        "checks": dict(Counter(c["check"] for c in checks)),
        "freetext_fields": n_ft,
    }
    (derived / "manifest.json").write_text(json.dumps(manifest, indent=2))

    if not quiet:
        print("=" * 70)
        for key, c in counts.items():
            rep = "unknown" if c["repeaters"] is None else c["repeaters"]
            print(
                f"{key}: teachers {c['teachers']}  placed {c['placed']}  repeaters {rep}  "
                f"courses {c['courses']} (ran {c['courses_ran']}"
                + (
                    f", unknown {c['courses_ran_unknown']}"
                    if c["courses_ran_unknown"]
                    else ""
                )
                + f", Singapore {c['sg']})  "
                f"preference rows {c['preference_rows']}"
            )
        if checks:
            print(
                "\nchecks (details in derived/checks.csv; each is a question, not a bug):"
            )
            for kind, n in Counter(
                (c["cycle"], c["check"]) for c in checks
            ).most_common():
                print(f"  {kind[0]}  {kind[1]:46s} {n:4d}")
        print(f"\nfree-text fields routed to freetext/: {n_ft}")
        print(f"wrote {derived}  (commit {commit[:8]}, dirty={dirty})")
    return manifest


def write_freetext(cfg, items):
    base = out_path(cfg, "freetext")
    base.mkdir(parents=True, exist_ok=True)
    rows = []
    for cyc, t, rnd, col, txt in items:
        d = base / cyc
        d.mkdir(parents=True, exist_ok=True)
        slug = (
            "".join(ch if ch.isalnum() else "_" for ch in col).lower().strip("_")[:40]
        )
        (d / f"{t}__{rnd}__{slug}.txt").write_text(txt)
        rows.append(dict(cycle=cyc, teacher_id=t, round=rnd, field=col, chars=len(txt)))
    new = pd.DataFrame(rows, columns=["cycle", "teacher_id", "round", "field", "chars"])
    sheet = base / "coding_sheet.csv"
    keys = ["cycle", "teacher_id", "round", "field"]
    if sheet.exists():
        old = pd.read_csv(sheet, dtype=str).fillna("")
        code_cols = [c for c in old.columns if c not in keys + ["chars"]]
        new = new.astype({"cycle": str}).merge(
            old[keys + code_cols], on=keys, how="left"
        )
        dropped = len(
            old.merge(new[keys], on=keys, how="left", indicator=True).query(
                "_merge == 'left_only'"
            )
        )
        if dropped:
            print(
                f"  ! coding sheet: {dropped} previously coded rows no longer have free text "
                "(kept in freetext/coding_sheet.previous.csv)"
            )
            old.to_csv(base / "coding_sheet.previous.csv", index=False)
    for c in CODE_COLUMNS:
        if c not in new.columns:
            new[c] = ""
    new.fillna("").to_csv(sheet, index=False)
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default="config/pseudonymize.yaml")
    args = ap.parse_args()
    run(load_config(args.config))


if __name__ == "__main__":
    main()
