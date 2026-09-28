"""Stage 1 of 2: propose the identity key and the course mapping for review.

    python src/build_crosswalk.py --config config/pseudonymize.yaml
    # review the three drafts under key/, set confirmed=y on every row, then
    python src/build_crosswalk.py --config config/pseudonymize.yaml --accept

Writes under private_root/key/:
    identity_draft.csv         one row per email or name; rows sharing a teacher_id
                               are one person across all cycles
    course_alias_draft.csv     every course string (offerings, forms, prior course)
                               -> course_id
    course_catalogue_draft.csv one row per course per cycle, with its type

Nothing is confirmed automatically. Re-running reads your edited drafts, keeps
every confirmed row and every teacher_id already assigned, and never re-merges
people you split. To give someone a fresh ID, type NEW (or NEW1, NEW2... for
several different new people) in teacher_id; any row whose teacher_id differs
from proposed_id needs a note saying why before --accept will pass.

Console output contains counts, spreadsheet rows, trip codes and pseudonymous
IDs only, so it is safe to share.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from idmap import (
    NONE_COURSE,
    CourseIndex,
    _ratio,
    load_config,
    looks_like_email,
    match_score,
    name_similarity,
    needs_review,
    norm_code,
    norm_course,
    norm_email,
    norm_name,
    out_path,
    phrase_in,
)
from sources import load_all

ID_DRAFT, ID_FINAL = "key/identity_draft.csv", "key/identity.csv"
ALIAS_DRAFT, ALIAS_FINAL = "key/course_alias_draft.csv", "key/course_alias.csv"
CAT_DRAFT, CAT_FINAL = "key/course_catalogue_draft.csv", "key/course_catalogue.csv"
DRAFT_MANIFEST = "key/draft_inputs.json"
ISSUED = "key/issued_ids.txt"  # every teacher_id ever handed out; never reused
YES = {"y", "yes", "true", "1"}
NAME_LINK_MIN = 0.75  # name-to-name similarity needed to merge
LOW_MARGIN = 0.10
STRONG_METHODS = {"same_row", "prior_confirmed", "same_name"}
SERIOUS = [
    "MULTI_EMAIL",
    "MULTI_NAME",
    "PLACED_NO_EMAIL",
    "NO_NAME",
    "LOW_MARGIN",
    "WEAK_LINK",
    "CROSS_CYCLE_LINK",
    "NEAR_MISS",
    "FORM_NAME_UNLIKE_EMAIL",
    "TWO_SLOTS_SAME_CYCLE",
    "PLACED_OFF_LIST",
    "SINGLE_TOKEN_NAME",
    "PRIOR_ID_CONFLICT",
]
EXACT = {"exact_name", "exact_code"}
# what the data asserts about an offering; a confirmed choice that disagrees is challenged
DATA_SAYS = EXACT | {"code_match", "CODE_MATCH_NAMES_DIFFER", "CODE_NOT_IN_PLACEMENTS"}
NEW_ID = r"(?i)new[\w\-]*"
WEAK_LINK_BELOW = 0.85  # fuzzy/weak-key links under this are always reviewed


def is_yes(v) -> bool:
    return str(v).strip().lower() in YES


def node_key(raw):
    """('E', email) or ('N', normalised name); None if neither can be formed."""
    if looks_like_email(raw):
        e = norm_email(raw)
        return ("E", e) if e else None
    n = norm_name(raw)
    return ("N", n) if n else None


def nr_id(offering_name: str) -> str:
    """Stable id for an offered course that has no trip code (did not run)."""
    return "NR-" + hashlib.sha1(norm_course(offering_name).encode()).hexdigest()[:6]


def backup(cfg, rel):
    p = out_path(cfg, rel)
    if p.exists():
        bdir = out_path(cfg, "key/backup")
        bdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(p, bdir / f"{p.stem}.{ts}{p.suffix}")


def read_prior(cfg, final_rel, draft_rel, key_fn):
    """Final and draft merged per row. The draft (what the user last edited) wins;
    rows only the final still has, e.g. while a file is temporarily missing, are
    kept, so nothing accepted is ever dropped."""
    frames, used = [], []
    for rel in (final_rel, draft_rel):
        p = out_path(cfg, rel)
        if p.exists():
            frames.append(pd.read_csv(p, dtype=str).fillna(""))
            used.append(rel)
    if not frames:
        return None, None
    df = pd.concat(frames, ignore_index=True).fillna("")
    df["_k"] = [key_fn(r) for r in df.to_dict("records")]
    df = df.drop_duplicates("_k", keep="last").drop(columns="_k").reset_index(drop=True)
    return df, " + ".join(used)


def id_key(r):
    return node_key(r["identifier"]) or ("?", r["identifier"])


def alias_key(r):
    return (str(r["cycle"]), r["source"], norm_course(r["raw_string"]))


def cat_key(r):
    return (str(r["cycle"]), r["course_id"])


def issued_ids(cfg) -> set:
    p = out_path(cfg, ISSUED)
    return set(p.read_text().split()) if p.exists() else set()


def record_issued(cfg, ids):
    p = out_path(cfg, ISSUED)
    p.write_text("\n".join(sorted((issued_ids(cfg) | set(ids)) - {""})) + "\n")


def fresh_ids(n, exclude):
    pool = [f"T{i:03d}" for i in range(1, 1000) if f"T{i:03d}" not in exclude]
    if len(pool) < n:
        raise SystemExit("ran out of teacher ids (T001-T999)")
    secrets.SystemRandom().shuffle(pool)
    return pool[:n]


def resolve_new_ids(df, exclude=()):
    """Replace NEW tokens in teacher_id with unused random IDs.

    Plain NEW means "this is someone else": rows typed NEW that came from the same
    proposed person become one new person, rows from different proposals become
    different people. A labelled token (NEW1, NEW-a) is one person wherever it is
    used, which is how to gather rows from several proposals into one new person.
    """
    tids = df["teacher_id"].astype(str).str.strip()
    props = df["proposed_id"] if "proposed_id" in df.columns else tids
    keys = []
    for t, pr in zip(tids, props):
        if re.fullmatch(NEW_ID, t):
            keys.append(("NEW", pr) if t.upper() == "NEW" else (t.upper(), ""))
        else:
            keys.append(None)
    groups = sorted({k for k in keys if k})
    if not groups:
        return df, {}
    used = set(tids) | set(props) | set(exclude)
    mapping = dict(zip(groups, fresh_ids(len(groups), used)))
    df = df.copy()
    df["teacher_id"] = [mapping[k] if k else t for k, t in zip(keys, tids)]
    return df, mapping


# ==========================================================================
# identity
# ==========================================================================


class Node:
    def __init__(self, key, display):
        self.key, self.display = key, display
        self.sources: set = set()
        self.placements: Counter = Counter()
        self.prior_tid = ""
        self.prior_proposed = ""
        self.prior_confirmed = False
        self.prior_notes = ""

    @property
    def prior_strong(self):
        """Confirmed by the user, or moved by hand: a decision, not a guess."""
        return bool(self.prior_tid) and (
            self.prior_confirmed
            or bool(self.prior_proposed and self.prior_proposed != self.prior_tid)
        )


class Clusters:
    def __init__(self, nodes):
        self.nodes = nodes
        self.parent = {k: k for k in nodes}
        self.members = {k: {k} for k in nodes}
        # confirmed rows and hand edits are decisions: they bind rows together
        self.lock = {
            k: (nodes[k].prior_tid if nodes[k].prior_strong else "") for k in nodes
        }
        # every ID a member held last time, and the subset the user decided on
        self.hints = {
            k: ({nodes[k].prior_tid} if nodes[k].prior_tid else set()) for k in nodes
        }
        self.strong = {
            k: ({nodes[k].prior_tid} if nodes[k].prior_strong else set()) for k in nodes
        }

    def find(self, k):
        root = k
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[k] != root:
            self.parent[k], k = root, self.parent[k]
        return root

    def kinds(self, r, kind):
        return [m for m in self.members[r] if m[0] == kind]

    def placement_cycles(self, r):
        out = Counter()
        for m in self.members[r]:
            out.update(self.nodes[m].placements)
        return out

    def can_merge(self, a, b, forced=False):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False, "same_cluster"
        la, lb = self.lock[ra], self.lock[rb]
        if la and lb and la != lb:
            return False, "confirmed_as_different_people"
        # a user decision beats evidence: never pull in anyone who held a different ID
        sa, sb = self.strong[ra], self.strong[rb]
        if (sa and not self.hints[rb] <= sa) or (sb and not self.hints[ra] <= sb):
            return False, "kept_apart_by_your_edits"
        if forced:
            return True, ""
        if self.kinds(ra, "E") and self.kinds(rb, "E"):
            return False, "both_have_an_email"
        if set(self.placement_cycles(ra)) & set(self.placement_cycles(rb)):
            return False, "both_placed_in_same_cycle"
        na, nb = self.kinds(ra, "N"), self.kinds(rb, "N")
        if (
            na
            and nb
            and max(name_similarity(x[1], y[1]) for x in na for y in nb) < NAME_LINK_MIN
        ):
            return False, "names_too_different"
        return True, ""

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if len(self.members[ra]) < len(self.members[rb]):
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.members[ra] |= self.members.pop(rb)
        lb = self.lock.pop(rb)
        self.lock[ra] = self.lock[ra] or lb
        self.hints[ra] |= self.hints.pop(rb)
        self.strong[ra] |= self.strong.pop(rb)

    def roots(self):
        return [k for k in self.parent if self.parent[k] == k]


def build_identity(cfg, cycles):
    floor = float(cfg["match_floor"])
    nodes: dict = {}
    same_row = []
    complete_cycles = {cy.key for cy in cycles if cy.repeaters is not None}

    def add(raw, src, placed_in=None):
        k = node_key(raw)
        if k is None:
            return None
        nd = nodes.get(k)
        if nd is None:
            nd = nodes[k] = Node(k, str(raw).strip())
        nd.sources.add(src)
        if placed_in:
            nd.placements[placed_in] += 1
        return k

    for cy in cycles:
        for r in cy.responses:
            ek = add(r.email, f"{cy.key}:{r.round}")
            if r.name:
                nk = add(r.name, f"{cy.key}:{r.round}")
                if ek and nk and nk != ek:
                    same_row.append((ek, nk))
        for rp in cy.repeaters or []:
            add(rp.email, f"{cy.key}:repeaters")
        for s in cy.slots:
            if s.status == "named":
                add(s.sponsor, f"{cy.key}:placements", placed_in=cy.key)

    # ---- prior assignments: confirmed rows are locks, unconfirmed are hints
    prior, prior_src = read_prior(cfg, ID_FINAL, ID_DRAFT, id_key)
    reserved, stale, new_ids = set(issued_ids(cfg)), 0, {}
    stale_rows = []
    if prior is not None:
        if "proposed_id" not in prior.columns:
            prior["proposed_id"] = prior["teacher_id"]
        prior.loc[prior["proposed_id"] == "", "proposed_id"] = prior["teacher_id"]
        prior, new_ids = resolve_new_ids(prior, reserved)
        reserved |= set(prior["proposed_id"]) - {""}
        for r in prior.itertuples():
            tid = str(r.teacher_id).strip()
            if tid:
                reserved.add(tid)
            k = node_key(r.identifier)
            if k in nodes:
                nodes[k].prior_tid = tid
                nodes[k].prior_proposed = r.proposed_id
                nodes[k].prior_confirmed = is_yes(r.confirmed) and bool(tid)
                nodes[k].prior_notes = r.notes
            else:
                stale += 1
                stale_rows.append(r._asdict())

    cl = Clusters(nodes)
    by_tid = defaultdict(list)
    for k, nd in nodes.items():
        if nd.prior_strong:
            by_tid[nd.prior_tid].append(k)
    for ks in by_tid.values():
        for k in ks[1:]:
            if cl.find(k) != cl.find(ks[0]):
                cl.union(ks[0], k)

    # ---- evidence
    edges = []  # (score, method, a, b)
    for ek, nk in same_row:
        edges.append((1.0, "same_row", ek, nk))
    E = sorted(k for k in nodes if k[0] == "E")
    N = sorted(k for k in nodes if k[0] == "N")
    for e in E:
        for n in N:
            m, s = match_score(e[1], n[1])
            if s >= floor - 0.1:
                edges.append((s, m, e, n))
    for i, a in enumerate(N):
        for b in N[i + 1 :]:
            s = name_similarity(a[1], b[1])
            if s >= 0.5:
                edges.append((s, "name_variant", a, b))

    blocked = Counter()
    for s, m, a, b in edges:  # same_row is forced evidence
        if m == "same_row":
            ok, why = cl.can_merge(a, b, forced=True)
            if ok:
                cl.union(a, b)
            elif why != "same_cluster":
                blocked[why] += 1

    def cycles(k):
        return {src.split(":", 1)[0] for src in nodes[k].sources}

    def same_cycle(a, b):
        """An address used in 2027 more plausibly belongs to a name placed in 2027."""
        return bool(cycles(a) & cycles(b))

    order = {"exact_key": 0, "name_variant": 1, "weak_key": 2, "fuzzy": 3}
    for s, m, a, b in sorted(
        edges,
        key=lambda t: (
            -t[0],
            not same_cycle(t[2], t[3]),
            order.get(t[1], 9),
            t[2],
            t[3],
        ),
    ):
        if m == "same_row":
            continue
        need = NAME_LINK_MIN if m == "name_variant" else floor
        if s < need:
            continue
        ok, why = cl.can_merge(a, b)
        if ok:
            cl.union(a, b)
        elif why != "same_cluster":
            blocked[why] += 1

    # ---- teacher ids
    roots = cl.roots()
    tid_of = {}
    taken = set()
    for r in roots:
        if cl.lock[r]:
            tid_of[r] = cl.lock[r]
            taken.add(cl.lock[r])
    soft_conflict = {r for r in roots if len(cl.hints[r]) > 1}
    for r in roots:
        if r in tid_of:
            continue
        hints = Counter(nodes[m].prior_tid for m in cl.members[r] if nodes[m].prior_tid)
        for tid, _ in hints.most_common():
            if tid not in taken:
                tid_of[r] = tid
                taken.add(tid)
                break
    todo = [r for r in sorted(roots) if r not in tid_of]
    for r, tid in zip(todo, fresh_ids(len(todo), taken | reserved)):
        tid_of[r] = tid

    # ---- per-node evidence summary
    adj = defaultdict(list)
    for s, m, a, b in edges:
        adj[a].append((s, m, b))
        adj[b].append((s, m, a))
    for ks in by_tid.values():
        for a in ks:
            for b in ks:
                if a != b:
                    adj[a].append((1.0, "prior_confirmed", b))

    grouped, cluster_flags = [], {}
    method_counts = Counter()
    for r in roots:
        mem = cl.members[r]
        emails, names = cl.kinds(r, "E"), cl.kinds(r, "N")
        pc = cl.placement_cycles(r)
        flags = set()
        if len(emails) > 1:
            flags.add("MULTI_EMAIL")
        if len(names) > 1:
            flags.add("MULTI_NAME")
        if not emails:
            flags.add("PLACED_NO_EMAIL" if set(pc) & complete_cycles else "NO_EMAIL")
        if not names:
            flags.add("NO_NAME")
        if any(v > 1 for v in pc.values()):
            flags.add("TWO_SLOTS_SAME_CYCLE")
        if any(len(n[1].split()) < 2 for n in names):
            flags.add("SINGLE_TOKEN_NAME")
        if r in soft_conflict:
            flags.add("PRIOR_ID_CONFLICT")
        for ek, nk in same_row:
            if (
                ek in mem
                and nk in mem
                and ek[0] == "E"
                and match_score(ek[1], nk[1])[1] < floor
            ):
                flags.add("FORM_NAME_UNLIKE_EMAIL")

        details = {}
        for k in mem:
            same = [(s, m, o) for s, m, o in adj[k] if cl.find(o) == r]
            other = [(s, m, o) for s, m, o in adj[k] if cl.find(o) != r]
            bs = max(same) if same else None
            bo = max(other) if other else None
            if len(mem) == 1:
                method, score, link = "singleton", "", ""
                if bo and bo[0] >= floor:
                    flags.add("NEAR_MISS")
            else:
                method = "same_name" if bs is None else bs[1]
                score, link = (bs[0], nodes[bs[2]].display) if bs else (1.0, "")
            margin = ""
            if bs is not None and bs[1] not in STRONG_METHODS:
                margin = round(bs[0] - (bo[0] if bo else 0.0), 3)
                if margin < LOW_MARGIN:
                    flags.add("LOW_MARGIN")
                if bs[1] in ("fuzzy", "weak_key") and bs[0] < WEAK_LINK_BELOW:
                    flags.add("WEAK_LINK")
                if not same_cycle(k, bs[2]):
                    flags.add("CROSS_CYCLE_LINK")
            method_counts[method] += 1
            details[k] = dict(
                method=method,
                score=score,
                link=link,
                margin=margin,
                other=(bo[0] if bo else ""),
                other_id=(tid_of[cl.find(bo[2])] if bo else ""),
            )
        cluster_flags[r] = flags
        tid = tid_of[r]
        crow = []
        for k in sorted(mem, key=lambda x: (x[0] != "E", x[1])):
            nd, d = nodes[k], details[k]
            carry = nd.prior_tid == tid
            manual = carry and nd.prior_proposed and nd.prior_proposed != tid
            crow.append(
                {
                    "teacher_id": tid,
                    "proposed_id": nd.prior_proposed if manual else tid,
                    "kind": "email" if k[0] == "E" else "name",
                    "identifier": nd.display,
                    "seen_in": "|".join(sorted(nd.sources)),
                    "link_method": d["method"],
                    "link_score": d["score"],
                    "linked_to": d["link"],
                    "nearest_other_score": d["other"],
                    "nearest_other_id": d["other_id"],
                    "margin": d["margin"],
                    "cluster_flags": "|".join(sorted(flags)),
                    "confirmed": "y" if (carry and nd.prior_confirmed) else "",
                    "notes": nd.prior_notes if carry else "",
                }
            )
        grouped.append(crow)
    rows = [x for crow in grouped for x in crow]
    for (
        r
    ) in stale_rows:  # accepted rows whose identifier is absent from this run's files
        rows.append(
            {
                "teacher_id": r["teacher_id"],
                "proposed_id": r.get("proposed_id") or r["teacher_id"],
                "kind": r.get("kind", ""),
                "identifier": r["identifier"],
                "seen_in": "",
                "link_method": "not_in_current_data",
                "link_score": "",
                "linked_to": "",
                "nearest_other_score": "",
                "nearest_other_id": "",
                "margin": "",
                "cluster_flags": "NOT_IN_DATA",
                "confirmed": r.get("confirmed", ""),
                "notes": r.get("notes", ""),
            }
        )
    record_issued(
        cfg, [r["teacher_id"] for r in rows] + [r["proposed_id"] for r in rows]
    )

    report = {
        "nodes_email": len(E),
        "nodes_name": len(N),
        "people": len(roots),
        "same_row_links": len(same_row),
        "blocked": dict(blocked),
        "flags": Counter(f for fl in cluster_flags.values() for f in fl),
        "methods": method_counts,
        "prior_source": prior_src,
        "stale_prior_rows": stale,
        "new_ids": len(new_ids),
        "confirmed_rows": sum(r["confirmed"] == "y" for r in rows),
    }
    return rows, report


# ==========================================================================
# courses
# ==========================================================================


def build_courses(cy, prior_alias, prior_cat):
    """Propose catalogue and alias rows for one cycle."""
    key, notes = cy.key, []
    pnames = {}
    for s in cy.slots:
        pnames.setdefault(s.code, s.course_name)
    has_named = {s.code for s in cy.slots if s.status == "named"}

    pidx = CourseIndex()
    for code, nm in pnames.items():
        pidx.add(code, [nm], [code])

    def locked(source, raw, valid):
        cid = prior_alias.get((key, source, norm_course(raw)))
        return cid if cid and valid(cid) else ""

    by_code = {norm_code(c): c for c in pnames}
    offer_codes = {o.code for o in cy.offerings if o.code}
    listed_sg = {norm_code(c) for c in cy.expected_sg_codes or []}
    not_run = {norm_code(c) for c in cy.not_run_codes}

    def offering_match(o):
        """(course_id, method, score, margin) for one offering, from the data alone."""
        if not cy.offerings_have_codes:
            return pidx.match(o.name)
        if o.code:  # a trip code means the course ran: join on the code, never the name
            pc = by_code.get(norm_code(o.code))
            if not pc:
                return o.code, "CODE_NOT_IN_PLACEMENTS", 1.0, ""
            a, b = norm_course(o.name), norm_course(pnames[pc])
            agree = _ratio(a, b) >= 0.6 or phrase_in(a, b) or phrase_in(b, a)
            return pc, ("code_match" if agree else "CODE_MATCH_NAMES_DIFFER"), 1.0, ""
        # no trip code: the course did not run, unless the placement sheet says it did
        m = pidx.match(o.name)
        if m[1] in EXACT:
            return m[0], "NO_CODE_BUT_IN_PLACEMENTS", 1.0, ""
        return "", "no_code_did_not_run", "", ""

    # 1. offerings -> placement courses (one-to-one)
    offer = []  # [offering, cid, method, score, margin]
    conflict_target = {}  # locked id -> what the data now says
    for o in cy.offerings:
        lk = locked(
            "offerings",
            o.name,
            lambda c: c in pnames or c.startswith("NR-") or c in offer_codes,
        )
        fresh = offering_match(o)
        if lk and fresh[1] in DATA_SAYS and fresh[0] != lk:
            # e.g. a course confirmed as "did not run" now appears in placements
            offer.append([o, lk, "LOCK_CONFLICT", 1.0, ""])
            conflict_target[lk] = fresh[0]
        elif lk:
            offer.append([o, lk, "prior_confirmed", 1.0, ""])
        else:
            offer.append([o, *fresh])
    claims = defaultdict(list)
    for i, rec in enumerate(offer):
        if rec[1] in pnames:
            claims[rec[1]].append(i)
    for cid, idx in claims.items():
        if len(idx) > 1:
            idx.sort(
                key=lambda i: (
                    offer[i][2] not in ("prior_confirmed", "LOCK_CONFLICT"),
                    -float(offer[i][3] or 0),
                )
            )
            for i in idx[1:]:
                offer[i][1:] = ["", "COLLIDED", offer[i][3], ""]

    # 2. Singapore form strings -> placement courses not joined to an offering
    joined = {rec[1] for rec in offer if rec[1] in pnames}
    sg_first = CourseIndex()
    for code, nm in pnames.items():
        if code not in joined:
            sg_first.add(code, [nm], [code])
    sg_evidence = set()
    for r in cy.responses:
        if r.channel == "sg":
            for _, raw in r.ranks:
                cid = sg_first.match(raw)[0]
                if cid:
                    sg_evidence.add(cid)

    # 3. residual pass: unmatched offerings vs placement courses nobody ranked as Singapore
    #    (skipped when the offerings carry trip codes: then a missing code means "did not run")
    pool = [
        c
        for c in pnames
        if c not in joined and c not in sg_evidence and not cy.offerings_have_codes
    ]
    cands = []
    for i, rec in enumerate(offer):
        if rec[1]:
            continue
        o = rec[0]
        on = norm_course(o.name)
        geo = [g for g in (norm_course(o.country), norm_course(o.city)) if g]
        for c in pool:
            pn = norm_course(pnames[c])
            r = _ratio(on, pn)
            if any(phrase_in(g, pn) for g in geo):
                cands.append((max(0.7, r), r, i, c, "GEO_HINT"))
            elif r >= 0.6:
                cands.append((r, r, i, c, "FUZZY_RESIDUAL"))
    used_i, used_c = set(), set()
    for score, r, i, c, m in sorted(cands, key=lambda t: (-t[0], -t[1], t[2], t[3])):
        if i in used_i or c in used_c:
            continue
        rivals = [t for t in cands if t[2] == i and t[3] != c and t[0] >= score - 0.05]
        offer[i][1:] = [c, m + ("_TIED" if rivals else ""), round(score, 3), ""]
        used_i.add(i)
        used_c.add(c)

    # 4. catalogue
    courses = {}
    for code, nm in pnames.items():
        courses[code] = dict(
            trip_code=code,
            placement_name=nm,
            offerings=[],
            city="",
            country="",
            join_method="",
            join_score="",
        )
    for rec in offer:
        o, cid, m, s, _ = rec
        if not cid:
            cid = nr_id(o.name)
            m = "not_in_placements" if m == "UNMATCHED" else m
            rec[1], rec[2] = cid, m
        if cid not in courses:  # did not run, or has a code but no placement row
            courses[cid] = dict(
                trip_code="" if cid.startswith("NR-") else cid,
                placement_name="",
                offerings=[],
                city="",
                country="",
                join_method=m,
                join_score="",
            )
        c = courses[cid]
        c["offerings"].append(o.name)
        c["city"] = c["city"] or o.city
        c["country"] = c["country"] or o.country
        if c["trip_code"]:
            c["join_method"], c["join_score"] = m, s

    missing_sg = []  # listed as Singapore courses but absent from the placement sheet
    for code in cy.expected_sg_codes or []:
        if norm_code(code) not in {norm_code(c) for c in courses}:
            courses[code] = dict(
                trip_code=code,
                placement_name="",
                offerings=[],
                city="",
                country="",
                join_method="",
                join_score="",
            )
            missing_sg.append(code)

    def ran_status(cid):
        if cid in has_named:
            return "y"
        c = courses[cid]
        if c["trip_code"] and cid not in pnames and norm_code(cid) not in not_run:
            return "unknown"  # it has a trip code but no placement row: ask the office
        return "n"

    has_offerings = bool(cy.offerings)
    intl_idx, sg_idx, all_idx = CourseIndex(), CourseIndex(), CourseIndex()
    for cid, c in courses.items():
        names = c["offerings"] + ([c["placement_name"]] if c["placement_name"] else [])
        codes = [c["trip_code"]] if c["trip_code"] else []
        all_idx.add(cid, names, codes)
        if c["offerings"] or not has_offerings:
            intl_idx.add(cid, names, codes)
        if not c["offerings"]:
            sg_idx.add(cid, names, codes)

    # 5. aliases: offerings, form strings, prior course
    alias = []

    def display(cid):
        c = courses.get(cid)
        if not c:
            return ""
        return c["placement_name"] or " | ".join(c["offerings"]) or "(no placement row)"

    for o, cid, m, s, mg in offer:
        alias.append(
            dict(
                cycle=key,
                source="offerings",
                raw_string=o.name,
                course_id=cid,
                matched_course=display(cid),
                method=m,
                score=s,
                margin=mg,
                uses=1,
                rounds="",
                conflict_with=(
                    conflict_target.get(cid, "") if m == "LOCK_CONFLICT" else ""
                ),
            )
        )

    strings = {}
    for r in cy.responses:
        for _, raw in r.ranks:
            e = strings.setdefault(
                (r.channel, norm_course(raw)), {"raw": raw, "rounds": set(), "uses": 0}
            )
            e["rounds"].add(r.round)
            e["uses"] += 1
    for rp in cy.repeaters or []:
        if rp.prior_raw:
            e = strings.setdefault(
                ("prior", norm_course(rp.prior_raw)),
                {"raw": rp.prior_raw, "rounds": {"repeaters"}, "uses": 0},
            )
            e["uses"] += 1

    ranked_by = defaultdict(set)
    for (src, nk), e in sorted(strings.items()):
        lk = locked(src, e["raw"], lambda c: c in courses or c == NONE_COURSE)
        primary = {"intl": intl_idx, "sg": sg_idx}.get(src, all_idx)
        fresh = primary.match(e["raw"])
        conflict = ""
        if lk and fresh[1] in EXACT and fresh[0] != lk:
            conflict = fresh[0]
        elif lk and lk in conflict_target:  # its offering row is in conflict too
            conflict = conflict_target[lk]
        if conflict:
            cid, m, s, mg = lk, "LOCK_CONFLICT", 1.0, ""
        elif lk:
            cid, m, s, mg = lk, "prior_confirmed", 1.0, ""
        else:
            cid, m, s, mg = fresh
            if not cid and src in ("intl", "sg"):
                c2 = all_idx.match(e["raw"])
                if c2[0]:
                    cid, m, s, mg = c2[0], "CROSS_FORM_" + c2[1], c2[2], c2[3]
        if cid and cid != NONE_COURSE and src in ("intl", "sg"):
            ranked_by[cid].add(src)
        alias.append(
            dict(
                cycle=key,
                source=src,
                raw_string=e["raw"],
                course_id=cid,
                matched_course=display(cid),
                method=m,
                score=s,
                margin=mg,
                uses=e["uses"],
                rounds="|".join(sorted(e["rounds"])),
                conflict_with=conflict,
            )
        )

    # 5b. a Singapore-form string that matches nothing probably names the missing course
    guessed = {}
    unmatched_sg = [a for a in alias if a["source"] == "sg" and not a["course_id"]]
    open_missing = [c for c in missing_sg if not ranked_by[c]]
    if len(open_missing) == 1 and len(unmatched_sg) == 1:
        a, code = unmatched_sg[0], open_missing[0]
        a.update(
            course_id=code,
            method="GUESS_MISSING_SG_COURSE",
            matched_course=display(code),
        )
        ranked_by[code].add("sg")
        guessed[code] = a["raw_string"]
    elif unmatched_sg and open_missing:
        notes.append(
            f"{key}: {len(unmatched_sg)} Singapore-form strings match no course and "
            f"{', '.join(open_missing)} {'has' if len(open_missing) == 1 else 'have'} no "
            "placement row. If a string names one of "
            "them, set its course_id to that code in course_alias_draft.csv."
        )

    # 6. course type
    catalogue = []
    for cid in sorted(courses, key=lambda c: (not courses[c]["trip_code"], c)):
        c = courses[cid]
        flags = []
        rb = ranked_by[cid]
        if listed_sg and norm_code(cid) in listed_sg:
            ctype, ev = "sg", "listed in expected_sg_codes"
            if c["offerings"]:
                flags.append("IN_OFFERINGS_AND_SG_LIST")
            if cid in guessed:
                ev += f"; the Singapore-form string {guessed[cid]!r} matches no other course"
        elif c["offerings"]:
            ctype, ev = "intl", "in offerings list"
            if "sg" in rb:
                flags.append("RANKED_IN_SG_FORM")
            if len(c["offerings"]) > 1:
                flags.append("SEVERAL_OFFERINGS")
        elif not has_offerings:
            ctype = "sg" if rb == {"sg"} else "intl" if rb == {"intl"} else ""
            ev = "no offerings list; type from forms"
            if not ctype:
                flags.append("TYPE_UNKNOWN")
        elif "sg" in rb and "intl" in rb:
            ctype, ev = "sg", "not in offerings; ranked in both forms"
            flags.append("RANKED_IN_BOTH_FORMS")
        elif "sg" in rb or cid in sg_evidence:
            ctype, ev = "sg", "not in offerings; ranked in Singapore form"
        elif "intl" in rb:
            ctype, ev = "intl", "not in offerings; ranked in international form"
            flags.append("RANKED_INTL_NOT_IN_OFFERINGS")
        else:
            ctype, ev = "sg", "not in offerings; nobody ranked it; assumed Singapore"
            flags.append("ASSUMED_SG")
        if listed_sg and ctype == "sg" and norm_code(cid) not in listed_sg:
            flags.append("SG_BUT_NOT_IN_SG_LIST")
        if ran_status(cid) == "unknown":
            flags.append("MISSING_FROM_PLACEMENTS")
        if c["join_method"] and needs_review(c["join_method"]) and c["trip_code"]:
            flags.append("JOIN_" + c["join_method"])
        pc = prior_cat.get((key, cid))
        confirmed = ""
        note = ""
        country = c["country"]
        if pc:
            if (
                pc["confirmed"]
                and pc["course_type"] in ("intl", "sg")
                and pc["course_type"] != ctype
            ):
                ctype, ev = pc["course_type"], "prior_confirmed"
            if pc["confirmed"] and pc["country"] and pc["country"] != country:
                country = pc["country"]  # user correction wins
            if pc["course_type"] == ctype:
                confirmed, note = ("y" if pc["confirmed"] else ""), pc["notes"]
        catalogue.append(
            dict(
                cycle=key,
                course_id=cid,
                trip_code=c["trip_code"],
                course_type=ctype,
                ran=ran_status(cid),
                in_offerings="y" if c["offerings"] else "n",
                placement_name=c["placement_name"],
                offerings_name=" | ".join(c["offerings"]),
                arrival_city=c["city"],
                country=country,
                join_method=c["join_method"],
                join_score=c["join_score"],
                type_evidence=ev,
                flags="|".join(flags),
                confirmed=confirmed,
                notes=note,
            )
        )

    # 7. checks worth printing
    n_sg = sum(r["course_type"] == "sg" for r in catalogue)
    joined_n = sum(1 for r in catalogue if r["trip_code"] and r["in_offerings"] == "y")
    nr = sum(1 for r in catalogue if not r["trip_code"])
    missing = sorted(r["course_id"] for r in catalogue if r["ran"] == "unknown")
    summary = dict(
        missing=missing,
        by_code=cy.offerings_have_codes,
        expected_sg_codes=len(cy.expected_sg_codes or []),
        placement_courses=len(pnames),
        offerings=len(cy.offerings),
        joined=joined_n,
        did_not_run=nr,
        sg=n_sg,
        expected_sg=cy.expected_sg_courses,
        continuation_rows=cy.n_continuation_rows,
        alias_methods=Counter(a["method"] for a in alias if a["source"] != "offerings"),
        join_methods=Counter(a["method"] for a in alias if a["source"] == "offerings"),
    )
    for cid in missing:
        why = (
            "is listed in expected_sg_codes"
            if norm_code(cid) in listed_sg
            else "has a trip code in the offerings file"
        )
        notes.append(
            f"{key}: {cid} {why} but has no row on the placement sheet. It is kept as a "
            "course with ran = unknown. When the office answers: if it did not run, add it "
            "to not_run_codes for this cycle; if it ran, get the corrected placement sheet."
        )
    for o, cid, m, s, _ in offer:
        if m == "NO_CODE_BUT_IN_PLACEMENTS":
            notes.append(
                f"{key}: offerings row {o.row} has no trip code (did not run) but its name "
                f"matches placement course {cid}. Joined to it for now; check which is right."
            )
    if listed_sg and n_sg != len(listed_sg):
        notes.append(
            f"{key}: {n_sg} courses classed as Singapore but expected_sg_codes lists "
            f"{len(listed_sg)}; see SG_BUT_NOT_IN_SG_LIST rows in the catalogue."
        )
    elif (
        not listed_sg
        and cy.expected_sg_courses is not None
        and n_sg != int(cy.expected_sg_courses)
    ):
        notes.append(
            f"{key}: {n_sg} courses classed as Singapore but expected "
            f"{cy.expected_sg_courses}. An international course whose placement name "
            "does not match its offerings name gets classed as Singapore; check the "
            "ASSUMED_SG rows in the catalogue."
        )
    for rnd, col, vals in cy.extra_columns:
        hits = sum(1 for v in vals if all_idx.match(v)[0])
        notes.append(
            f"{key} {rnd}: column {col!r} is not in the config and holds {len(vals)} "
            f"values ({hits} look like course names). It is ignored. If it is a "
            "preference, add it to rank_cols; if free text, to freetext_cols; "
            "otherwise to ignore_cols."
        )
    return catalogue, alias, summary, notes


def carry_alias_confirmation(alias, prior_alias_rows):
    """Keep confirmed/notes for alias rows whose mapping did not change."""
    prev = {}
    if prior_alias_rows is not None:
        for r in prior_alias_rows.to_dict("records"):
            prev[alias_key(r)] = (
                r["course_id"],
                r["confirmed"],
                r["notes"],
                r.get("conflict_with", ""),
            )
    for a in alias:
        p = prev.get(alias_key(a))
        same = bool(p) and p[0] == a["course_id"]
        a["notes"] = p[2] if same else ""
        if a["method"] == "LOCK_CONFLICT":
            # confirmed while this very conflict was showing = a deliberate override
            if same and is_yes(p[1]) and p[3] == a["conflict_with"]:
                a["confirmed"], a["method"] = "y", "override_confirmed"
            else:
                a["confirmed"] = ""
        else:
            a["confirmed"] = "y" if same and is_yes(p[1]) else ""


def flag_off_list(cycles, id_rows, alias_all):
    """Flag people placed on a course that is on none of their own lists.

    A form submitter linked to the wrong placement name (qzhou@ -> a different
    'Q. Zhou' who was placed without responding) looks structurally normal; the
    only trace is that the placement is on nobody's list. The same flag also
    marks genuine office discretion, so it asks for a check, not a correction.
    """
    tid_of = {node_key(r["identifier"]): r["teacher_id"] for r in id_rows}
    amap = {
        (a["cycle"], a["source"], norm_course(a["raw_string"])): a["course_id"]
        for a in alias_all
        if a["course_id"]
    }
    flagged = set()
    for cy in cycles:
        ranked, placed = defaultdict(set), defaultdict(set)
        for r in cy.responses:
            t = tid_of.get(("E", r.email))
            for _, raw in r.ranks:
                cid = amap.get((cy.key, r.channel, norm_course(raw)))
                if t and cid:
                    ranked[t].add(cid)
        for s in cy.slots:
            if s.status == "named":
                t = tid_of.get(node_key(s.sponsor))
                if t:
                    placed[t].add(s.code)
        for t, codes in placed.items():
            if ranked.get(t) and not (codes & ranked[t]):
                flagged.add(t)
    for r in id_rows:
        if r["teacher_id"] in flagged:
            fl = set(filter(None, r["cluster_flags"].split("|"))) | {"PLACED_OFF_LIST"}
            r["cluster_flags"] = "|".join(sorted(fl))
    return len(flagged)


def sort_identity_rows(rows):
    """Unconfirmed, most-flagged, weakest-linked people first; one person's rows together."""
    by_tid = defaultdict(list)
    for r in rows:
        by_tid[r["teacher_id"]].append(r)

    def key(tid):
        rs = by_tid[tid]
        fl = {f for x in rs for f in x["cluster_flags"].split("|") if f}
        scored = [
            float(x["link_score"])
            for x in rs
            if x["link_score"] != "" and x["link_method"] not in STRONG_METHODS
        ]
        return (
            all(x["confirmed"] == "y" for x in rs),
            -len(fl & set(SERIOUS)),
            min(scored) if scored else 1.0,
            tid,
        )

    return [
        r
        for tid in sorted(by_tid, key=key)
        for r in sorted(
            by_tid[tid], key=lambda x: (x["kind"] != "email", x["identifier"])
        )
    ]


