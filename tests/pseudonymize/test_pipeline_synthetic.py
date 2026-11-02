"""End to end on invented data with the real files' layout, scored against truth.

Generates a two-cycle dataset (tools/make_synthetic.py) and, with the real
example config, runs each cycle in its own folders, oldest first, the way the
user would: stage 1, review the drafts (here: correct them from the truth and
confirm everything), accept, stage 2. The proposals are scored against the
truth as stage 1 left them; then the derived tables, the consistency checks,
IDs carried across cycles, stability on rerun, and leakage are checked.
"""

from collections import defaultdict

import pandas as pd
import pytest
import yaml
from make_synthetic import generate

import stable_sponsors.pseudonymize.apply_pseudonymization as s2
import stable_sponsors.pseudonymize.build_crosswalk as s1
from stable_sponsors.pseudonymize.idmap import (
    REPO_ROOT,
    load_config,
    norm_course,
    out_path,
)
from stable_sponsors.pseudonymize.layout import prepare_cycle
from stable_sponsors.pseudonymize.leakcheck import find_leaks

CYCLES = ("2026", "2027")
DRAFTS = (s1.ID_DRAFT, s1.ALIAS_DRAFT, s1.CAT_DRAFT)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic")
    truth = generate(root, seed=7)
    cfg_d = yaml.safe_load((REPO_ROOT / "config/pseudonymize.example.yaml").read_text())
    cfg_d["private_root"] = str(root)
    cp = root / "config.yaml"
    cp.write_text(yaml.safe_dump(cfg_d))
    cfg = load_config(cp)
    world = {"root": root, "truth": truth, "cfg": cfg}
    world["ccfg"] = {c: prepare_cycle(cfg, c, quiet=True) for c in CYCLES}
    world["proposals"], world["reports"], world["manifests"] = {}, {}, {}
    for c in CYCLES:
        ccfg = world["ccfg"][c]
        world["reports"][c] = s1.run(ccfg, quiet=True)
        world["proposals"][c] = {rel: _csv(ccfg, rel) for rel in DRAFTS}
        _review_like_a_human(world, c)
        for rel in DRAFTS:
            df = _csv(ccfg, rel)
            df["confirmed"] = "y"
            df.to_csv(out_path(ccfg, rel), index=False)
        s1.accept(ccfg)
        world["manifests"][c] = s2.run(ccfg, quiet=True)
    return world


@pytest.fixture(scope="module")
def built(world):
    return world["manifests"]


def _csv(ccfg, rel):
    return pd.read_csv(out_path(ccfg, rel), dtype=str).fillna("")


def _derived(world, name):
    """One derived table, every cycle's rows together."""
    return pd.concat(
        [_csv(world["ccfg"][c], f"derived/{name}.csv") for c in CYCLES],
        ignore_index=True,
    )


def _course_truth_key(r):
    """A catalogue row's key in truth: its trip code, or NR:<name> if it did not run."""
    return r.trip_code or "NR:" + norm_course(r.offerings_name)


def _truth_keys(truth):
    m = {}
    for pid, p in truth["persons"].items():
        for v in p["emails"] + p["names"]:
            m[s1.node_key(v)] = pid
    return m


def _tid_to_pid(world):
    """T### -> person, from every cycle's accepted key."""
    tk = _truth_keys(world["truth"])
    d = pd.concat([_csv(world["ccfg"][c], s1.ID_FINAL) for c in CYCLES])
    out = {}
    for tid, g in d.groupby("teacher_id"):
        pids = {tk.get(s1.node_key(x)) for x in g["identifier"]} - {None}
        out[tid] = pids.pop() if len(pids) == 1 else None
    return out


def _clusters(world, cycle):
    """Stage 1's proposals for one cycle, before review."""
    d = world["proposals"][cycle][s1.ID_DRAFT]
    tk = _truth_keys(world["truth"])
    out = {}
    for tid, g in d.groupby("teacher_id"):
        out[tid] = {
            "tid": tid,
            "pids": [tk.get(s1.node_key(x)) for x in g["identifier"]],
            "flags": set(filter(None, g["cluster_flags"].iloc[0].split("|"))),
            "idents": list(g["identifier"]),
        }
    return out


