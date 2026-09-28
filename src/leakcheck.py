"""Find personal identifiers that survived into derived/.

Used by tests/test_leakage.py and by the synthetic end-to-end test. Returns
findings instead of printing them, because the findings themselves are names.
"""

from __future__ import annotations

import re

import pandas as pd

from idmap import EMAIL_RE, email_domain, norm_name, out_path

MIN_TOKEN = 2          # catches Ng, Li, Wu, Ho


def identifier_tokens(cfg) -> set[str]:
    cw = pd.read_csv(out_path(cfg, "key/identity.csv"), dtype=str).fillna("")
    toks = set()
    for kind, ident in zip(cw["kind"], cw["identifier"]):
        if kind == "email":
            local = ident.lower().split("@")[0]
            toks |= {t for t in re.split(r"[^a-z]+", local) if len(t) >= MIN_TOKEN}
        else:
            toks |= {t for t in norm_name(ident).split() if len(t) >= MIN_TOKEN}
    return toks


def allowlist(cfg) -> set[str]:
    p = out_path(cfg, "key/leakage_allowlist.txt")
    if not p.exists():
        return set()
    return {ln.strip().lower() for ln in p.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")}


def find_leaks(cfg) -> dict:
    derived = out_path(cfg, "derived")
    files = sorted(p for p in derived.glob("*") if p.is_file())
    blob = "\n".join(p.read_text(errors="replace").lower() for p in files)
    domains = set()
    cw = pd.read_csv(out_path(cfg, "key/identity.csv"), dtype=str).fillna("")
    for kind, ident in zip(cw["kind"], cw["identifier"]):
        if kind == "email" and email_domain(ident):
            domains.add(email_domain(ident))
    ok = allowlist(cfg)
    toks = identifier_tokens(cfg) - ok
    words = set(re.findall(r"[a-z]+", blob))       # whole words only, so "li" never hits "list"
    return {
        "files": [p.name for p in files],
        "emails": sorted(set(EMAIL_RE.findall(blob))),
        "domains": sorted(d for d in domains if d in blob),
        "tokens": sorted(toks & words),
        "stray_text_files": sorted(p.name for p in files if p.suffix == ".txt"),
    }
