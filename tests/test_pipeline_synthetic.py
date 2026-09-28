"""End to end on invented data with the real files' layout, scored against truth.

Generates a two-cycle dataset (tools/make_synthetic.py), runs stage 1 with the
real example config, checks every proposed identity and course link against
the ground truth, then confirms everything, runs stage 2, and checks the
derived tables, the consistency checks, stability on rerun, and leakage.
"""

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import apply_pseudonymization as s2  # noqa: E402
import build_crosswalk as s1  # noqa: E402
from idmap import load_config, norm_course  # noqa: E402
from leakcheck import find_leaks  # noqa: E402
from make_synthetic import generate  # noqa: E402


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic")
    truth = generate(root, seed=7)
    cfg_d = yaml.safe_load((ROOT / "config/pseudonymize.example.yaml").read_text())
    cfg_d["private_root"] = str(root)
    cp = root / "config.yaml"
    cp.write_text(yaml.safe_dump(cfg_d))
    cfg = load_config(cp)
    report = s1.run(cfg, quiet=True)
    return dict(root=root, truth=truth, cfg=cfg, report=report)


def _csv(root, rel):
    return pd.read_csv(root / rel, dtype=str).fillna("")


def _truth_keys(truth):
    m = {}
    for pid, p in truth["persons"].items():
        for v in p["emails"] + p["names"]:
            m[s1.node_key(v)] = pid
    return m


def _tid_to_pid(world, rel=s1.ID_DRAFT):
    d = _csv(world["root"], rel)
    tk = _truth_keys(world["truth"])
    out = {}
    for tid, g in d.groupby("teacher_id"):
        pids = {tk.get(s1.node_key(x)) for x in g["identifier"]} - {None}
        out[tid] = pids.pop() if len(pids) == 1 else None
    return out


def _clusters(world, rel=s1.ID_DRAFT):
    d = _csv(world["root"], rel)
    tk = _truth_keys(world["truth"])
    out = {}
    for tid, g in d.groupby("teacher_id"):
        out[tid] = dict(pids=[tk.get(s1.node_key(x)) for x in g["identifier"]],
                        flags=set(filter(None, g["cluster_flags"].iloc[0].split("|"))),
                        idents=list(g["identifier"]))
    return out


def test_unflagged_identity_proposals_are_all_correct(world):
    cl = _clusters(world)
    assert all(None not in c["pids"] for c in cl.values()), "identifier missing from truth"
    pid_tids = defaultdict(set)
    for tid, c in cl.items():
        for p in c["pids"]:
            pid_tids[p].add(tid)
    wrong = {tid for tid, c in cl.items()
             if len(set(c["pids"])) > 1 or any(len(pid_tids[p]) > 1 for p in c["pids"])}
    unflagged_wrong = [tid for tid in wrong if not (cl[tid]["flags"] & set(s1.SERIOUS))]
    assert not unflagged_wrong, [(t, cl[t]) for t in unflagged_wrong]
    # only the two deliberately undecidable cases may be wrong (and they are flagged)
    sp = world["truth"]["special"]
    allowed = [{sp["sam"], sp["samantha"]}, {sp["qiang"], sp["quinn"]}]
    assert all(any(set(cl[t]["pids"]) <= a for a in allowed) for t in wrong), \
        [(t, cl[t]) for t in wrong]


def test_hard_identity_cases(world):
    cl = _clusters(world)
    sp = world["truth"]["special"]
    by_pid = defaultdict(list)
    for tid, c in cl.items():
        for p in set(c["pids"]):
            by_pid[p].append(c)
    [david] = by_pid[sp["david"]]
    assert set(david["pids"]) == {sp["david"]} and "LOW_MARGIN" in david["flags"]
    [dana] = by_pid[sp["dana"]]
    assert set(dana["pids"]) == {sp["dana"]} and "NEAR_MISS" in dana["flags"]
    [martin] = by_pid[sp["martin"]]
    assert set(martin["pids"]) == {sp["martin"]} and "MULTI_NAME" in martin["flags"]
    [maria] = by_pid[sp["maria"]]
    assert len(maria["idents"]) == 3
    [twm] = by_pid[sp["twm"]]
    assert "WEAK_LINK" in twm["flags"]
    sam_clusters = by_pid[sp["sam"]] + by_pid[sp["samantha"]]
    for c in sam_clusters:
        names = {x.lower() for x in c["idents"] if "@" not in x}
        assert len(names) == 1, "one person, one name: Sam and Samantha never merged together"
        assert len(c["idents"]) == 2 and "LOW_MARGIN" in c["flags"]
    # undecidable from the data (slee@ vs slee2@): either assignment is acceptable,
    # but it must be flagged, which is asserted above
    [zhou] = {id(c): c for c in by_pid[sp["quinn"]]}.values()
    assert "PLACED_OFF_LIST" in zhou["flags"], "qzhou@ linked to Quinn must be flagged"