# ==========================================================================
# CLI
# ==========================================================================


def accept(cfg):
    problems = []
    frames = {}
    for draft in (ID_DRAFT, ALIAS_DRAFT, CAT_DRAFT):
        p = out_path(cfg, draft)
        if not p.exists():
            problems.append(f"{draft} not found; run stage 1 first")
            continue
        df = pd.read_csv(p, dtype=str).fillna("")
        frames[draft] = df
        bad = df[~df["confirmed"].map(is_yes)]
        if len(bad):
            problems.append(
                f"{draft}: {len(bad)} of {len(df)} rows not confirmed "
                f"(first at CSV line {bad.index[0] + 2})"
            )
        if draft == ID_DRAFT:
            if "proposed_id" not in df.columns:
                df["proposed_id"] = df["teacher_id"]
            df, mapping = resolve_new_ids(df, issued_ids(cfg))
            frames[draft] = df
            if mapping:
                print(f"  assigned {len(mapping)} fresh id(s) for NEW entries")
                record_issued(cfg, mapping.values())
            badid = df[~df["teacher_id"].str.fullmatch(r"T\d{3}")]
            if len(badid):
                problems.append(
                    f"{draft}: {len(badid)} rows have a teacher_id that is neither "
                    "T### nor NEW"
                )
            moved = df[
                (df["teacher_id"] != df["proposed_id"])
                & (df["notes"].str.strip() == "")
            ]
            if len(moved):
                problems.append(
                    f"{draft}: {len(moved)} rows were moved to a different teacher_id "
                    f"without a note (first at CSV line {moved.index[0] + 2}); "
                    "add a note saying why, so accidental merges cannot slip through"
                )
            keys = [node_key(v) for v in df["identifier"]]
            if None in keys:
                problems.append(f"{draft}: {keys.count(None)} identifiers are empty")
            owners = defaultdict(set)
            for k, tid in zip(keys, df["teacher_id"]):
                if k:
                    owners[k].add(tid)
            clash = [k for k, ts in owners.items() if len(ts) > 1]
            if clash:
                problems.append(
                    f"{draft}: {len(clash)} identifiers are assigned to two teacher_ids"
                )
        if draft == ALIAS_DRAFT:
            empty = df[df["course_id"].str.strip() == ""]
            if len(empty):
                problems.append(
                    f"{draft}: {len(empty)} rows have no course_id (fill in a course_id, "
                    f"or {NONE_COURSE} if the string is not a course)"
                )
            known = set(
                frames.get(CAT_DRAFT, pd.DataFrame(columns=["course_id"]))["course_id"]
            )
            if CAT_DRAFT not in frames:
                cp = out_path(cfg, CAT_DRAFT)
                if cp.exists():
                    known = set(pd.read_csv(cp, dtype=str).fillna("")["course_id"])
            unknown = df[
                (df["course_id"].str.strip() != "")
                & (df["course_id"] != NONE_COURSE)
                & ~df["course_id"].isin(known)
            ]
            if len(unknown):
                problems.append(
                    f"{draft}: {len(unknown)} rows point to a course_id that is not in "
                    "the catalogue; rerun stage 1 to add it, then review"
                )
            offered = {
                (c, i)
                for c, s, i in zip(df["cycle"], df["source"], df["course_id"])
                if s == "offerings"
            }
            orphan_nr = {
                (c, i)
                for c, s, i in zip(df["cycle"], df["source"], df["course_id"])
                if s != "offerings" and i.startswith("NR-") and (c, i) not in offered
            }
            if orphan_nr:
                problems.append(
                    f"{draft}: {len(orphan_nr)} did-not-run course ids are used by form "
                    "strings but no offering row points to them any more "
                    f"(e.g. {sorted(orphan_nr)[0][1]}); remap those strings"
                )
        if draft == CAT_DRAFT:
            badt = df[~df["course_type"].isin(["intl", "sg"])]
            if len(badt):
                problems.append(
                    f"{draft}: {len(badt)} rows have course_type other than intl/sg"
                )

    mp = out_path(cfg, DRAFT_MANIFEST)
    if mp.exists():
        then = json.loads(mp.read_text())
        now = {cy.key: cy.inputs for cy in load_all(cfg)}
        if then != now:
            problems.append(
                "raw input files changed since the drafts were built; rerun stage 1"
            )
    else:
        problems.append(f"{DRAFT_MANIFEST} missing; rerun stage 1")

    if problems:
        print("NOT ACCEPTED")
        for p in problems:
            print(f"  ! {p}")
        sys.exit(1)
    for draft, final in (
        (ID_DRAFT, ID_FINAL),
        (ALIAS_DRAFT, ALIAS_FINAL),
        (CAT_DRAFT, CAT_FINAL),
    ):
        backup(cfg, final)
        frames[draft].to_csv(out_path(cfg, draft), index=False)  # NEW ids written back
        shutil.copy2(out_path(cfg, draft), out_path(cfg, final))
        print(f"accepted {draft} -> {final}")