def _review_like_a_human(world, cycle):
    """Correct any wrong identity rows the way the user would: by editing teacher_id.

    Someone already in another cycle's accepted key gets that ID back, as the
    user would copy it over.
    """
    ccfg = world["ccfg"][cycle]
    d = _csv(ccfg, s1.ID_DRAFT)
    tk = _truth_keys(world["truth"])
    d["pid"] = [tk[s1.node_key(x)] for x in d["identifier"]]
    known = {}
    for c in CYCLES:
        p = out_path(world["ccfg"][c], s1.ID_FINAL)
        if c != cycle and p.exists():
            f = pd.read_csv(p, dtype=str)
            known |= {tk[s1.node_key(x)]: t for x, t in zip(f.identifier, f.teacher_id)}
    used = set(known.values())
    chosen = {}
    for pid, g in d.sort_values("kind").groupby("pid", sort=True):
        tid = known.get(pid) or g["teacher_id"].iloc[0]
        if pid not in known and tid in used:
            tid = next(
                f"T{i:03d}"
                for i in range(999, 0, -1)
                if f"T{i:03d}" not in set(d["teacher_id"]) | used
            )
        chosen[pid] = tid
        used.add(tid)
    new = d["pid"].map(chosen)
    moved = new != d["teacher_id"]
    d.loc[moved, "notes"] = "checked with office: different person"
    d["teacher_id"] = new
    d.drop(columns="pid").to_csv(out_path(ccfg, s1.ID_DRAFT), index=False)


@pytest.mark.parametrize("cycle", CYCLES)
def test_unflagged_identity_proposals_are_all_correct(world, cycle):
    cl = _clusters(world, cycle)
    assert all(None not in c["pids"] for c in cl.values()), (
        "identifier missing from truth"
    )
    pid_tids = defaultdict(set)
    for tid, c in cl.items():
        for p in c["pids"]:
            pid_tids[p].add(tid)
    wrong = {
        tid
        for tid, c in cl.items()
        if len(set(c["pids"])) > 1 or any(len(pid_tids[p]) > 1 for p in c["pids"])
    }
    unflagged_wrong = [tid for tid in wrong if not (cl[tid]["flags"] & set(s1.SERIOUS))]
    assert not unflagged_wrong, [(t, cl[t]) for t in unflagged_wrong]
    # only the two deliberately undecidable cases may be wrong (and they are flagged)
    sp = world["truth"]["special"]
    allowed = [{sp["sam"], sp["samantha"]}, {sp["qiang"], sp["quinn"]}]
    assert all(any(set(cl[t]["pids"]) <= a for a in allowed) for t in wrong), [
        (t, cl[t]) for t in wrong
    ]


def test_hard_identity_cases(world):
    sp = world["truth"]["special"]
    by_pid = defaultdict(list)  # person -> their cluster in each cycle they appear in
    for cycle in CYCLES:
        for c in _clusters(world, cycle).values():
            for p in set(c["pids"]):
                by_pid[p].append(c)
    [david] = by_pid[sp["david"]]
    assert set(david["pids"]) == {sp["david"]} and "LOW_MARGIN" in david["flags"]
    [dana] = by_pid[sp["dana"]]
    assert set(dana["pids"]) == {sp["dana"]} and "NEAR_MISS" in dana["flags"]
    martin = by_pid[sp["martin"]]
    assert all(set(c["pids"]) == {sp["martin"]} for c in martin)
    assert any("MULTI_NAME" in c["flags"] for c in martin)
    maria = by_pid[sp["maria"]]
    assert all(set(c["pids"]) == {sp["maria"]} for c in maria)
    assert len({c["tid"] for c in maria}) == 1, "one ID in both cycles"
    assert len({i for c in maria for i in c["idents"]}) == 3
    [twm] = by_pid[sp["twm"]]
    assert "WEAK_LINK" in twm["flags"]
    sam_clusters = by_pid[sp["sam"]] + by_pid[sp["samantha"]]
    for c in sam_clusters:
        names = {x.lower() for x in c["idents"] if "@" not in x}
        assert len(names) == 1, (
            "one person, one name: Sam and Samantha never merged together"
        )
        assert len(c["idents"]) == 2 and "LOW_MARGIN" in c["flags"]
    # undecidable from the data (slee@ vs slee2@): either assignment is acceptable,
    # but it must be flagged, which is asserted above
    [zhou] = {id(c): c for c in by_pid[sp["quinn"]]}.values()
    assert "PLACED_OFF_LIST" in zhou["flags"], "qzhou@ linked to Quinn must be flagged"