def test_course_links_match_truth(world):
    root, truth = world["root"], world["truth"]
    al, cat = _csv(root, s1.ALIAS_DRAFT), _csv(root, s1.CAT_DRAFT)
    tkey = {(r.cycle, r.course_id): (r.trip_code or "NR:" + norm_course(r.offerings_name))
            for r in cat.itertuples()}
    errs = []
    for r in al.itertuples():
        want = truth["aliases"][r.cycle][r.source].get(r.raw_string)
        got = tkey.get((r.cycle, r.course_id))
        if want is None or got != want:
            errs.append((r.cycle, r.source, r.raw_string, r.method, got, want))
    assert not errs, errs


def test_catalogue_types_and_ran_match_truth(world):
    root, truth = world["root"], world["truth"]
    cat = _csv(root, s1.CAT_DRAFT)
    seen, errs = defaultdict(set), []
    for r in cat.itertuples():
        k = r.trip_code or "NR:" + norm_course(r.offerings_name)
        want = truth["courses"][r.cycle].get(k)
        seen[r.cycle].add(k)
        ran = {"y": True, "n": False, "unknown": None}[r.ran]
        if not want or want["type"] != r.course_type or want["ran"] != ran:
            errs.append((r.cycle, k, r.course_type, r.ran, want))
    for cyc, courses in truth["courses"].items():
        errs += [(cyc, k, "missing") for k in courses if k not in seen[cyc]]
    assert not errs, errs


def _review_like_a_human(world):
    """Correct any wrong identity rows the way the user would: by editing teacher_id."""
    root = world["root"]
    d = _csv(root, s1.ID_DRAFT)
    tk = _truth_keys(world["truth"])
    d["pid"] = [tk[s1.node_key(x)] for x in d["identifier"]]
    chosen, used = {}, set()
    for pid, g in d.sort_values("kind").groupby("pid", sort=True):
        tid = g["teacher_id"].iloc[0]
        if tid in used:
            tid = next(f"T{i:03d}" for i in range(999, 0, -1)
                       if f"T{i:03d}" not in set(d["teacher_id"]) | used)
        chosen[pid] = tid
        used.add(tid)
    new = d["pid"].map(chosen)
    moved = new != d["teacher_id"]
    d.loc[moved, "notes"] = "checked with office: different person"
    d["teacher_id"] = new
    d.drop(columns="pid").to_csv(root / s1.ID_DRAFT, index=False)


@pytest.fixture(scope="module")
def built(world):
    root, cfg = world["root"], world["cfg"]
    _review_like_a_human(world)
    for rel in (s1.ID_DRAFT, s1.ALIAS_DRAFT, s1.CAT_DRAFT):
        df = _csv(root, rel)
        df["confirmed"] = "y"
        df.to_csv(root / rel, index=False)
    s1.accept(cfg)
    return s2.run(cfg, quiet=True)


def test_placements_match_truth(world, built):
    root, truth = world["root"], world["truth"]
    t2p = _tid_to_pid(world, s1.ID_FINAL)
    pl = _csv(root, "derived/placements.csv")
    got = {(r.cycle, r.course_id, int(r.sponsor_slot), t2p[r.teacher_id])
           for r in pl.itertuples() if r.status == "assigned"}
    want = {(cyc, c, int(s), p) for cyc, rows in truth["placements"].items() for c, s, p in rows}
    assert got == want, (sorted(got - want)[:5], sorted(want - got)[:5])


def test_preferences_match_truth(world, built):
    root, truth = world["root"], world["truth"]
    t2p = _tid_to_pid(world, s1.ID_FINAL)
    cat = _csv(root, s1.CAT_FINAL)
    tkey = {(r.cycle, r.course_id): (r.trip_code or "NR:" + norm_course(r.offerings_name))
            for r in cat.itertuples()}
    pr = _csv(root, "derived/preferences.csv")
    got = {(r.cycle, r.round, t2p[r.teacher_id], int(r.rank), tkey[(r.cycle, r.course_id)])
           for r in pr.itertuples()}
    want = {tuple(x) for x in truth["prefs"]}
    assert got == want, (sorted(got - want)[:5], sorted(want - got)[:5])