def run(cfg, quiet=False):
    out_path(cfg, "key").mkdir(parents=True, exist_ok=True)
    cycles = load_all(cfg)

    id_rows, id_rep = build_identity(cfg, cycles)

    prior_alias_rows, _ = read_prior(cfg, ALIAS_FINAL, ALIAS_DRAFT, alias_key)
    prior_alias = {}
    if prior_alias_rows is not None:
        for r in prior_alias_rows.to_dict("records"):
            if is_yes(r["confirmed"]) and str(r["course_id"]).strip():
                prior_alias[alias_key(r)] = r["course_id"].strip()
    prior_cat_rows, _ = read_prior(cfg, CAT_FINAL, CAT_DRAFT, cat_key)
    prior_cat = {}
    if prior_cat_rows is not None:
        for r in prior_cat_rows.itertuples():
            prior_cat[(str(r.cycle), r.course_id)] = dict(
                course_type=r.course_type,
                confirmed=is_yes(r.confirmed),
                notes=r.notes,
                country=getattr(r, "country", ""),
            )

    cat_all, alias_all, summaries, notes = [], [], {}, []
    for cy in cycles:
        cat, alias, summ, nt = build_courses(cy, prior_alias, prior_cat)
        cat_all += cat
        alias_all += alias
        summaries[cy.key] = summ
        notes += nt
    carry_alias_confirmation(alias_all, prior_alias_rows)
    off = flag_off_list(cycles, id_rows, alias_all)
    id_rep["flags"] = Counter(
        f
        for fl in {r["teacher_id"]: r["cluster_flags"] for r in id_rows}.values()
        for f in fl.split("|")
        if f
    )
    id_rep["off_list"] = off
    id_rows = sort_identity_rows(id_rows)

    def aprio(a):
        m = a["method"]
        tier = (
            3
            if m == "prior_confirmed"
            else (
                0
                if needs_review(m)
                else 2 if m in ("exact_name", "exact_code", "not_in_placements") else 1
            )
        )
        return (a["confirmed"] == "y", tier, a["cycle"], a["source"], a["raw_string"])

    alias_all.sort(key=aprio)
    cat_all.sort(
        key=lambda c: (
            c["confirmed"] == "y",
            not c["flags"],
            c["cycle"],
            c["course_id"],
        )
    )

    for rel in (ID_DRAFT, ALIAS_DRAFT, CAT_DRAFT):
        backup(cfg, rel)
    pd.DataFrame(id_rows).to_csv(out_path(cfg, ID_DRAFT), index=False)
    alias_cols = [
        "cycle",
        "source",
        "raw_string",
        "course_id",
        "matched_course",
        "method",
        "conflict_with",
        "score",
        "margin",
        "uses",
        "rounds",
        "confirmed",
        "notes",
    ]
    pd.DataFrame(alias_all)[alias_cols].to_csv(out_path(cfg, ALIAS_DRAFT), index=False)
    pd.DataFrame(cat_all).to_csv(out_path(cfg, CAT_DRAFT), index=False)
    out_path(cfg, DRAFT_MANIFEST).write_text(
        json.dumps({cy.key: cy.inputs for cy in cycles}, indent=2, sort_keys=True)
    )

    if not quiet:
        print_report(cycles, id_rep, id_rows, summaries, notes, alias_all, cat_all, cfg)
    return dict(identity=id_rep, courses=summaries, notes=notes)