def test_proposals_reuse_the_previous_cycles_ids(world):
    """2027 is built after 2026 was accepted: anyone whose email or name is in the
    2026 key is proposed under their 2026 ID, before any review."""
    tk = _truth_keys(world["truth"])
    key26 = _csv(world["ccfg"]["2026"], s1.ID_FINAL)
    id26 = {s1.node_key(x): t for x, t in zip(key26.identifier, key26.teacher_id)}
    prop27 = world["proposals"]["2027"][s1.ID_DRAFT]
    shared = [
        (tk[k], id26[k], t)
        for k, t in (
            (s1.node_key(x), t) for x, t in zip(prop27.identifier, prop27.teacher_id)
        )
        if k in id26
    ]
    assert len({pid for pid, _, _ in shared}) >= 20  # every continuing teacher
    assert all(t26 == t27 for _, t26, t27 in shared), [
        x for x in shared if x[1] != x[2]
    ]
    assert world["reports"]["2027"]["identity"]["shared_with_other_cycles"] > 0
    # and no one who is new in 2027 was handed a 2026 ID
    new = {tk[s1.node_key(x)] for x in prop27.identifier} - {
        tk[s1.node_key(x)] for x in key26.identifier
    }
    new_ids = {
        t
        for x, t in zip(prop27.identifier, prop27.teacher_id)
        if tk[s1.node_key(x)] in new
    }
    assert new and new_ids and not new_ids & set(key26.teacher_id)


def test_each_cycle_has_its_own_folders(world):
    root = world["root"]
    for c in CYCLES:
        for area in ("key", "derived", "freetext"):
            assert (root / area / c).is_dir()
        assert (root / "key" / c / "identity.csv").exists()
        assert (root / "derived" / c / "teachers.csv").exists()
    # nothing in the old flat places; one ID registry for all cycles
    assert not [p for p in (root / "derived").iterdir() if p.is_file()]
    assert (root / "key" / "issued_ids.txt").exists()
    assert not list((root / "key").glob("*/issued_ids.txt"))


def test_course_links_match_truth(world):
    truth = world["truth"]
    errs = []
    for cycle in CYCLES:
        drafts = world["proposals"][cycle]
        al, cat = drafts[s1.ALIAS_DRAFT], drafts[s1.CAT_DRAFT]
        tkey = {(r.cycle, r.course_id): _course_truth_key(r) for r in cat.itertuples()}
        for r in al.itertuples():
            want = truth["aliases"][r.cycle][r.source].get(r.raw_string)
            got = tkey.get((r.cycle, r.course_id))
            if want is None or got != want:
                errs.append((r.cycle, r.source, r.raw_string, r.method, got, want))
    assert not errs, errs


def test_catalogue_types_and_ran_match_truth(world):
    truth = world["truth"]
    cat = pd.concat([world["proposals"][c][s1.CAT_DRAFT] for c in CYCLES])
    seen, errs = defaultdict(set), []
    for r in cat.itertuples():
        k = _course_truth_key(r)
        want = truth["courses"][r.cycle].get(k)
        seen[r.cycle].add(k)
        ran = {"y": True, "n": False, "unknown": None}[r.ran]
        if not want or want["type"] != r.course_type or want["ran"] != ran:
            errs.append((r.cycle, k, r.course_type, r.ran, want))
    for cyc, courses in truth["courses"].items():
        errs += [(cyc, k, "missing") for k in courses if k not in seen[cyc]]
    assert not errs, errs


def test_placements_match_truth(world, built):
    truth = world["truth"]
    t2p = _tid_to_pid(world)
    pl = _derived(world, "placements")
    got = {
        (r.cycle, r.course_id, int(r.sponsor_slot), t2p[r.teacher_id])
        for r in pl.itertuples()
        if r.status == "assigned"
    }
    want = {
        (cyc, c, int(s), p)
        for cyc, rows in truth["placements"].items()
        for c, s, p in rows
    }
    assert got == want, (sorted(got - want)[:5], sorted(want - got)[:5])


def test_preferences_match_truth(world, built):
    truth = world["truth"]
    t2p = _tid_to_pid(world)
    cat = pd.concat([_csv(world["ccfg"][c], s1.CAT_FINAL) for c in CYCLES])
    tkey = {(r.cycle, r.course_id): _course_truth_key(r) for r in cat.itertuples()}
    pr = _derived(world, "preferences")
    got = {
        (r.cycle, r.round, t2p[r.teacher_id], int(r.rank), tkey[(r.cycle, r.course_id)])
        for r in pr.itertuples()
    }
    want = {tuple(x) for x in truth["prefs"]}
    assert got == want, (sorted(got - want)[:5], sorted(want - got)[:5])


def test_slot_tags_match_truth(world, built):
    t2p = _tid_to_pid(world)
    pr = _derived(world, "preferences")
    got = {
        (r.cycle, r.round, t2p[r.teacher_id], int(r.rank), r.slot_gender)
        for r in pr.itertuples()
        if r.slot_gender
    }
    want = {tuple(x) for x in world["truth"]["slot_tags"]}
    assert want and got == want, (sorted(got - want)[:5], sorted(want - got)[:5])


