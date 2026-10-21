"""Find personal identifiers that survived into derived/.

Used by tests/pseudonymize/test_leakage.py and by the synthetic end-to-end
test. Returns findings instead of printing them, because the findings
themselves are names.
"""

from __future__ import annotations

import re

import pandas as pd

from stable_sponsors.pseudonymize.idmap import (
    EMAIL_RE,
    email_domain,
    norm_name,
    out_path,
)

MIN_TOKEN = 2  # catches Ng, Li, Wu, Ho

# Hex digests (manifest.json) and hashed course codes (NR-3ce91a) are not
# prose, but splitting them on [a-z]+ yields fragments like "ce", "be", "ad"
# that collide with short names, and change on every rebuild. Drop any run of
# 6+ hex characters that contains a digit before tokenizing: a name never
# contains a digit, so this cannot hide a real leak.
HEX_RUN = re.compile(r"(?<![0-9a-z])(?=[0-9a-f]*[0-9])[0-9a-f]{6,}(?![0-9a-z])")


def text_words(blob: str) -> set[str]:
    """Whole lowercase words in blob, ignoring hex digests and hash codes."""
    # whole words only, so "li" never hits "list"
    return set(re.findall(r"[a-z]+", HEX_RUN.sub(" ", blob.lower())))


def identity_tokens_and_domains(cfg) -> tuple[set[str], set[str]]:
    """Name/email-local tokens and email domains from key/identity.csv, in one read."""
    cw = pd.read_csv(out_path(cfg, "key/identity.csv"), dtype=str).fillna("")
    toks, domains = set(), set()
    for kind, ident in zip(cw["kind"], cw["identifier"]):
        if kind == "email":
            local = ident.lower().split("@")[0]
            toks |= {t for t in re.split(r"[^a-z]+", local) if len(t) >= MIN_TOKEN}
            if d := email_domain(ident):
                domains.add(d)
        else:
            toks |= {t for t in norm_name(ident).split() if len(t) >= MIN_TOKEN}
    return toks, domains


def allowlist(cfg) -> set[str]:
    p = out_path(cfg, "key/leakage_allowlist.txt")
    if not p.exists():
        return set()
    return {
        ln.strip().lower()
        for ln in p.read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    }


def find_leaks(cfg) -> dict:
    derived = out_path(cfg, "derived")
    files = sorted(p for p in derived.glob("*") if p.is_file())
    blob = "\n".join(p.read_text(errors="replace").lower() for p in files)
    toks, domains = identity_tokens_and_domains(cfg)
    toks -= allowlist(cfg)
    words = text_words(blob)
    return {
        "files": [p.name for p in files],
        "emails": sorted(set(EMAIL_RE.findall(blob))),
        "domains": sorted(d for d in domains if d in blob),
        "tokens": sorted(toks & words),
        "stray_text_files": sorted(p.name for p in files if p.suffix == ".txt"),
    }
