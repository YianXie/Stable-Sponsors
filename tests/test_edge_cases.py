"""Targeted regressions, one per defect found in review. Tiny hand-built datasets."""

import sys
from pathlib import Path

import openpyxl
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import apply_pseudonymization as s2  # noqa: E402
import build_crosswalk as s1  # noqa: E402
from idmap import CourseIndex, load_config  # noqa: E402
from sources import load_cycle  # noqa: E402

D = "sas.edu.sg"


def xlsx(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(path)


def mini(tmp, placements=None, r1=None, offerings=None, repeaters=True, r1_names=False,
         coded_offerings=None, sg=None, extra=None, r1_extra_col=False):
    """One cycle 'C'. Default: two teachers, two courses, both placed from their lists."""
    raw = tmp / "raw" / "C"
    offerings = offerings or [["Bali Service", "Denpasar", "Indonesia"],
                              ["Nepal Trek", "Kathmandu", "Nepal"],
                              ["Fiji Reef", "Nadi", "Fiji"]]
    r1 = r1 if r1 is not None else [[f"aabbott@{D}", "Bali Service", "Nepal Trek"],
                                    [f"bbaker@{D}", "Nepal Trek", "Bali Service"]]
    placements = placements or [["IDN-SVC", "Bali Service", "Alan Abbott", "Carla Cruz"],
                                ["NPL-TRK", "Nepal Trek", "Brian Baker", ""]]
    if coded_offerings is not None:          # [code, name, city, country]; code blank = did not run
        xlsx(raw / "off.xlsx", ["Trip Code", "Course Name", "Arrival City", "Country"],
             coded_offerings)
    else:
        xlsx(raw / "off.xlsx", ["Course Name", "Arrival City", "Country"], offerings)
    hdr = ["Email Address"] + (["Name (First & Last)"] if r1_names else []) + \
        ["First Preference", "Second Preference"] + (["Stray"] if r1_extra_col else [])
    xlsx(raw / "r1.xlsx", hdr, [row + (["x"] if r1_extra_col else []) for row in r1])
    xlsx(raw / "pl.xlsx", ["Trip Code", "Courses Name", "Sponsor 1", "Sponsor 2"], placements)
    spec = {
        "offerings": {"path": "C/off.xlsx", "name_col": "Course Name",
                      "city_col": "Arrival City", "country_col": "Country"},
        "preferences": [{"round": "intl_r1", "path": "C/r1.xlsx", "email_col": "Email Address",
                         "name_col": "Name (First & Last)" if r1_names else None,
                         "rank_cols": ["First Preference", "Second Preference"]}],
        "placements": {"path": "C/pl.xlsx", "code_col": "Trip Code", "name_col": "Courses Name",
                       "sponsor_cols": ["Sponsor 1", "Sponsor 2"]},
    }
    if coded_offerings is not None:
        spec["offerings"]["code_col"] = "Trip Code"
    if sg is not None:
        xlsx(raw / "sg.xlsx", ["Email Address", "First Preference", "Second Preference"], sg)
        spec["preferences"].append({"round": "sg", "path": "C/sg.xlsx",
                                    "email_col": "Email Address",
                                    "rank_cols": ["First Preference", "Second Preference"]})
    spec.update(extra or {})
    if repeaters:
        xlsx(raw / "rep.xlsx", ["Email", "Prior Course"], [])
        spec["repeaters"] = {"path": "C/rep.xlsx", "email_col": "Email",
                             "prior_course_col": "Prior Course"}
    cp = tmp / "cfg.yaml"
    cp.write_text(yaml.safe_dump({"private_root": str(tmp), "raw_dir": "raw",
                                  "cycles": {"C": spec}}))
    return load_config(cp)


def confirm_all(cfg):
    for rel in (s1.ID_DRAFT, s1.ALIAS_DRAFT, s1.CAT_DRAFT):
        p = s1.out_path(cfg, rel)
        df = pd.read_csv(p, dtype=str).fillna("")
        df["confirmed"] = "y"
        df.to_csv(p, index=False)


def ids(cfg, rel=s1.ID_DRAFT):
    df = pd.read_csv(s1.out_path(cfg, rel), dtype=str).fillna("")
    return df, dict(zip(df["identifier"], df["teacher_id"]))


# ---------------------------------------------------------------- loader

def test_placeholders_and_null_preferences(tmp_path):
    cfg = mini(tmp_path,
               placements=[["IDN-SVC", "Bali Service", "Alan Abbott", "TBD."],
                           ["NPL-TRK", "Nepal Trek", "(new hire)", "—"],
                           ["FJI-REF", "Fiji Reef", "(parent volunteer)", ""]],
               r1=[[f"aabbott@{D}", "Bali Service", "N/A."], [f"bbaker@{D}", "?", "Nepal Trek"]])
    cy = load_cycle(cfg, "C")
    assert [s.status for s in cy.slots] == ["named", "placeholder_in_source",
                                             "placeholder_in_source", "placeholder_in_source",
                                             "placeholder_in_source", "blank_in_source"]
    assert [r.ranks for r in cy.responses] == [[(1, "Bali Service")], [(2, "Nepal Trek")]]


def test_merged_code_with_repeated_name_is_a_continuation(tmp_path):
    cfg = mini(tmp_path, placements=[["IDN-SVC", "Bali Service", "Alan Abbott", "Brian Baker"],
                                     ["", "Bali Service", "Carla Cruz", ""]])
    cy = load_cycle(cfg, "C")
    assert {s.code for s in cy.slots} == {"IDN-SVC"}
    assert [s.slot for s in cy.slots] == [1, 2, 3]


def test_codeless_course_ids_do_not_depend_on_row_order(tmp_path):
    rows = [["", "Singapore Hawker", "Alan Abbott", ""], ["", "Singapore Mangroves", "Brian Baker", ""]]
    a = {s.course_name: s.code for s in load_cycle(mini(tmp_path / "a", placements=rows), "C").slots}
    b = {s.course_name: s.code for s in load_cycle(mini(tmp_path / "b", placements=rows[::-1]), "C").slots}
    assert a == b and len(set(a.values())) == 2


def test_missing_header_row_does_not_print_personal_data(tmp_path, capsys):
    cfg = mini(tmp_path)
    xlsx(tmp_path / "raw" / "C" / "r1.xlsx", [f"aabbott@{D}", "Alan Abbott", "Bali Service"], [])
    with pytest.raises(SystemExit) as e:
        load_cycle(cfg, "C")
    msg = str(e.value)
    assert "aabbott" not in msg and "Alan Abbott" not in msg and "header row missing" in msg


# ---------------------------------------------------------------- stage 2 semantics

def test_unknown_repeat_status_stays_unknown(tmp_path):
    cfg = mini(tmp_path, repeaters=False)      # Carla Cruz is placed with no form
    s1.run(cfg, quiet=True)
    confirm_all(cfg)
    s1.accept(cfg)
    s2.run(cfg, quiet=True)
    t = pd.read_csv(tmp_path / "derived/teachers.csv", dtype=str).fillna("")
    _, m = ids(cfg, s1.ID_FINAL)
    carla = t[t.teacher_id == m["Carla Cruz"]].iloc[0]
    assert carla["placed_without_submission"] == "" and carla["is_repeater"] == ""


def test_two_addresses_for_one_teacher_give_one_list(tmp_path):
    cfg = mini(tmp_path, r1=[[f"aabbott@{D}", "Bali Service", "Nepal Trek"],
                             [f"alan.abbott@{D}", "Nepal Trek", "Bali Service"],
                             [f"bbaker@{D}", "Nepal Trek", "Bali Service"]])
    s1.run(cfg, quiet=True)
    df, m = ids(cfg)
    main = m[f"aabbott@{D}"]
    row = df["identifier"] == f"alan.abbott@{D}"
    df.loc[row & (df["teacher_id"] != main), "notes"] = "second address of the same person"
    df.loc[row, "teacher_id"] = main
    df.to_csv(s1.out_path(cfg, s1.ID_DRAFT), index=False)
    confirm_all(cfg)
    s1.accept(cfg)
    s2.run(cfg, quiet=True)
    p = pd.read_csv(tmp_path / "derived/preferences.csv", dtype=str)
    assert len(p[p.teacher_id == main]) == 2
    c = pd.read_csv(tmp_path / "derived/checks.csv", dtype=str)
    assert (c["check"] == "two_addresses_same_teacher_same_form").sum() == 1


# ---------------------------------------------------------------- review workflow

def test_moving_a_row_without_a_note_is_refused(tmp_path):
    cfg = mini(tmp_path)
    s1.run(cfg, quiet=True)
    df, m = ids(cfg)
    df.loc[df["identifier"] == "Carla Cruz", "teacher_id"] = m["Alan Abbott"]
    df.to_csv(s1.out_path(cfg, s1.ID_DRAFT), index=False)
    confirm_all(cfg)
    with pytest.raises(SystemExit):
        s1.accept(cfg)


def test_new_id_token_and_draft_edits_survive_rerun_after_accept(tmp_path):
    cfg = mini(tmp_path)
    s1.run(cfg, quiet=True)
    confirm_all(cfg)
    s1.accept(cfg)
    s1.run(cfg, quiet=True)                        # e.g. told to rerun by stage 2
    df, m = ids(cfg)
    before = m[f"aabbott@{D}"]
    df.loc[df["identifier"] == "Alan Abbott", ["teacher_id", "notes"]] = ["NEW", "office: not the same"]
    df.to_csv(s1.out_path(cfg, s1.ID_DRAFT), index=False)
    s1.run(cfg, quiet=True)
    df2, m2 = ids(cfg)
    assert m2["Alan Abbott"] != before and m2[f"aabbott@{D}"] == before
    assert df2.loc[df2["identifier"] == "Alan Abbott", "notes"].iloc[0] == "office: not the same"
    assert df2["teacher_id"].str.fullmatch(r"T\d{3}").all()


def test_split_with_only_one_side_confirmed_survives_rerun(tmp_path):
    cfg = mini(tmp_path)
    s1.run(cfg, quiet=True)
    df, m = ids(cfg)
    row = df["identifier"] == "Alan Abbott"
    df.loc[row, ["teacher_id", "notes", "confirmed"]] = ["NEW", "split on purpose", "y"]
    df.to_csv(s1.out_path(cfg, s1.ID_DRAFT), index=False)
    s1.run(cfg, quiet=True)
    _, m2 = ids(cfg)
    assert m2["Alan Abbott"] != m2[f"aabbott@{D}"]


def test_confirmed_did_not_run_lock_is_challenged_when_course_appears(tmp_path):
    cfg = mini(tmp_path)
    s1.run(cfg, quiet=True)
    confirm_all(cfg)
    s1.accept(cfg)
    mini(tmp_path, placements=[["IDN-SVC", "Bali Service", "Alan Abbott", "Carla Cruz"],
                               ["NPL-TRK", "Nepal Trek", "Brian Baker", ""],
                               ["FJI-REF", "Fiji Reef", "Dana Diaz", ""]])
    s1.run(cfg, quiet=True)
    al = pd.read_csv(s1.out_path(cfg, s1.ALIAS_DRAFT), dtype=str).fillna("")
    fiji = al[(al.source == "offerings") & (al.raw_string == "Fiji Reef")].iloc[0]
    assert fiji["method"] == "LOCK_CONFLICT" and fiji["confirmed"] == ""


def test_off_list_placement_is_flagged(tmp_path):
    # qzhou@ submitted but was not placed; a different Q. Zhou was placed without a form
    cfg = mini(tmp_path, r1=[[f"aabbott@{D}", "Bali Service", "Nepal Trek"],
                             [f"qzhou@{D}", "Bali Service", "Fiji Reef"]],
               placements=[["IDN-SVC", "Bali Service", "Alan Abbott", ""],
                           ["NPL-TRK", "Nepal Trek", "Quinn Zhou", ""]])
    s1.run(cfg, quiet=True)
    df, _ = ids(cfg)
    assert "PLACED_OFF_LIST" in df.loc[df["identifier"] == "Quinn Zhou", "cluster_flags"].iloc[0]


def test_numeric_codes_are_not_matched_inside_names():
    ix = CourseIndex()
    ix.add("101", ["Bali Surf"], ["101"])
    ix.add("134", ["Bali Photography 101"], ["134"])
    assert ix.match("Bali Photography 101 (Ubud)")[0] == "134"


# ---------------------------------------------------------------- second review round

def _set(cfg, ident, **cols):
    df = pd.read_csv(s1.out_path(cfg, s1.ID_DRAFT), dtype=str).fillna("")
    for c, v in cols.items():
        df.loc[df["identifier"] == ident, c] = v
    df.to_csv(s1.out_path(cfg, s1.ID_DRAFT), index=False)


def test_plain_new_on_two_people_gives_two_ids_and_labels_group(tmp_path):
    cfg = mini(tmp_path)
    s1.run(cfg, quiet=True)
    _set(cfg, "Alan Abbott", teacher_id="NEW", notes="x")
    _set(cfg, "Brian Baker", teacher_id="NEW", notes="x")
    _set(cfg, f"aabbott@{D}", teacher_id="new-a", notes="x")
    _set(cfg, f"bbaker@{D}", teacher_id="NEW-A", notes="x")
    s1.run(cfg, quiet=True)
    _, m = ids(cfg)
    assert m["Alan Abbott"] != m["Brian Baker"]                    # plain NEW: two people
    assert m[f"aabbott@{D}"] == m[f"bbaker@{D}"]                   # same label: one person
    assert len({m["Alan Abbott"], m["Brian Baker"], m[f"aabbott@{D}"]}) == 3


def test_rows_missing_for_one_run_keep_their_accepted_ids(tmp_path):
    cfg = mini(tmp_path)
    s1.run(cfg, quiet=True)
    confirm_all(cfg)
    s1.accept(cfg)
    _, before = ids(cfg, s1.ID_FINAL)
    mini(tmp_path, r1=[[f"aabbott@{D}", "Bali Service", "Nepal Trek"]],        # Brian vanishes
         placements=[["IDN-SVC", "Bali Service", "Alan Abbott", "Carla Cruz"]])
    s1.run(cfg, quiet=True)
    df, mid = ids(cfg)
    gone = df[df["identifier"] == "Brian Baker"].iloc[0]
    assert gone["cluster_flags"] == "NOT_IN_DATA" and gone["confirmed"] == "y"
    assert mid["Brian Baker"] == before["Brian Baker"]
    mini(tmp_path, r1=[[f"aabbott@{D}", "Bali Service", "Nepal Trek"],       # new person arrives
                       [f"ddiaz@{D}", "Nepal Trek", "Bali Service"]],
         placements=[["IDN-SVC", "Bali Service", "Alan Abbott", "Carla Cruz"],
                     ["NPL-TRK", "Nepal Trek", "Dana Diaz", ""]])
    s1.run(cfg, quiet=True)
    mini(tmp_path)                                                              # Brian is back
    s1.run(cfg, quiet=True)
    df2, after = ids(cfg)
    for who in ("Alan Abbott", "Brian Baker", "Carla Cruz", f"bbaker@{D}"):
        assert after[who] == before[who]
    assert (df2.set_index("identifier").loc[list(before), "confirmed"] == "y").all()
    assert after["Dana Diaz"] not in set(before.values())                     # never reused


def test_offering_conflict_reaches_form_strings_and_accept_blocks_orphans(tmp_path):
    r1 = [[f"aabbott@{D}", "Bali Service", "Fiji Reef"], [f"bbaker@{D}", "Nepal Trek", "Fiji Reef"]]
    cfg = mini(tmp_path, r1=r1)
    s1.run(cfg, quiet=True)
    confirm_all(cfg)
    s1.accept(cfg)
    mini(tmp_path, r1=r1, placements=[["IDN-SVC", "Bali Service", "Alan Abbott", "Carla Cruz"],
                                      ["NPL-TRK", "Nepal Trek", "Brian Baker", ""],
                                      ["FJI-REF", "Fiji Reef", "Dana Diaz", ""]])
    s1.run(cfg, quiet=True)
    al = pd.read_csv(s1.out_path(cfg, s1.ALIAS_DRAFT), dtype=str).fillna("")
    fiji = al[al.raw_string == "Fiji Reef"]
    assert set(fiji["method"]) == {"LOCK_CONFLICT"} and set(fiji["confirmed"]) == {""}
    assert set(fiji["conflict_with"]) == {"FJI-REF"}
    # fix only the offering row, confirm everything else as-is: accept must refuse
    al.loc[(al.raw_string == "Fiji Reef") & (al.source == "offerings"), "course_id"] = "FJI-REF"
    al["confirmed"] = "y"
    al.to_csv(s1.out_path(cfg, s1.ALIAS_DRAFT), index=False)
    for rel in (s1.ID_DRAFT, s1.CAT_DRAFT):
        d = pd.read_csv(s1.out_path(cfg, rel), dtype=str).fillna("")
        d["confirmed"] = "y"
        d.to_csv(s1.out_path(cfg, rel), index=False)
    with pytest.raises(SystemExit):
        s1.accept(cfg)


def test_confirmed_override_of_a_conflict_sticks(tmp_path):
    cfg = mini(tmp_path)
    s1.run(cfg, quiet=True)
    confirm_all(cfg)
    s1.accept(cfg)
    mini(tmp_path, placements=[["IDN-SVC", "Bali Service", "Alan Abbott", "Carla Cruz"],
                               ["NPL-TRK", "Nepal Trek", "Brian Baker", ""],
                               ["FJI-REF", "Fiji Reef", "Dana Diaz", ""]])
    s1.run(cfg, quiet=True)
    p = s1.out_path(cfg, s1.ALIAS_DRAFT)
    al = pd.read_csv(p, dtype=str).fillna("")
    row = al.raw_string == "Fiji Reef"
    al.loc[row, ["confirmed", "notes"]] = ["y", "office: different trip, keep NR"]
    al.to_csv(p, index=False)
    s1.run(cfg, quiet=True)
    s1.run(cfg, quiet=True)
    al = pd.read_csv(p, dtype=str).fillna("")
    r = al[al.raw_string == "Fiji Reef"].iloc[0]
    assert r["confirmed"] == "y" and r["method"] == "override_confirmed"


def test_unconfirmed_wrong_link_is_corrected_by_new_evidence(tmp_path):
    pl = [["IDN-SVC", "Bali Service", "Dana Kim", ""], ["NPL-TRK", "Nepal Trek", "Daniel Kim", ""]]
    cfg = mini(tmp_path, r1=[[f"dkim@{D}", "Nepal Trek", "Bali Service"]], placements=pl)
    s1.run(cfg, quiet=True)
    _, m = ids(cfg)
    assert m[f"dkim@{D}"] == m["Dana Kim"]            # the tie went the wrong way
    mini(tmp_path, r1=[[f"dkim@{D}", "Daniel Kim", "Nepal Trek", "Bali Service"]],
         placements=pl, r1_names=True)
    cfg = load_config(tmp_path / "cfg.yaml")
    s1.run(cfg, quiet=True)
    df, m = ids(cfg)
    assert m[f"dkim@{D}"] == m["Daniel Kim"] != m["Dana Kim"]
    flags = df.loc[df["identifier"] == "Daniel Kim", "cluster_flags"].iloc[0]
    assert "PRIOR_ID_CONFLICT" in flags


def test_latest_submission_wins_across_two_addresses(tmp_path):
    cfg = mini(tmp_path, r1=[[f"aabbott@{D}", "Bali Service", "Nepal Trek"],     # row 2
                             [f"alan.abbott@{D}", "Fiji Reef", "Bali Service"],  # row 3
                             [f"aabbott@{D}", "Nepal Trek", "Fiji Reef"],        # row 4: latest
                             [f"bbaker@{D}", "Nepal Trek", "Bali Service"]])
    s1.run(cfg, quiet=True)
    _, m = ids(cfg)
    _set(cfg, f"alan.abbott@{D}", teacher_id=m[f"aabbott@{D}"], notes="same person")
    confirm_all(cfg)
    s1.accept(cfg)
    s2.run(cfg, quiet=True)
    pr = pd.read_csv(tmp_path / "derived/preferences.csv", dtype=str)
    got = pr[pr.teacher_id == m[f"aabbott@{D}"]].sort_values("rank")["course_id"].tolist()
    assert got == ["NPL-TRK", s1.nr_id("Fiji Reef")]


def test_header_masking_and_non_latin_names():
    from idmap import is_placeholder_sponsor, norm_name, safe_headers
    shown = safe_headers(["Email Address", "Courses Name", "free text 1", "David Kim",
                          "Courtney Freeman", "Emily Firstbrook"])
    assert shown[:3] == ["Email Address", "Courses Name", "free text 1"]
    assert all(s.startswith("<") for s in shown[3:])
    assert not is_placeholder_sponsor("王伟") and norm_name("王伟") == "王伟"


def test_ids_are_never_reissued_even_after_the_key_is_rebuilt(tmp_path):
    cfg = mini(tmp_path)
    s1.out_path(cfg, "key").mkdir(parents=True, exist_ok=True)
    s1.record_issued(cfg, [f"T{i:03d}" for i in range(1, 991)])     # only T991-T999 free
    s1.run(cfg, quiet=True)
    _, first = ids(cfg)
    assert all(t >= "T991" for t in first.values())
    for rel in (s1.ID_DRAFT, s1.ID_FINAL):
        s1.out_path(cfg, rel).unlink(missing_ok=True)
    s1.run(cfg, quiet=True)
    _, second = ids(cfg)
    assert not set(first.values()) & set(second.values())
    assert all(t >= "T991" for t in second.values())


# ---------------------------------------------------------------- offerings with trip codes, SING-9

CODED = [["IDN-SVC", "Bali Service", "Denpasar", "Indonesia"],
         ["NPL-TRK", "Nepal Trek", "Kathmandu", "Nepal"],
         ["", "Fiji Reef", "Nadi", "Fiji"]]


def _drafts(cfg):
    al = pd.read_csv(s1.out_path(cfg, s1.ALIAS_DRAFT), dtype=str).fillna("")
    cat = pd.read_csv(s1.out_path(cfg, s1.CAT_DRAFT), dtype=str).fillna("")
    return al, cat.set_index("course_id")


def test_coded_offerings_join_by_code_and_blank_code_means_did_not_run(tmp_path):
    cfg = mini(tmp_path, coded_offerings=CODED + [["", "Nepal Trek Advanced", "Pokhara", "Nepal"]],
               placements=[["IDN-SVC", "Bali Service Week", "Alan Abbott", ""],
                           ["NPL-TRK", "Nepal Trek", "Brian Baker", ""]])
    s1.run(cfg, quiet=True)
    al, cat = _drafts(cfg)
    off = al[al.source == "offerings"].set_index("raw_string")
    assert off.loc["Bali Service", ["course_id", "method"]].tolist() == ["IDN-SVC", "code_match"]
    assert off.loc["Fiji Reef", "method"] == "no_code_did_not_run"
    # no code: never fuzzy- or containment-joined to a course that ran
    assert off.loc["Nepal Trek Advanced", "course_id"].startswith("NR-")
    assert cat.loc["IDN-SVC", "ran"] == "y" and cat.loc[off.loc["Fiji Reef", "course_id"], "ran"] == "n"


def test_coded_offering_contradictions_are_flagged(tmp_path):
    cfg = mini(tmp_path,
               coded_offerings=[["IDN-SVC", "Bali Service", "Denpasar", "Indonesia"],
                                ["NPL-TRK", "Nepal Trek", "Kathmandu", "Nepal"],
                                ["FJI-REF", "Fiji Reef", "Nadi", "Fiji"],          # code, no row
                                ["", "Laos Weaving", "Luang Prabang", "Laos"],     # no code, has row
                                ["PER-TRK", "Peru Trek", "Cusco", "Peru"]],        # code, other name
               placements=[["IDN-SVC", "Bali Service", "Alan Abbott", ""],
                           ["NPL-TRK", "Nepal Trek", "Brian Baker", ""],
                           ["LAO-WVG", "Laos Weaving", "Carla Cruz", ""],
                           ["PER-TRK", "Andes Photography", "Dana Diaz", ""]])
    s1.run(cfg, quiet=True)
    al, cat = _drafts(cfg)
    off = al[al.source == "offerings"].set_index("raw_string")
    assert off.loc["Fiji Reef", ["course_id", "method"]].tolist() == ["FJI-REF", "CODE_NOT_IN_PLACEMENTS"]
    assert cat.loc["FJI-REF", "ran"] == "unknown" and "MISSING_FROM_PLACEMENTS" in cat.loc["FJI-REF", "flags"]
    assert off.loc["Laos Weaving", ["course_id", "method"]].tolist() == ["LAO-WVG", "NO_CODE_BUT_IN_PLACEMENTS"]
    assert off.loc["Peru Trek", ["course_id", "method"]].tolist() == ["PER-TRK", "CODE_MATCH_NAMES_DIFFER"]


def test_confirmed_did_not_run_is_challenged_when_the_offering_gains_a_code(tmp_path):
    cfg = mini(tmp_path, coded_offerings=CODED)
    s1.run(cfg, quiet=True)
    confirm_all(cfg)
    s1.accept(cfg)
    mini(tmp_path, coded_offerings=CODED[:2] + [["FJI-REF", "Fiji Reef", "Nadi", "Fiji"]])
    s1.run(cfg, quiet=True)
    al, _ = _drafts(cfg)
    fiji = al[(al.source == "offerings") & (al.raw_string == "Fiji Reef")].iloc[0]
    assert fiji["method"] == "LOCK_CONFLICT" and fiji["conflict_with"] == "FJI-REF"


SG_PL = [["IDN-SVC", "Bali Service", "Alan Abbott", "Carla Cruz"],
         ["NPL-TRK", "Nepal Trek", "Brian Baker", ""],
         ["SING-1", "Singapore Heritage", "Dana Diaz", ""]]
SG_FORM = [[f"ddiaz@{D}", "Singapore Heritage", "Singapore Film"],
           [f"eevans@{D}", "Singapore Film", "Singapore Heritage"]]
SG_LIST = {"expected_sg_codes": ["SING-1", "SING-2"]}


def test_listed_singapore_course_missing_from_placements(tmp_path):
    cfg = mini(tmp_path, placements=SG_PL, sg=SG_FORM, extra=SG_LIST)
    report = s1.run(cfg, quiet=True)
    al, cat = _drafts(cfg)
    film = al[(al.source == "sg") & (al.raw_string == "Singapore Film")].iloc[0]
    assert film["course_id"] == "SING-2" and film["method"] == "GUESS_MISSING_SG_COURSE"
    assert cat.loc["SING-2", ["course_type", "ran"]].tolist() == ["sg", "unknown"]
    assert report["courses"]["C"]["missing"] == ["SING-2"]
    confirm_all(cfg)
    s1.accept(cfg)
    s2.run(cfg, quiet=True)
    c = pd.read_csv(tmp_path / "derived/courses.csv", dtype=str).fillna("").set_index("course_id")
    assert c.loc["SING-2", "ran"] == "" and c.loc["SING-1", "ran"] == "True"
    ch = pd.read_csv(tmp_path / "derived/checks.csv", dtype=str)
    assert ((ch["check"] == "course_missing_from_placements") & (ch["course_id"] == "SING-2")).sum() == 1


def test_office_says_it_did_not_run(tmp_path):
    cfg = mini(tmp_path, placements=SG_PL, sg=SG_FORM,
               extra={**SG_LIST, "not_run_codes": ["SING-2"]})
    s1.run(cfg, quiet=True)
    _, cat = _drafts(cfg)
    assert cat.loc["SING-2", "ran"] == "n" and "MISSING" not in cat.loc["SING-2", "flags"]
    confirm_all(cfg)
    s1.accept(cfg)
    s2.run(cfg, quiet=True)
    c = pd.read_csv(tmp_path / "derived/courses.csv", dtype=str).fillna("").set_index("course_id")
    assert c.loc["SING-2", "ran"] == "False"


def test_no_guess_when_two_singapore_strings_are_unmatched(tmp_path):
    cfg = mini(tmp_path, placements=SG_PL, extra=SG_LIST,
               sg=SG_FORM + [[f"ffox@{D}", "Singapore Pottery", "Singapore Heritage"]])
    report = s1.run(cfg, quiet=True)
    al, _ = _drafts(cfg)
    sgs = al[al.source == "sg"].set_index("raw_string")
    assert sgs.loc["Singapore Film", "course_id"] == "" == sgs.loc["Singapore Pottery", "course_id"]
    assert any("SING-2" in n for n in report["notes"])


def test_unconfigured_column_is_reported_and_ignore_cols_may_name_a_deleted_column(tmp_path):
    cfg = mini(tmp_path, r1_extra_col=True)
    report = s1.run(cfg, quiet=True)
    assert any("'Stray'" in n for n in report["notes"])
    mini(tmp_path, extra={})                      # column deleted from the file...
    cfg = load_config(tmp_path / "cfg.yaml")
    cfg["cycles"]["C"]["preferences"][0]["ignore_cols"] = ["Stray"]   # ...but still listed
    assert load_cycle(cfg, "C").extra_columns == []


def test_listed_course_nobody_ranked_still_appears_in_courses(tmp_path):
    cfg = mini(tmp_path, placements=SG_PL, sg=[[f"ddiaz@{D}", "Singapore Heritage", ""]],
               extra={**SG_LIST, "not_run_codes": ["SING-2"]})
    s1.run(cfg, quiet=True)
    confirm_all(cfg)
    s1.accept(cfg)
    s2.run(cfg, quiet=True)
    c = pd.read_csv(tmp_path / "derived/courses.csv", dtype=str).fillna("").set_index("course_id")
    assert c.loc["SING-2", ["course_type", "ran"]].tolist() == ["sg", "False"]


def test_no_code_offering_is_never_joined_by_containment_or_country(tmp_path):
    cfg = mini(tmp_path,
               coded_offerings=[["IDN-SVC", "Bali Service", "Denpasar", "Indonesia"],
                                ["", "Laos Weaving", "Luang Prabang", "Laos"],
                                ["", "Fiji Reef", "Nadi", "Fiji"]],
               placements=[["IDN-SVC", "Bali Service", "Alan Abbott", ""],
                           ["LAO-WVG", "Laos Weaving Week", "Brian Baker", ""],   # contains it
                           ["FJI-DIV", "Fiji Diving", "Carla Cruz", ""]])        # same country
    s1.run(cfg, quiet=True)
    al, _ = _drafts(cfg)
    off = al[al.source == "offerings"].set_index("raw_string")
    assert off.loc["Laos Weaving", "course_id"].startswith("NR-")
    assert off.loc["Fiji Reef", "course_id"].startswith("NR-")


def test_singapore_list_decides_type_and_flags_strays(tmp_path):
    cfg = mini(tmp_path, extra=SG_LIST, sg=[[f"ddiaz@{D}", "Singapore Heritage", ""]],
               placements=SG_PL + [["SING-2", "Singapore Film", "Eve Evans", ""],   # nobody ranks it
                                   ["SING-5", "Singapore Pottery", "Fay Fox", ""]])  # not listed
    s1.run(cfg, quiet=True)
    _, cat = _drafts(cfg)
    assert cat.loc["SING-2", "type_evidence"] == "listed in expected_sg_codes"
    assert "ASSUMED_SG" not in cat.loc["SING-2", "flags"]
    assert "SG_BUT_NOT_IN_SG_LIST" in cat.loc["SING-5", "flags"]