def test_derived_keys_are_unique(world, built):
    root = world["root"]
    assert not _csv(root, "derived/preferences.csv").duplicated(
        ["cycle", "teacher_id", "round", "rank"]).any()
    assert not _csv(root, "derived/teachers.csv").duplicated(["cycle", "teacher_id"]).any()
    assert not _csv(root, "derived/placements.csv").duplicated(
        ["cycle", "course_id", "sponsor_slot"]).any()


def test_repeaters_and_unknowns(world, built):
    root, truth = world["root"], world["truth"]
    t2p = _tid_to_pid(world, s1.ID_FINAL)
    t = _csv(root, "derived/teachers.csv")
    t26, t27 = t[t.cycle == "2026"], t[t.cycle == "2027"]
    assert (t26["is_repeater"] == "").all(), "2026 has no repeat file: status must be unknown"
    assert (t26["submitted_intl_r2"] == "").all(), "2026 had no round 2"
    got = {t2p[r.teacher_id]: r.prior_course_id for r in t27.itertuples() if r.is_repeater == "True"}
    assert got == truth["repeaters"]["2027"]


def test_expected_checks(world, built):
    c = _csv(world["root"], "derived/checks.csv")
    n = (c["check"] == "prior_course_differs_from_previous_placement").sum()
    assert n == world["truth"]["expected_checks"]["prior_course_differs_from_previous_placement"]
    assert (c["check"] == "placed_without_any_response").sum() == 1       # Quinn
    assert (c["check"] == "submitted_but_not_placed").sum() >= 1          # Qiang
    assert not (c["check"] == "placed_on_course_not_in_any_list").any()   # after the fix
    missing = c[c["check"] == "course_missing_from_placements"]
    assert missing[["cycle", "course_id"]].values.tolist() == [["2026", "SING-9"]]
    co = _csv(world["root"], "derived/courses.csv")
    sing9 = co[(co.cycle == "2026") & (co.course_id == "SING-9")].iloc[0]
    assert sing9["ran"] == "" and sing9["course_type"] == "sg"
    assert not (c["check"] == "repeater_placed_on_other_course").any()
    assert not (c["check"] == "placed_on_more_than_one_course").any()


def test_no_leaks(world, built):
    leaks = find_leaks(world["cfg"])
    assert not leaks["emails"] and not leaks["domains"] and not leaks["stray_text_files"], leaks
    assert not leaks["tokens"], leaks["tokens"]


def test_manifest_records_inputs_and_key(built):
    assert set(built["inputs_sha256"]) == {"2026", "2027"}
    assert len(built["key_sha256"]) == 3
    assert built["counts"]["2026"]["repeaters"] is None


def test_rerun_keeps_ids_and_confirmations(world, built):
    root, cfg = world["root"], world["cfg"]
    before = _csv(root, s1.ID_FINAL)[["identifier", "teacher_id"]]
    s1.run(cfg, quiet=True)
    after = _csv(root, s1.ID_DRAFT)
    m = before.merge(after[["identifier", "teacher_id", "confirmed"]], on="identifier")
    assert len(m) == len(before)
    assert (m["teacher_id_x"] == m["teacher_id_y"]).all()
    assert (m["confirmed"] == "y").all()
    assert (_csv(root, s1.ALIAS_DRAFT)["confirmed"] == "y").all()


def test_coding_sheet_survives_rebuild(world, built):
    root, cfg = world["root"], world["cfg"]
    sheet = root / "freetext/coding_sheet.csv"
    df = _csv(root, "freetext/coding_sheet.csv")
    df.loc[df.index[0], "req_certification"] = "scuba"
    df.to_csv(sheet, index=False)
    s2.run(cfg, quiet=True)
    assert _csv(root, "freetext/coding_sheet.csv").loc[0, "req_certification"] == "scuba"


def test_stage2_refuses_uncovered_identity(world, built):
    root, cfg = world["root"], world["cfg"]
    p = root / s1.ID_FINAL
    full = _csv(root, s1.ID_FINAL)
    full.iloc[1:].to_csv(p, index=False)
    try:
        with pytest.raises(SystemExit):
            s2.run(cfg, quiet=True)
    finally:
        full.to_csv(p, index=False)