def test_derived_keys_are_unique(world, built):
    assert (
        not _derived(world, "preferences")
        .duplicated(["cycle", "teacher_id", "round", "rank"])
        .any()
    )
    assert not _derived(world, "teachers").duplicated(["cycle", "teacher_id"]).any()
    assert (
        not _derived(world, "placements")
        .duplicated(["cycle", "course_id", "sponsor_slot"])
        .any()
    )


def test_repeaters_and_unknowns(world, built):
    truth = world["truth"]
    t2p = _tid_to_pid(world)
    t = _derived(world, "teachers")
    t26, t27 = t[t.cycle == "2026"], t[t.cycle == "2027"]
    assert (t26["is_repeater"] == "").all(), (
        "2026 has no repeat file: status must be unknown"
    )
    assert (t26["submitted_intl_r2"] == "").all(), "2026 had no round 2"
    got = {
        t2p[r.teacher_id]: r.prior_course_id
        for r in t27.itertuples()
        if r.is_repeater == "True"
    }
    assert got == truth["repeaters"]["2027"]


def test_expected_checks(world, built):
    c = _derived(world, "checks")
    n = (c["check"] == "prior_course_differs_from_previous_placement").sum()
    assert (
        n
        == world["truth"]["expected_checks"][
            "prior_course_differs_from_previous_placement"
        ]
    )
    assert (c["check"] == "placed_without_any_response").sum() == 1  # Quinn
    assert (c["check"] == "submitted_but_not_placed").sum() >= 1  # Qiang
    assert not (c["check"] == "placed_on_course_not_in_any_list").any()  # after the fix
    missing = c[c["check"] == "course_missing_from_placements"]
    assert missing[["cycle", "course_id"]].values.tolist() == [["2026", "SING-9"]]
    co = _derived(world, "courses")
    sing9 = co[(co.cycle == "2026") & (co.course_id == "SING-9")].iloc[0]
    assert sing9["ran"] == "" and sing9["course_type"] == "sg"
    assert not (c["check"] == "repeater_placed_on_other_course").any()
    assert not (c["check"] == "placed_on_more_than_one_course").any()


@pytest.mark.parametrize("cycle", CYCLES)
def test_no_leaks(world, built, cycle):
    leaks = find_leaks(world["ccfg"][cycle])
    assert (
        not leaks["emails"] and not leaks["domains"] and not leaks["stray_text_files"]
    ), leaks
    assert not leaks["tokens"], leaks["tokens"]


def test_manifest_records_inputs_and_key(built):
    for cycle, m in built.items():
        assert m["cycle"] == cycle and set(m["inputs_sha256"]) == {cycle}
        assert len(m["key_sha256"]) == 3
    assert built["2026"]["counts"]["2026"]["repeaters"] is None
    assert built["2026"]["previous_cycle_placements"] == {"cycle": None, "sha256": None}
    prev = built["2027"]["previous_cycle_placements"]
    assert prev["cycle"] == "2026" and prev["sha256"]


@pytest.mark.parametrize("cycle", CYCLES)
def test_rerun_keeps_ids_and_confirmations(world, built, cycle):
    ccfg = world["ccfg"][cycle]
    before = _csv(ccfg, s1.ID_FINAL)[["identifier", "teacher_id"]]
    s1.run(ccfg, quiet=True)
    after = _csv(ccfg, s1.ID_DRAFT)
    m = before.merge(after[["identifier", "teacher_id", "confirmed"]], on="identifier")
    assert len(m) == len(before)
    assert (m["teacher_id_x"] == m["teacher_id_y"]).all()
    assert (m["confirmed"] == "y").all()
    assert (_csv(ccfg, s1.ALIAS_DRAFT)["confirmed"] == "y").all()


def test_coding_sheet_survives_rebuild(world, built):
    ccfg = world["ccfg"]["2027"]
    sheet = out_path(ccfg, "freetext/coding_sheet.csv")
    df = _csv(ccfg, "freetext/coding_sheet.csv")
    df.loc[df.index[0], "req_certification"] = "scuba"
    df.to_csv(sheet, index=False)
    s2.run(ccfg, quiet=True)
    assert (
        _csv(ccfg, "freetext/coding_sheet.csv").loc[0, "req_certification"] == "scuba"
    )


def test_stage2_refuses_uncovered_identity(world, built):
    ccfg = world["ccfg"]["2027"]
    p = out_path(ccfg, s1.ID_FINAL)
    full = _csv(ccfg, s1.ID_FINAL)
    full.iloc[1:].to_csv(p, index=False)
    try:
        with pytest.raises(SystemExit):
            s2.run(ccfg, quiet=True)
    finally:
        full.to_csv(p, index=False)