def print_report(cycles, id_rep, id_rows, summaries, notes, alias_all, cat_all, cfg):
    bar = "=" * 70
    print(bar)
    print("IDENTITY (all cycles)")
    print(bar)
    print(
        f"  emails {id_rep['nodes_email']}   distinct names {id_rep['nodes_name']}   "
        f"-> people {id_rep['people']}"
    )
    print(f"  links from forms with both email and name: {id_rep['same_row_links']}")
    if id_rep["prior_source"]:
        print(
            f"  earlier assignments reused from {id_rep['prior_source']} "
            f"({id_rep['confirmed_rows']} rows still confirmed, "
            f"{id_rep['stale_prior_rows']} no longer in the data)"
        )
    print("  how each identifier was linked:")
    for m, n in id_rep["methods"].most_common():
        print(f"    {m:18s} {n:4d}")
    if id_rep["flags"]:
        print("  people flagged for review:")
        for f, n in id_rep["flags"].most_common():
            tag = "  REVIEW" if f in SERIOUS else ""
            print(f"    {f:24s} {n:4d}{tag}")
    if id_rep.get("off_list"):
        print(
            f"  placed on a course not on their own lists: {id_rep['off_list']} "
            "(PLACED_OFF_LIST; verify these links first)"
        )
    if id_rep.get("new_ids"):
        print(f"  NEW entries given fresh ids: {id_rep['new_ids']}")
    if id_rep["blocked"]:
        print("  candidate merges refused:")
        for why, n in sorted(id_rep["blocked"].items()):
            print(f"    {why:30s} {n:4d}")

    for cy in cycles:
        s = summaries[cy.key]
        print()
        print(bar)
        print(f"COURSES {cy.key}")
        print(bar)
        print(
            f"  placements : {s['placement_courses']} courses"
            + (
                f" ({s['continuation_rows']} extra-sponsor rows)"
                if s["continuation_rows"]
                else ""
            )
        )
        print(
            f"  offerings  : {s['offerings']} rows -> {s['joined']} joined to a placement, "
            f"{s['did_not_run']} did not run"
            + (" (joined by trip code)" if s["by_code"] else " (joined by name)")
        )
        if s["expected_sg_codes"]:
            exp = f" (expected_sg_codes lists {s['expected_sg_codes']})"
        elif s["expected_sg"] is not None:
            exp = f" (expected {s['expected_sg']})"
        else:
            exp = ""
        print(f"  Singapore  : {s['sg']}{exp}")
        if s["missing"]:
            print(f"  NO PLACEMENT ROW, ran = unknown: {', '.join(s['missing'])}")
        print("  offerings -> placement join:")
        for m, n in s["join_methods"].most_common():
            print(f"    {m:28s} {n:4d}{'  REVIEW' if needs_review(m) else ''}")
        print("  form and prior-course strings:")
        for m, n in s["alias_methods"].most_common():
            print(f"    {m:28s} {n:4d}{'  REVIEW' if needs_review(m) else ''}")
        blanks = [x for x in cy.slots if x.status != "named"]
        if blanks:
            print(f"  sponsor cells empty or placeholder: {len(blanks)}")
            for x in blanks:
                print(f"    row {x.row}  {x.code}  slot {x.slot}  {x.status}")
        for w in cy.warnings:
            print(f"  ! {w}")

    if notes:
        print()
        print(bar)
        print("NOTES")
        print(bar)
        for n in notes:
            print(f"  ! {n}")

    todo_id = sum(r["confirmed"] != "y" for r in id_rows)
    todo_alias = sum(a["confirmed"] != "y" for a in alias_all)
    todo_cat = sum(c["confirmed"] != "y" for c in cat_all)
    print()
    print(f"wrote {out_path(cfg, 'key')}")
    print(f"  identity_draft.csv          {todo_id:4d} rows to confirm (worst first)")
    print(
        f"  course_alias_draft.csv      {todo_alias:4d} rows to confirm (worst first)"
    )
    print(
        f"  course_catalogue_draft.csv  {todo_cat:4d} rows to confirm (flagged first)"
    )
    print(
        "NEXT: fix anything wrong, set confirmed=y on every row, then rerun with --accept"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default="config/pseudonymize.yaml")
    ap.add_argument(
        "--accept",
        action="store_true",
        help="promote fully confirmed drafts to the final key files",
    )
    args = ap.parse_args()
    cfg = load_config(args.config)
    if args.accept:
        accept(cfg)
    else:
        run(cfg)


if __name__ == "__main__":
    main()
